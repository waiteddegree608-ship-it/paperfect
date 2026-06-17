import os
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, Boolean, Table
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime
from backend.core.config import get_base_dir

# SQLite Database initialization
db_path = os.path.join(get_base_dir(), "data", "paperfect_library.db")
os.makedirs(os.path.dirname(db_path), exist_ok=True)
engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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
Base.metadata.create_all(bind=engine)
