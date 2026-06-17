import os
import sys
import json
import time
import json

# Ensure we can import backend
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.models.database import SessionLocal, Document, Tag
from backend.services.paper_analyzer import analyze_paper

def main():
    db = SessionLocal()
    try:
        docs = db.query(Document).all()
        total = len(docs)
        print(f"Found {total} documents. Starting re-analysis...")
        
        for i, doc in enumerate(docs):
            if doc.venue and doc.venue != "Unknown" and "arxiv" not in doc.venue.lower() and "Unknown" not in doc.title:
                print(f"[{i+1}/{total}] Skipping {doc.title} (Venue: {doc.venue})")
                continue
            
            print(f"[{i+1}/{total}] Processing: {doc.title} (ID: {doc.id})")
            if not os.path.exists(doc.file_path):
                print(f"  -> File not found: {doc.file_path}, skipping.")
                continue
                
            try:
                analysis = analyze_paper(doc.file_path)
                
                en_title = analysis.get("en_title")
                if en_title and en_title != "Unknown Title":
                    doc.title = en_title
                doc.zh_title = analysis.get("zh_title", "")
                doc.venue = analysis.get("venue", "Unknown")
                doc.paper_type = analysis.get("paper_type", "")
                doc.jcr_partition = analysis.get("jcr_partition", "")
                doc.ccf_partition = analysis.get("ccf_partition", "")
                doc.core_type = analysis.get("core_type", "")
                doc.research_field = analysis.get("research_field", "")
                doc.research_direction = analysis.get("research_direction", "")
                doc.abstract = analysis.get("abstract", "")
                doc.en_abstract = analysis.get("en_abstract", "")
                doc.en_keywords = json.dumps(analysis.get("en_keywords", []), ensure_ascii=False)
                
                # Handle tags
                for kw in analysis.get("zh_keywords", []):
                    kw = kw.strip()
                    if not kw: continue
                    tag = db.query(Tag).filter(Tag.name == kw, Tag.category == "Keywords").first()
                    if not tag:
                        tag = Tag(name=kw, category="Keywords")
                        db.add(tag)
                    if tag not in doc.tags:
                        doc.tags.append(tag)
                
                db.commit()
                print(f"  -> Success. Venue: {doc.venue}, CCF: {doc.ccf_partition}")
            except Exception as e:
                print(f"  -> Error analyzing document ID {doc.id}: {e}")
                db.rollback()
            
            time.sleep(1.5) # Prevent rate limiting
                
        print("Re-analysis complete.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
