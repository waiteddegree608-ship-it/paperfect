import os
from fastapi import APIRouter, UploadFile, File, Form, Request
from backend.services.file_manager import handle_upload_file, get_item_by_name, delete_target_item, scan_items
from backend.services.task_runner import submit_task, active_tasks
from backend.core.config import get_base_dir
from pydantic import BaseModel

router = APIRouter()

@router.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    book_name, pdf_path = await handle_upload_file(file, "book")
    submit_task(pdf_path, book_name, "book")
    return {"status": "processing", "book_name": book_name}

@router.post("/api/upload_paper")
async def upload_paper(file: UploadFile = File(...), prompt_type: str = Form("提示词汇总"), ppt_mode: str = Form("creative")):
    book_name, pdf_path = await handle_upload_file(file, "paper")
    submit_task(pdf_path, book_name, "paper", prompt_type, ppt_mode)
    return {"status": "processing", "book_name": book_name}

@router.delete("/api/delete_target")
async def delete_target(name: str, type: str):
    return delete_target_item(name, type)

@router.post("/api/resume/{book_name}")
async def resume_task(book_name: str):
    target_dir = os.path.join(get_base_dir(), "data", "textbooks", "raw")
    pdf_path = os.path.join(target_dir, f"{book_name}.pdf")
    if os.path.exists(pdf_path):
        submit_task(pdf_path, book_name, "book")
        return {"status": "processing"}
        
    target_dir = os.path.join(get_base_dir(), "data", "papers", "raw")
    pdf_path_paper = os.path.join(target_dir, f"{book_name}.pdf")
    if os.path.exists(pdf_path_paper):
        submit_task(pdf_path_paper, book_name, "paper", "提示词汇总", "creative")
        return {"status": "processing"}
        
    return {"status": "error", "message": "PDF not found"}

@router.get("/api/status/{item_type}/{book_name}")
async def check_status(item_type: str, book_name: str):
    target_dir = os.path.join(get_base_dir(), "data", "textbooks" if item_type == "book" else "papers")
    
    if item_type == "book":
        kb_path = os.path.join(target_dir, "parsed", f"{book_name}_KnowledgeBase.md")
        if os.path.exists(kb_path):
            return {"status": "ready"}
            
        status = "processing" if f"books_{book_name}" in active_tasks else "interrupted"
        progress = "抽取中"
        return {"status": status, "progress": progress}
    else:
        pptx_path = os.path.join(target_dir, "pptx", f"{book_name}_Full_Presentation.pptx")
        return {"status": "ready" if os.path.exists(pptx_path) else "processing"}

# Prompts API
class PromptSaveRequest(BaseModel):
    content: str

@router.get("/api/prompts")
async def list_prompts():
    prompt_dir = os.path.join(get_base_dir(), "standalone_pdf2ppt", "prompts")
    if not os.path.exists(prompt_dir):
        os.makedirs(prompt_dir)
    files = [f for f in os.listdir(prompt_dir) if f.endswith('.md')]
    names = [os.path.splitext(f)[0] for f in files]
    return {"status": "success", "prompts": names}

@router.get("/api/prompts/{prompt_name}")
async def get_prompt(prompt_name: str):
    prompt_dir = os.path.join(get_base_dir(), "standalone_pdf2ppt", "prompts")
    path = os.path.join(prompt_dir, f"{prompt_name}.md")
    if not os.path.exists(path):
        return {"status": "error", "message": "Prompt not found"}
    with open(path, "r", encoding="utf-8") as f:
        return {"status": "success", "content": f.read()}

@router.post("/api/prompts/{prompt_name}")
async def save_prompt(prompt_name: str, req: PromptSaveRequest):
    prompt_name = os.path.basename(prompt_name)
    prompt_dir = os.path.join(get_base_dir(), "standalone_pdf2ppt", "prompts")
    if not os.path.exists(prompt_dir):
        os.makedirs(prompt_dir)
    path = os.path.join(prompt_dir, f"{prompt_name}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(req.content)
    return {"status": "success"}

@router.delete("/api/prompts/{prompt_name}")
async def delete_prompt(prompt_name: str):
    prompt_name = os.path.basename(prompt_name)
    prompt_dir = os.path.join(get_base_dir(), "standalone_pdf2ppt", "prompts")
    path = os.path.join(prompt_dir, f"{prompt_name}.md")
    if os.path.exists(path):
        os.remove(path)
        return {"status": "success"}
    return {"status": "error", "message": "Prompt not found"}
