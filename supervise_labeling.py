import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.models.database import SessionLocal, Document
from backend.services.paper_analyzer import analyze_paper
from sqlalchemy import or_

def run_supervision():
    db = SessionLocal()
    # Find up to 3 papers that have 'arxiv' or 'Unknown' in their venue
    docs = db.query(Document).filter(
        or_(
            Document.venue.ilike('%arxiv%'),
            Document.venue.ilike('%unknown%'),
            Document.venue == '',
            Document.venue == None
        )
    ).limit(3).all()
    
    if not docs:
        print("No papers found needing re-labeling!")
        return

    for doc in docs:
        print(f"\n[{doc.id}] Processing: {doc.title}")
        print(f"   Current Venue: {doc.venue}")
        
        # Analyze
        res = analyze_paper(doc.file_path)
        
        new_venue = res.get('venue', 'Unknown')
        new_ccf = res.get('ccf_partition', '')
        
        print(f" -> Result Venue: {new_venue}")
        if new_ccf:
            print(f" -> CCF Partition: {new_ccf}")
        
        # Update db
        doc.venue = new_venue
        if new_ccf:
            doc.ccf_partition = new_ccf
            
        # Update other fields if necessary
        for k in ['zh_title', 'paper_type', 'abstract', 'en_abstract', 'research_field', 'research_direction']:
            if res.get(k):
                setattr(doc, k, res.get(k))
                
        # Handle keywords
        if res.get('en_keywords'):
            doc.en_keywords = ", ".join(res.get('en_keywords'))
            
        db.commit()
        print(f" -> DB Updated for doc ID {doc.id}")
        
    db.close()

if __name__ == "__main__":
    run_supervision()
