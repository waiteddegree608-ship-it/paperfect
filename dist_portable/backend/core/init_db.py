import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.models.database import SessionLocal, Folder

def init_db():
    db = SessionLocal()
    try:
        # Check if default folders exist
        default_folder = db.query(Folder).filter(Folder.name == "默认文件夹", Folder.is_system == True).first()
        if not default_folder:
            default_folder = Folder(name="默认文件夹", is_system=True)
            db.add(default_folder)
            
        db.commit()
        print("Database initialized successfully with default folder.")
    except Exception as e:
        print(f"Error initializing database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
