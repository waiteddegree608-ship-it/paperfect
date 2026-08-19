import os
from fastapi import APIRouter, UploadFile, File, Form, Request, BackgroundTasks
from backend.services.file_manager import handle_upload_file, get_item_by_name, delete_target_item, scan_items, active_tasks, active_tasks_progress
from backend.services.task_runner import async_run_builder
from backend.core.config import get_base_dir
from pydantic import BaseModel
import json

router = APIRouter()

@router.post("/api/upload")
async def upload_pdf(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    result = await handle_upload_file(file, "book")
    book_name, pdf_path = result[0], result[1]
    task_id = f"books_{book_name}"
    if task_id not in active_tasks:
        active_tasks.add(task_id)
        background_tasks.add_task(async_run_builder, pdf_path, book_name, "book")
    return {"status": "processing", "book_name": book_name}

@router.post("/api/upload_paper")
async def upload_paper(background_tasks: BackgroundTasks, file: UploadFile = File(...), prompt_type: str = Form("提示词汇总"), ppt_mode: str = Form("creative"), ppt_lang: str = Form("zh")):
    result = await handle_upload_file(file, "paper")
    book_name, pdf_path = result[0], result[1]
    task_id = f"papers_{book_name}"
    if task_id not in active_tasks:
        active_tasks.add(task_id)
        background_tasks.add_task(async_run_builder, pdf_path, book_name, "paper", prompt_type, ppt_mode, ppt_lang)
    return {"status": "processing", "book_name": book_name}

@router.delete("/api/delete_target")
async def delete_target(name: str, type: str):
    return delete_target_item(name, type)

@router.post("/api/resume/{book_name:path}")
async def resume_task(book_name: str, background_tasks: BackgroundTasks, prompt_type: str = "提示词汇总", ppt_mode: str = "creative", ppt_lang: str = "zh"):
    """Resume interrupted pipeline. Skips stages that already produced artifacts (see task_runner)."""
    from urllib.parse import unquote
    book_name = unquote(book_name or "").strip().strip("/")

    target_dir = os.path.join(get_base_dir(), "data", "textbooks", book_name, "raw")
    pdf_path = os.path.join(target_dir, f"{book_name}.pdf")
    if os.path.exists(pdf_path):
        task_id = f"books_{book_name}"
        if task_id not in active_tasks:
            active_tasks.add(task_id)
            background_tasks.add_task(async_run_builder, pdf_path, book_name, "book")
        return {"status": "processing", "book_name": book_name, "type": "book"}

    target_dir = os.path.join(get_base_dir(), "data", "papers", book_name, "raw")
    pdf_path_paper = os.path.join(target_dir, f"{book_name}.pdf")
    # Fallback: any pdf in raw/
    if not os.path.exists(pdf_path_paper) and os.path.isdir(target_dir):
        for f in os.listdir(target_dir):
            if f.lower().endswith(".pdf") and "annotated" not in f.lower():
                pdf_path_paper = os.path.join(target_dir, f)
                break
    if os.path.exists(pdf_path_paper):
        task_id = f"papers_{book_name}"
        flags = {"do_translate": True, "do_annotate": True, "do_ppt": True}
        pipe_fp = os.path.join(get_base_dir(), "data", "papers", book_name, "pipeline.json")
        try:
            if os.path.isfile(pipe_fp):
                with open(pipe_fp, "r", encoding="utf-8") as f:
                    saved = json.load(f) or {}
                for k in flags:
                    if k in saved:
                        flags[k] = bool(saved[k])
        except Exception:
            pass
        if task_id not in active_tasks:
            active_tasks.add(task_id)
            background_tasks.add_task(
                async_run_builder,
                pdf_path_paper,
                book_name,
                "paper",
                prompt_type,
                ppt_mode,
                ppt_lang,
                flags["do_translate"],
                flags["do_annotate"],
                flags["do_ppt"],
            )
        return {"status": "processing", "book_name": book_name, "type": "paper"}

    return {"status": "error", "message": "PDF not found"}

@router.get("/api/status/{item_type}/{book_name}")
async def check_status(item_type: str, book_name: str):
    target_dir = os.path.join(get_base_dir(), "data", "textbooks" if item_type == "book" else "papers", book_name)
    
    if item_type == "book":
        if f"books_{book_name}" in active_tasks:
            status = "processing"
            progress_info = active_tasks_progress.get(f"books_{book_name}", {"percent": 0, "stage": "准备中..."})
            return {
                "status": status, 
                "progress": progress_info.get("stage", "准备中..."), 
                "percent": progress_info.get("percent", 50)
            }
            
        kb_path = os.path.join(target_dir, "parsed", f"{book_name}_KnowledgeBase.md")
        if os.path.exists(kb_path):
            return {"status": "ready"}
            
        return {"status": "interrupted", "progress": "已中断", "percent": 0}
    else:
        if f"papers_{book_name}" in active_tasks:
            status = "processing"
            progress_info = active_tasks_progress.get(f"papers_{book_name}", {"percent": 0, "stage": "生成中"})
            return {
                "status": status, 
                "progress": progress_info.get("stage", "生成中"), 
                "percent": progress_info.get("percent", 50)
            }
            
        pptx_path = os.path.join(target_dir, "pptx", f"{book_name}_Full_Presentation.pptx")
        if os.path.exists(pptx_path):
            return {"status": "ready"}
        
        return {"status": "interrupted", "progress": "已中断", "percent": 0}

# Prompts API
class PromptSaveRequest(BaseModel):
    content: str

@router.get("/api/prompts")
async def list_prompts(lang: str = "zh"):
    prompt_dir = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "prompts")
    if not os.path.exists(prompt_dir):
        os.makedirs(prompt_dir)
        
    files = [f for f in os.listdir(prompt_dir) if f.endswith('.md') and not f.endswith('_en.md') and not f.endswith('_zh.md')]
    
    prompts_list = []
    for f in files:
        original_name = os.path.splitext(f)[0]
        path = os.path.join(prompt_dir, f"{original_name}_{lang}.md")
        if not os.path.exists(path):
            path = os.path.join(prompt_dir, f)
            
        display_name = original_name
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as file:
                    first_line = file.readline().strip()
                    if first_line.startswith("## "):
                        display_name = first_line[3:].strip()
            except Exception:
                pass
                
        prompts_list.append({
            "id": original_name,
            "name": display_name
        })
        
    return {"status": "success", "prompts": prompts_list}

