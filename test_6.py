import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.models.database import SessionLocal, Document
from backend.services.paper_analyzer import analyze_paper

db = SessionLocal()
doc = db.query(Document).filter(Document.id == 6).first()
if doc:
    print('Starting analysis...')
    res = analyze_paper(doc.file_path)
    print('Venue:', res.get('venue'))
    doc.venue = res.get('venue', 'Unknown')
    db.commit()
db.close()
