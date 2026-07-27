import os
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Table
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
from backend.core.config import get_base_dir

# SQLite Database initialization
db_path = os.path.normpath(os.path.join(get_base_dir(), "data", "paperfect_library.db"))

# Self-healing database check
if os.path.exists(db_path):
    if os.path.getsize(db_path) == 0:
        print(f"[Warning] Database file {db_path} is 0 bytes. Deleting to recreate...")
        try:
            os.remove(db_path)
        except Exception as e:
            print(f"[Error] Failed to delete 0-byte database: {e}")
    else:
        import sqlite3
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check;")
            row = cursor.fetchone()
            conn.close()
            if not row or row[0] != "ok":
                print(f"[Warning] Database {db_path} is corrupted. Deleting to recreate...")
                os.remove(db_path)
        except Exception as e:
            print(f"[Warning] Database integrity check failed: {e}. Deleting to recreate...")
            try:
                os.remove(db_path)
            except Exception:
                pass

try:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    # Convert backslashes to forward slashes for SQLite URL compatibility in SQLAlchemy
    db_path_url = db_path.replace("\\", "/")
    # timeout=30s waits on locks instead of failing; WAL reduces "UI freeze when navigating"
    # while a background task (parse/translate) is writing.
    engine = create_engine(
        f"sqlite:///{db_path_url}",
        connect_args={"check_same_thread": False, "timeout": 30},
        pool_pre_ping=True,
    )
    try:
        with engine.connect() as _conn:
            _conn.exec_driver_sql("PRAGMA journal_mode=WAL;")
            _conn.exec_driver_sql("PRAGMA synchronous=NORMAL;")
            _conn.exec_driver_sql("PRAGMA busy_timeout=30000;")
    except Exception as _pragma_err:
        print(f"[DB] PRAGMA setup warning: {_pragma_err}")
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception as e:
    print("\n" + "="*80)
    print("  [FATAL ERROR] 数据库连接创建失败！/ Database Engine Initialization Failed!")
    print(f"  路径: {db_path}")
    print(f"  错误详情: {e}")
    print("  这通常是因为程序安装在 C:\\ 根目录下且没有管理员写入权限。")
    print("  解决方法: 请尝试以【管理员身份运行】此程序，或者重新运行安装包，")
    print("            选择安装在不需要管理员权限的目录（例如桌面、文档或 C:\\Users\\ 目录下）。")
    print("="*80 + "\n")
    raise e

Base = declarative_base()

# Many-to-Many relationship table for Document and Tag
document_tag_association = Table(
    'document_tag',
    Base.metadata,
    Column('document_id', Integer, ForeignKey('documents.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)

class Folder(Base):
    __tablename__ = "folders"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    parent_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    documents = relationship("Document", back_populates="folder")
    subfolders = relationship("Folder", backref="parent", remote_side=[id])

class Document(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True, nullable=False) # Original English Title
    zh_title = Column(String, nullable=True) # Translated Chinese Title
    original_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    upload_time = Column(DateTime, default=datetime.utcnow)
    venue = Column(String, nullable=True)
    paper_type = Column(String, nullable=True) # 研究 / 综述
    jcr_partition = Column(String, nullable=True) # 一区 / 二区
    ccf_partition = Column(String, nullable=True) # A / B / C
    core_type = Column(String, nullable=True) # 南大核心 / 北大核心 / 中文核心
    research_field = Column(String, nullable=True)
    research_direction = Column(String, nullable=True)
    
    abstract = Column(Text, nullable=True)
    en_abstract = Column(Text, nullable=True)
    en_keywords = Column(Text, nullable=True) # JSON array string
    folder_id = Column(Integer, ForeignKey("folders.id"), nullable=True)
    
    # Relationships
    folder = relationship("Folder", back_populates="documents")
    tags = relationship("Tag", secondary=document_tag_association, back_populates="documents")

class Tag(Base):
    __tablename__ = "tags"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    category = Column(String, index=True, nullable=False) # e.g. JCR, CCF, keywords, etc.
    
    # Relationships
    documents = relationship("Document", secondary=document_tag_association, back_populates="tags")

class DocumentRelation(Base):
    __tablename__ = "document_relations"
    id = Column(Integer, primary_key=True, index=True)
    source_doc_id = Column(Integer, ForeignKey("documents.id"))
    target_doc_id = Column(Integer, ForeignKey("documents.id"))
    relation_type = Column(String, nullable=False) # e.g. 'shared_keywords', 'citation'
    weight = Column(Integer, default=1)

class JournalMeta(Base):
    __tablename__ = "journal_meta"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False, unique=True)
    ccf_level = Column(String, nullable=True) # A, B, C
    jcr_level = Column(String, nullable=True) # Q1, Q2, Q3, Q4

# Create tables
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print("\n" + "="*80)
    print("  [FATAL ERROR] 数据库表创建失败！/ Database Schema Creation Failed!")
    print(f"  路径: {db_path}")
    print(f"  错误详情: {e}")
    print("  这通常是因为程序安装在 C:\\ 根目录下且没有管理员写入权限。")
    print("  解决方法: 请尝试以【管理员身份运行】此程序，或者重新运行安装包，")
    print("            选择安装在不需要管理员权限的目录（例如桌面、文档或 C:\\Users\\ 目录下）。")
    print("="*80 + "\n")
    raise e
