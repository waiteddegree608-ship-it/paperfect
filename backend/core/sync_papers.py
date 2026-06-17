import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.models.database import SessionLocal, Document, Folder, Tag
from backend.services.paper_analyzer import analyze_paper
from backend.services.file_manager import scan_items
from backend.core.config import get_base_dir

def sync_existing_items():
    db = SessionLocal()
    try:
        # Get default folder
        default_folder = db.query(Folder).filter(Folder.name == "默认文件夹", Folder.is_system == True).first()
        if not default_folder:
            print("Database not initialized properly. Missing default folder.")
            return

        # Combine both books and papers
        items = scan_items("book") + scan_items("paper")
        
        print(f"Found {len(items)} existing items. Starting sync and auto-tagging...")
        
        for item in items:
            name = item["name"]
            pdf_path = item["pdf_path"]
            
            if not pdf_path or not os.path.exists(pdf_path):
                print(f"Skip: {name} (PDF file not found)")
                continue
                
            # Check if already in DB
            existing_doc = db.query(Document).filter(Document.original_filename == f"{name}.pdf").first()
            if existing_doc:
                print(f"Skip: {name} (Already exists in database)")
                continue
                
            print(f"Processing: {name} ... (Calling SiliconFlow AI API for auto-tagging)")
            
            # Analyze using API
            analysis = analyze_paper(pdf_path)
            
            # Save to DB
            en_title = analysis.get("en_title")
            if not en_title or en_title == "Unknown Title":
                en_title = name
                
            doc = Document(
                title=en_title,
                zh_title=analysis.get("zh_title", ""),
                original_filename=f"{name}.pdf",
                file_path=pdf_path,
                venue=analysis.get("venue", "Unknown"),
                paper_type=analysis.get("paper_type", ""),
                jcr_partition=analysis.get("jcr_partition", ""),
                ccf_partition=analysis.get("ccf_partition", ""),
                core_type=analysis.get("core_type", ""),
                research_field=analysis.get("research_field", ""),
                research_direction=analysis.get("research_direction", ""),
                abstract=analysis.get("abstract", ""),
                en_abstract=analysis.get("en_abstract", ""),
                en_keywords=json.dumps(list(set(analysis.get("en_keywords", []))), ensure_ascii=False),
                folder_id=default_folder.id
            )
            db.add(doc)
            db.commit()
            db.refresh(doc)
            
            # Save Keywords (Unique)
            keywords = list(set(analysis.get("zh_keywords", [])))
            for kw in keywords:
                kw = kw.strip()
                if not kw: continue
                tag = db.query(Tag).filter(Tag.name == kw, Tag.category == "Keywords").first()
                if not tag:
                    tag = Tag(name=kw, category="Keywords")
                    db.add(tag)
                doc.tags.append(tag)
                
            db.commit()
            print(f"Successfully synced: {name} | Title: {doc.title[:20]}... | Tags: {len(keywords)}")
            
        print("Sync completed successfully.")
    except Exception as e:
        print(f"Error during sync: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    sync_existing_items()
