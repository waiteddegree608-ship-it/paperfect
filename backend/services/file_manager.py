import os
import shutil
from backend.core.config import get_base_dir

active_tasks = set()

def scan_items(item_type="book"):
    items = []
    base_dir = get_base_dir()
    target_dir = os.path.join(base_dir, "data", "textbooks" if item_type == "book" else "papers")
    
    if os.path.exists(target_dir):
        for b_name in os.listdir(target_dir):
            book_dir = os.path.join(target_dir, b_name)
            if os.path.isdir(book_dir):
                pdf_file = os.path.join(book_dir, "raw", f"{b_name}.pdf")
                translated_pdf = os.path.join(book_dir, "translated", f"{b_name}_translated.pdf")
                annotated_pdf = os.path.join(book_dir, "marked", f"{b_name}_annotated.pdf")
                kb_file = os.path.join(book_dir, "parsed", f"{b_name}_KnowledgeBase.md")
                pptx_path = os.path.join(book_dir, "pptx", f"{b_name}_Full_Presentation.pptx")
                
                if item_type == "book":
                    if os.path.exists(kb_file):
                        status = "ready"
                        progress = "100%"
                    else:
                        status = "processing" if f"books_{b_name}" in active_tasks else "interrupted"
                        progress = "抽取中"
                else:
                    status = "ready" if os.path.exists(pptx_path) else ("processing" if f"papers_{b_name}" in active_tasks else "interrupted")
                    progress = "生成中"
                    
                items.append({
                    "name": b_name,
                    "pdf_path": pdf_file if os.path.exists(pdf_file) else "",
                    "translated_pdf_path": translated_pdf if os.path.exists(translated_pdf) else "",
                    "annotated_pdf_path": annotated_pdf if os.path.exists(annotated_pdf) else "",
                    "kb_path": kb_file if os.path.exists(kb_file) else "",
                    "status": status,
                    "progress": progress,
                    "type": item_type
                })
    return items

def get_item_by_name(name):
    for b in scan_items("book") + scan_items("paper"):
        if b["name"] == name:
             return b
    return None

def delete_target_item(name: str, type: str):
    target_dir = os.path.join(get_base_dir(), "data", "textbooks" if type == "book" else "papers", name)
    if os.path.exists(target_dir):
        try: shutil.rmtree(target_dir, ignore_errors=True)
        except: pass
    return {"status": "success"}

async def handle_upload_file(file, item_type):
    filename = os.path.basename(file.filename) if file.filename else "unknown.pdf"
    name_part, ext_part = os.path.splitext(filename)
    book_name = name_part.strip()
    if book_name.endswith(".pdf"):
        book_name = book_name[:-4]
    filename = book_name + ext_part.lower()

    target_dir = os.path.join(get_base_dir(), "data", "textbooks" if item_type == "book" else "papers", book_name, "raw")
    os.makedirs(target_dir, exist_ok=True)
    
    pdf_path = os.path.join(target_dir, filename)
    content = await file.read()
    with open(pdf_path, "wb") as buffer:
        buffer.write(content)
        
    return book_name, pdf_path
