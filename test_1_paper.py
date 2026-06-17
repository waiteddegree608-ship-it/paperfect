import os, sys
sys.path.append('e:/workspace/ddl')
from backend.models.database import SessionLocal, Document
from backend.services.paper_analyzer import analyze_paper

db = SessionLocal()
doc = db.query(Document).filter(Document.id == 23).first()
if doc:
    print(f'Processing: {doc.title}', flush=True)
    res = analyze_paper(doc.file_path)
    print(f'New Venue: {res.get("venue")}', flush=True)
    doc.venue = res.get('venue')
    db.commit()
db.close()