@router.get("/api/prompts/{prompt_name}")
async def get_prompt(prompt_name: str, lang: str = "zh"):
    prompt_name = os.path.basename(prompt_name)
    prompt_dir = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "prompts")
    
    # Try language-specific file first, then fall back to master template
    path = os.path.join(prompt_dir, f"{prompt_name}_{lang}.md")
    if not os.path.exists(path):
        path = os.path.join(prompt_dir, f"{prompt_name}.md")
        
    if not os.path.exists(path):
        return {"status": "error", "message": "Prompt not found"}
    with open(path, "r", encoding="utf-8") as f:
        return {"status": "success", "content": f.read()}

def translate_prompt_task(prompt_name: str, content: str, target_lang: str):
    try:
        from backend.core.config import load_config
        from openai import OpenAI
        cfg = load_config()
        client = OpenAI(api_key=cfg["chat_api_key"], base_url=cfg["chat_api_url"])
        model = cfg.get("chat_model", "Qwen/Qwen2.5-72B-Instruct")
        
        if target_lang == "en":
            sys_prompt = "You are a professional academic translation assistant. Translate the following Chinese academic prompt template into English. Keep the layout, headers, and bullet points identical. Output ONLY the English translation, no other text."
        else:
            sys_prompt = "You are a professional academic translation assistant. Translate the following English academic prompt template into Chinese. Keep the layout, headers, and bullet points identical. Output ONLY the Chinese translation, no other text."
            
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": content}
            ],
            temperature=0.1
        )
        translated_content = response.choices[0].message.content.strip()
        
        prompt_dir = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "prompts")
        target_file = os.path.join(prompt_dir, f"{prompt_name}_{target_lang}.md")
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(translated_content)
        print(f"[Prompt Auto-Trans] Successfully translated '{prompt_name}' to {target_lang}", flush=True)
    except Exception as e:
        print(f"[Prompt Auto-Trans] Failed to translate: {e}", flush=True)

@router.post("/api/prompts/{prompt_name}")
async def save_prompt(prompt_name: str, req: PromptSaveRequest, background_tasks: BackgroundTasks, lang: str = "zh"):
    prompt_name = os.path.basename(prompt_name)
    prompt_dir = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "prompts")
    if not os.path.exists(prompt_dir):
        os.makedirs(prompt_dir)
        
    # 1. Save language-specific file
    path = os.path.join(prompt_dir, f"{prompt_name}_{lang}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(req.content)
        
    # Also save as master file for fallback
    master_path = os.path.join(prompt_dir, f"{prompt_name}.md")
    with open(master_path, "w", encoding="utf-8") as f:
        f.write(req.content)
        
    # 2. Trigger auto-translation for the other language
    other_lang = "en" if lang == "zh" else "zh"
    background_tasks.add_task(translate_prompt_task, prompt_name, req.content, other_lang)
        
    return {"status": "success"}

@router.delete("/api/prompts/{prompt_name}")
async def delete_prompt(prompt_name: str):
    prompt_name = os.path.basename(prompt_name)
    prompt_dir = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "prompts")
    path = os.path.join(prompt_dir, f"{prompt_name}.md")
    deleted = False
    if os.path.exists(path):
        os.remove(path)
        deleted = True
    # Also delete language-specific files if they exist
    for lang in ["zh", "en"]:
        lang_path = os.path.join(prompt_dir, f"{prompt_name}_{lang}.md")
        if os.path.exists(lang_path):
            os.remove(lang_path)
            deleted = True
            
    if deleted:
        return {"status": "success"}
    return {"status": "error", "message": "Prompt not found"}
