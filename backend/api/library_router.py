from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List, Optional
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
    return [{"id": f.id, "name": f.name, "parent_id": f.parent_id, "is_system": f.is_system} for f in folders]

@router.post("/folders")
def create_folder(name: str = Form(...), parent_id: Optional[int] = Form(None), db: Session = Depends(get_db)):
    folder = Folder(name=name, parent_id=parent_id)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return {"id": folder.id, "name": folder.name, "parent_id": folder.parent_id}

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

@router.post("/api/library/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    folder_id: int = Form(None),
    folder_name: str = Form(None),
    item_type: str = Form("paper"),
    prompt_type: str = Form("提示词汇总"),
    ppt_mode: str = Form("creative"),
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
            background_tasks.add_task(async_run_builder, pdf_path, book_name, "paper", prompt_type, ppt_mode)
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
                doc_to_update.research_field = analysis.get("research_field", "")
                doc_to_update.research_direction = analysis.get("research_direction", "")
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
    # 1. Fetch catalog
    docs = db.query(Document).all()
    catalog = []
    for d in docs:
        tags = [t.name for t in d.tags if t.category == 'Keywords']
        catalog.append({
            "id": d.id,
            "title": d.title,
            "zh_title": d.zh_title,
            "venue": d.venue,
            "keywords": tags,
            # Limit abstract length to save tokens
            "abstract_snippet": d.abstract[:150] if d.abstract else ""
        })
    
    catalog_str = json.dumps(catalog, ensure_ascii=False)
    
    sys_prompt = f"""你是一个专业的学术文献推荐助理，你需要帮助用户检索本地文献知识库。
当前知识库中的所有文献概览如下（包含文献ID、标题、期刊和摘要片段）：
{catalog_str}

你的任务是理解用户的需求，推荐知识库中最相关的文献。

【重要规则：如何使用工具】
如果你觉得仅仅看概览无法确定，你必须**直接调用** `search_paper_knowledge_base` 工具，通过文献ID深入搜索该文献的具体内容。
**绝对不要**在最终回复中说“让我去检索一下”或“我马上为您查找”之类的话而不实际调用工具！只要你需要看内容，就立刻调用工具。

【重要规则：如何输出最终结果】
当你完成了所有检索，准备给出最终的推荐结果时，你必须输出**且仅输出**一段 Markdown 格式的 JSON，包含：
```json
{{
  "reply": "你的对话回复（用中文），详细向用户解释你为什么推荐这些文献，总结它们的亮点。请务必是一段完整的回复！",
  "document_ids": [1, 2, 3]
}}
```
- 如果找不到相关的，请在 reply 中如实告知，并将 document_ids 设为空列表 []。
"""
    
    messages = [{"role": "system", "content": sys_prompt}]
    for hist in req.chat_history:
        messages.append({"role": hist["role"], "content": hist["content"]})
    messages.append({"role": "user", "content": req.message})
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "search_paper_knowledge_base",
                "description": "如果单凭摘要无法判断，调用此工具深入检索特定文献的内容。你可以通过它查看论文的方法、作者单位等详细信息。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "integer",
                            "description": "要深入检索的文献ID"
                        },
                        "query": {
                            "type": "string",
                            "description": "检索的关键词或具体问题（如：作者单位是什么？方法细节是什么？）"
                        }
                    },
                    "required": ["document_id", "query"]
                }
            }
        }
    ]
    
    cfg = load_config()
    # 增加超时时间到10分钟(600秒)，防止长回复时连接中断
    client = OpenAI(api_key=cfg["chat_api_key"], base_url=cfg["chat_api_url"], timeout=600.0)
    model = cfg.get("chat_model", "Qwen/Qwen2.5-72B-Instruct")
    
    # Loop for agentic behavior
    for _ in range(5):  # Max 5 iterations
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=tools,
                # 去除 response_format={"type": "json_object"}，因为它会严重干扰 Qwen 的工具调用逻辑
                max_tokens=8192,
                temperature=0.5
            )
            
            message = response.choices[0].message
            
            if message.tool_calls:
                # Need to include the assistant message before the tool responses
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
                                    tool_result = rag_result if rag_result else "未找到相关信息。"
                                else:
                                    tool_result = "该文献暂无深度知识库文件。"
                            else:
                                tool_result = "未找到该文献。"
                        except Exception as e:
                            tool_result = f"工具执行出错: {str(e)}"
                            
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "name": tool_call.function.name,
                            "content": tool_result
                        })
                # Continue loop to send tool results back to LLM
                continue
            
            # If no tool calls, this is the final response
            content = message.content or ""
            
            # Log the raw response for debugging
            with open("data/search_debug.log", "a", encoding="utf-8") as f:
                f.write(f"--- RAW RESPONSE ---\n{content}\n")
                
            parsed = extract_json(content)
            
            # Intercept hallucinatory tool calls put directly into content
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
                            tool_result = rag_result if rag_result else "未找到相关信息。"
                        else:
                            tool_result = "该文献暂无深度知识库文件。"
                    else:
                        tool_result = "未找到该文献。"
                except Exception as e:
                    tool_result = f"工具执行出错: {str(e)}"
                    
                messages.append({
                    "role": "assistant",
                    "content": content
                })
                messages.append({
                    "role": "user",
                    "content": f"工具调用结果：\n{tool_result}\n\n请根据上述工具返回的内容，必须输出包含 'reply' 和 'document_ids' 的标准JSON格式。"
                })
                continue

            if parsed and "reply" in parsed:
                reply = parsed.get("reply")
                doc_ids = parsed.get("document_ids", [])
            else:
                # Fallback if the model didn't output the expected format
                reply = content
                doc_ids = []
            
            # Fetch full documents
            final_docs = []
            if doc_ids and isinstance(doc_ids, list):
                # Ensure ids are integers
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
