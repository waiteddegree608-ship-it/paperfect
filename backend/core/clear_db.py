import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.models.database import SessionLocal, Document, Tag, document_tag_association

def clear_db():
    db = SessionLocal()
    try:
        db.execute(document_tag_association.delete())
        db.query(Document).delete()
        db.query(Tag).delete()
        db.commit()
        print("Cleared documents and tags.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    clear_db()
