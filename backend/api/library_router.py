from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel
import os
import shutil
import json

from backend.models.database import SessionLocal, Folder, Document, Tag, DocumentRelation
from backend.services.paper_analyzer import analyze_paper
from backend.core.config import get_base_dir

router = APIRouter(prefix="/api/library", tags=["library"])

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@router.get("/folders")
def get_folders(db: Session = Depends(get_db)):
    folders = db.query(Folder).all()
    return [{"id": f.id, "name": f.name, "parent_id": f.parent_id, "is_system": f.is_system, "doc_count": db.query(Document).filter(Document.folder_id == f.id).count()} for f in folders]

@router.post("/folders")
def create_folder(name: str = Form(...), parent_id: Optional[int] = Form(None), db: Session = Depends(get_db)):
    folder = Folder(name=name, parent_id=parent_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}

class FolderRenameRequest(BaseModel):
    name: str

class MoveDocumentRequest(BaseModel):
    folder_id: Optional[int] = None

@router.delete("/folders/{folder_id}")
def delete_folder(folder_id: int, db: Session = Depends(get_db)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    db.query(Document).filter(Document.folder_id == folder_id).update({"folder_id": None})
    db.delete(folder)
    db.commit()
    return {"status": "success"}

@router.put("/folders/{folder_id}")
def rename_folder(folder_id: int, req: FolderRenameRequest, db: Session = Depends(get_db)):
    folder = db.query(Folder).filter(Folder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    folder.name = req.name
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}

@router.put("/documents/{doc_id}/move")
def move_document(doc_id: int, req: MoveDocumentRequest, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if req.folder_id is not None:
        folder = db.query(Folder).filter(Folder.id == req.folder_id).first()
        if not folder:
            raise HTTPException(status_code=404, detail="Folder not found")
    doc.folder_id = req.folder_id
    db.commit()
    db.refresh(doc)
    return {"status": "success", "id": doc.id, "folder_id": doc.folder_id}

@router.get("/documents")
def get_documents(folder_id: Optional[int] = None, tag: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(Document)
    if folder_id:
        query = query.filter(Document.folder_id == folder_id)
    if tag:
        query = query.join(Document.tags).filter(Tag.name == tag)
        
    docs = query.all()
    result = []
    for d in docs:
        result.append({
            "id": d.id,
            "title": d.title,
            "zh_title": d.zh_title,
            "original_filename": d.original_filename,
            "upload_time": d.upload_time,
            "venue": d.venue,
            "paper_type": d.paper_type,
            "jcr_partition": d.jcr_partition,
            "ccf_partition": d.ccf_partition,
            "core_type": d.core_type,
            "research_field": d.research_field,
            "research_direction": d.research_direction,
            "abstract": d.abstract,
            "en_abstract": d.en_abstract,
            "en_keywords": d.en_keywords,
            "folder_id": d.folder_id,
            "tags": [{"id": t.id, "name": t.name, "category": t.category} for t in d.tags]
        })
    return result

from backend.services.file_manager import handle_upload_file as old_handle_upload_file
from backend.services.task_runner import active_tasks, async_run_builder

@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    folder_id: int = Form(None),
    folder_name: str = Form(None),
    item_type: str = Form("paper"),
    prompt_type: str = Form("提示词汇总"),
    ppt_mode: str = Form("creative"),
    ppt_lang: str = Form("zh"),
    db: Session = Depends(get_db)
):
    # Determine folder
    if folder_id:
        folder = db.query(Folder).filter(Folder.id == folder_id).first()
    elif folder_name:
        folder = db.query(Folder).filter(Folder.name == folder_name).first()
        if not folder:
            folder = Folder(name=folder_name)
            db.add(folder)
            db.commit()
            db.refresh(folder)
    else:
        folder = db.query(Folder).filter(Folder.name == "默认文件夹").first()

    # Use the old handle_upload_file to save to data/papers or data/textbooks
    book_name, pdf_path = await old_handle_upload_file(file, item_type)
    
    # Save to DB
    doc = Document(
        title=book_name,
        original_filename=f"{book_name}.pdf",
        file_path=pdf_path,
        folder_id=folder.id if folder else None
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    # Trigger background task for parsing/PPT (The old pipeline)
    task_id = f"{item_type}s_{book_name}"
    if task_id not in active_tasks:
        active_tasks.add(task_id)
        if item_type == "paper":
            background_tasks.add_task(async_run_builder, pdf_path, book_name, "paper", prompt_type, ppt_mode, ppt_lang)
        else:
            background_tasks.add_task(async_run_builder, pdf_path, book_name, "book")
            
    # Also trigger the auto-tagging for the new DB in the background
    from backend.services.paper_analyzer import analyze_paper
    from backend.models.database import SessionLocal as SLocal
    
    def auto_tag(doc_id, path):
        db_local = SLocal()
        try:
            analysis = analyze_paper(path)
            doc_to_update = db_local.query(Document).filter(Document.id == doc_id).first()
            if doc_to_update:
                en_title = analysis.get("en_title")
                if en_title and en_title != "Unknown Title":
                    doc_to_update.title = en_title
                doc_to_update.zh_title = analysis.get("zh_title", "")
                doc_to_update.venue = analysis.get("venue", "Unknown")
                doc_to_update.paper_type = analysis.get("paper_type", "")
                doc_to_update.jcr_partition = analysis.get("jcr_partition", "")
                doc_to_update.ccf_partition = analysis.get("ccf_partition", "")
                doc_to_update.core_type = analysis.get("core_type", "")
                f_val = analysis.get("research_field", "")
                doc_to_update.research_field = json.dumps(f_val, ensure_ascii=False) if isinstance(f_val, dict) else str(f_val)
                d_val = analysis.get("research_direction", "")
                doc_to_update.research_direction = json.dumps(d_val, ensure_ascii=False) if isinstance(d_val, dict) else str(d_val)
                doc_to_update.abstract = analysis.get("abstract", "")
                doc_to_update.en_abstract = analysis.get("en_abstract", "")
                doc_to_update.en_keywords = json.dumps(analysis.get("en_keywords", []), ensure_ascii=False)
                
                for kw in analysis.get("zh_keywords", []):
                    kw = kw.strip()
                    if not kw: continue
                    tag = db_local.query(Tag).filter(Tag.name == kw, Tag.category == "Keywords").first()
                    if not tag:
                        tag = Tag(name=kw, category="Keywords")
                        db_local.add(tag)
                    doc_to_update.tags.append(tag)
                db_local.commit()
        except Exception as e:
            print("Auto tag error:", e)
        finally:
            db_local.close()
            
    background_tasks.add_task(auto_tag, doc.id, pdf_path)
    
    return {"status": "success", "id": doc.id, "book_name": book_name}

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
        
    # Delete from DB
    db.delete(doc)
    db.commit()
    
    # Try to delete physical folder using old logic
    from backend.services.file_manager import delete_target_item
    name_without_ext = doc.original_filename.replace('.pdf', '')
    delete_target_item(name_without_ext, "paper")
    delete_target_item(name_without_ext, "book")
    
    return {"status": "success"}

@router.get("/graph")
def get_knowledge_graph(db: Session = Depends(get_db)):
    # Build a simple graph of documents and tags
    nodes = []
    links = []
    
    docs = db.query(Document).all()
    for d in docs:
        nodes.append({"id": f"doc_{d.id}", "name": d.title, "category": 0, "symbolSize": 20})
        for t in d.tags:
            tag_id = f"tag_{t.id}"
            if not any(n["id"] == tag_id for n in nodes):
                nodes.append({"id": tag_id, "name": t.name, "category": 1, "symbolSize": 10})
            links.append({"source": f"doc_{d.id}", "target": tag_id})
    return {"nodes": nodes, "links": links, "categories": [{"name": "Document"}, {"name": "Keyword"}]}

from pydantic import BaseModel
from openai import OpenAI
from backend.core.config import load_config
from backend.api.chat_router import simple_rag_search
from backend.services.file_manager import get_item_by_name

import re

class UniversalSearchRequest(BaseModel):
    message: str
    chat_history: list
    lang: str = "zh"

def extract_json(text: str):
    try:
        return json.loads(text)
    except:
        pass
    
    # Try to find JSON block
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except:
            pass
            
    # Try to find anything that looks like a JSON object
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0).strip())
        except:
            pass
            
    return None

@router.post("/universal_search")
def universal_search(req: UniversalSearchRequest, db: Session = Depends(get_db)):
    # 1. Build a COMPACT catalog string (saves ~70% tokens vs JSON)
    docs = db.query(Document).all()
    catalog_lines = []
    doc_lookup = {}  # id -> doc for later
    for d in docs:
        doc_lookup[d.id] = d
        tags = [t.name for t in d.tags if t.category == 'Keywords']
        tags_str = ",".join(tags[:5]) if tags else ""
        # Compact single-line format: ID | title | zh_title | venue | keywords | abstract_snippet
        abstract_snip = (d.abstract or "")[:80].replace("\n", " ")
        line = f"[{d.id}] {d.title}"
        if d.zh_title:
            line += f" ({d.zh_title})"
        if d.venue and d.venue != "Unknown":
            line += f" @{d.venue}"
        if tags_str:
            line += f" #{tags_str}"
        if abstract_snip:
            line += f" | {abstract_snip}"
        catalog_lines.append(line)
    
    catalog_str = "\n".join(catalog_lines)
    
    if req.lang == 'en':
        sys_prompt = f"""You are an academic literature recommendation assistant. Based on the user's query, recommend the most relevant documents from the knowledge base.

[Document Catalog]
{catalog_str}

[Tool Usage]
To view a document's details, call search_paper_knowledge_base.

[Output Format]
After searching, output JSON:
```json
{{"reply": "Brief English recommendation (max 300 words)", "document_ids": [1, 2]}}
```
If nothing found, set document_ids to empty list."""
    else:
        sys_prompt = f"""你是学术文献推荐助理。根据用户需求，从知识库中推荐最相关的文献。

【知识库文献列表】
{catalog_str}

【工具使用】
如需查看某文献的详细内容，调用 search_paper_knowledge_base 工具。

【输出格式】
完成检索后，输出JSON：
```json
{{"reply": "中文推荐说明（简明扰要）", "document_ids": [1, 2]}}
```
找不到就 document_ids 设空列表。reply 务必简洁，不超过300字。"""
    
    messages = [{"role": "system", "content": sys_prompt}]
    # Only keep last 4 turns of chat history to save context
    recent_history = req.chat_history[-4:] if len(req.chat_history) > 4 else req.chat_history
    for hist in recent_history:
        messages.append({"role": hist["role"], "content": hist["content"]})
    messages.append({"role": "user", "content": req.message})
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_paper_knowledge_base",
                "description": "深入检索特定文献的详细内容（方法、结论等）",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "integer",
                            "description": "文献ID"
                        },
                        "query": {
                            "type": "string",
                            "description": "检索关键词"
                        }
                    },
                    "required": ["document_id", "query"]
                }
            }
        }
    ]
    
    cfg = load_config()
    client = OpenAI(api_key=cfg["chat_api_key"], base_url=cfg["chat_api_url"], timeout=300.0)
    model = cfg.get("chat_model", "Qwen/Qwen2.5-72B-Instruct")
    
    # Collect tool results across iterations for a summarized re-injection
    tool_results_summary = []
    
    # Loop for agentic behavior — max 3 iterations (reduced from 5)
    for iteration in range(3):
        try:
            # On the final possible iteration, drop tools to force a text response
            current_tools = tools if iteration < 2 else None
            
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=current_tools,
                max_tokens=4096,
                temperature=0.5
            )
            
            message = response.choices[0].message
            
            if message.tool_calls:
                # Process tool calls
                assistant_msg = {
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": t.id,
                            "type": "function",
                            "function": {
                                "name": t.function.name,
                                "arguments": t.function.arguments
                            }
                        } for t in message.tool_calls
                    ]
                }
                messages.append(assistant_msg)
                
                for tool_call in message.tool_calls:
                    if tool_call.function.name == "search_paper_knowledge_base":
                        try:
                            args = json.loads(tool_call.function.arguments)
                            doc_id = args.get("document_id")
                            query = args.get("query", "")
                            
                            doc = db.query(Document).filter(Document.id == doc_id).first()
                            if doc:
                                name_without_ext = doc.original_filename.replace('.pdf', '')
                                item_info = get_item_by_name(name_without_ext)
                                if item_info and item_info["kb_path"]:
                                    rag_result = simple_rag_search(item_info["kb_path"], query)
                                    # TRUNCATE tool result to prevent context overflow
                                    tool_result = (rag_result[:800] + "...") if rag_result and len(rag_result) > 800 else (rag_result or "未找到相关信息。")
                                else:
                                    tool_result = "该文献暂无深度知识库文件。"
                            else:
                                tool_result = "未找到该文献。"
                        except Exception as e:
                            tool_result = f"工具执行出错: {str(e)}"
                        
                        # Save summary for potential context rebuild
                        tool_results_summary.append(f"[文献{doc_id}检索结果]: {tool_result[:300]}")
                            
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": tool_result
                        })
                
                # CONTEXT MANAGEMENT: If messages are getting too long, rebuild with summary
                total_content_len = sum(len(str(m.get("content", ""))) for m in messages)
                if total_content_len > 12000:
                    # Rebuild messages: keep system + user question + summarized tool results
                    summary = "\n".join(tool_results_summary)
                    messages = [
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": f"{req.message}\n\n【已检索到的信息摘要】\n{summary}\n\n请根据以上信息直接给出推荐结果JSON。"}
                    ]
                
                continue
            
            # Final response — no tool calls
            content = message.content or ""
            
            with open("data/search_debug.log", "a", encoding="utf-8") as f:
                f.write(f"--- RAW RESPONSE (iter {iteration}) ---\n{content[:500]}\n")
                
            parsed = extract_json(content)
            
            # Intercept hallucinatory tool calls in content
            if parsed and "name" in parsed and "arguments" in parsed and parsed.get("name") == "search_paper_knowledge_base":
                try:
                    tool_args = parsed.get("arguments", {})
                    if isinstance(tool_args, str):
                        tool_args = json.loads(tool_args)
                    doc_id = tool_args.get("document_id")
                    query = tool_args.get("query", "")
                    doc = db.query(Document).filter(Document.id == doc_id).first()
                    if doc:
                        name_without_ext = doc.original_filename.replace('.pdf', '')
                        item_info = get_item_by_name(name_without_ext)
                        if item_info and item_info["kb_path"]:
                            rag_result = simple_rag_search(item_info["kb_path"], query)
                            tool_result = (rag_result[:800] + "...") if rag_result and len(rag_result) > 800 else (rag_result or "未找到相关信息。")
                        else:
                            tool_result = "该文献暂无深度知识库文件。"
                    else:
                        tool_result = "未找到该文献。"
                except Exception as e:
                    tool_result = f"工具执行出错: {str(e)}"
                
                tool_results_summary.append(f"[文献{doc_id}检索结果]: {tool_result[:300]}")
                # Rebuild with summary to force final answer
                summary = "\n".join(tool_results_summary)
                messages = [
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": f"{req.message}\n\n【已检索到的信息摘要】\n{summary}\n\n请直接输出JSON结果。"}
                ]
                continue

            if parsed and "reply" in parsed:
                reply = parsed.get("reply")
                doc_ids = parsed.get("document_ids", [])
            else:
                reply = content
                doc_ids = []
            
            # Fetch full documents
            final_docs = []
            if doc_ids and isinstance(doc_ids, list):
                doc_ids = [int(i) for i in doc_ids if str(i).isdigit() or isinstance(i, int)]
                if doc_ids:
                    docs = db.query(Document).filter(Document.id.in_(doc_ids)).all()
                    for d in docs:
                        final_docs.append({
                            "id": d.id,
                            "title": d.title,
                            "zh_title": d.zh_title,
                            "original_filename": d.original_filename,
                            "venue": d.venue,
                            "paper_type": d.paper_type,
                            "jcr_partition": d.jcr_partition,
                            "ccf_partition": d.ccf_partition,
                            "core_type": d.core_type,
                            "research_field": d.research_field,
                            "research_direction": d.research_direction,
                            "abstract": d.abstract,
                            "tags": [{"id": t.id, "name": t.name, "category": t.category} for t in d.tags]
                        })
                    
            return {"reply": reply, "documents": final_docs}
            
        except Exception as e:
            with open("data/search_debug.log", "a", encoding="utf-8") as f:
                f.write(f"--- ERROR ---\n{str(e)}\n")
            return {"reply": f"系统错误：{str(e)}", "documents": []}
            
    return {"reply": "由于检索过程过于复杂，我未能得出结论。请尝试简化您的需求。", "documents": []}
