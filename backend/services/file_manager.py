import os
import shutil
from backend.core.config import get_base_dir

active_tasks = set()

def scan_items(item_type="book"):
    items = []
    base_dir = get_base_dir()
    target_dir = os.path.join(base_dir, "data", "textbooks" if item_type == "book" else "papers")
    
    # Check if target dir exists
    raw_dir = os.path.join(target_dir, "raw")
    if os.path.exists(raw_dir):
        for f in os.listdir(raw_dir):
            if f.endswith(".pdf"):
                b_name = os.path.splitext(f)[0]
                pdf_file = os.path.join(raw_dir, f)
                translated_pdf = os.path.join(target_dir, "translated", f"{b_name}_translated.pdf")
                annotated_pdf = os.path.join(target_dir, "marked", f"{b_name}_annotated.pdf")
                
                if item_type == "book":
                    kb_file = os.path.join(target_dir, "parsed", f"{b_name}_KnowledgeBase.md")
                    if os.path.exists(kb_file):
                        status = "ready"
                        progress = "100%"
                    else:
                        status = "processing" if f"books_{b_name}" in active_tasks else "interrupted"
                        progress = "抽取中"
                else:
                    kb_file = os.path.join(target_dir, "parsed", f"{b_name}_KnowledgeBase.md")
                    pptx_path = os.path.join(target_dir, "pptx", f"{b_name}_Full_Presentation.pptx")
                    status = "ready" if os.path.exists(pptx_path) else ("processing" if f"papers_{b_name}" in active_tasks else "interrupted")
                    progress = "生成中"
                    
                items.append({
                    "name": b_name,
                    "pdf_path": pdf_file,
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
    target_dir = os.path.join(get_base_dir(), "data", "textbooks" if type == "book" else "papers")
    
    paths_to_delete = [
        os.path.join(target_dir, "raw", f"{name}.pdf"),
        os.path.join(target_dir, "translated", f"{name}_translated.pdf"),
        os.path.join(target_dir, "marked", f"{name}_annotated.pdf"),
        os.path.join(target_dir, "parsed", f"{name}_KnowledgeBase.md"),
        os.path.join(target_dir, "parsed", f"输出结果_{name}.md"),
        os.path.join(target_dir, "pptx", f"{name}_Full_Presentation.pptx")
    ]
    
    for p in paths_to_delete:
        if os.path.exists(p):
            try: os.remove(p)
            except: pass
            
    # Also clean up images related to this
    images_dir = os.path.join(target_dir, "images")
    if os.path.exists(images_dir):
        for img in os.listdir(images_dir):
            if img.startswith(f"{name}_"):
                try: os.remove(os.path.join(images_dir, img))
                except: pass

    cache_dir = os.path.join(target_dir, "cache")
    if os.path.exists(cache_dir):
        for c in os.listdir(cache_dir):
            if c.startswith(f"{name}_"):
                try: os.remove(os.path.join(cache_dir, c))
                except: pass
        
    return {"status": "success"}

async def handle_upload_file(file, item_type):
    target_dir = os.path.join(get_base_dir(), "data", "textbooks" if item_type == "book" else "papers", "raw")
    os.makedirs(target_dir, exist_ok=True)
    
    filename = os.path.basename(file.filename) if file.filename else "unknown.pdf"
    name_part, ext_part = os.path.splitext(filename)
    filename = name_part.strip() + ext_part.lower()

    if filename.endswith(".pdf.pdf"):
        filename = filename[:-4]
        
    pdf_path = os.path.join(target_dir, filename)
    content = await file.read()
    with open(pdf_path, "wb") as buffer:
        buffer.write(content)
        
    book_name = os.path.splitext(filename)[0]
    return book_name, pdf_path
