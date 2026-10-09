import os, sys, time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from backend.models.database import SessionLocal, Document
from backend.services.paper_analyzer import analyze_paper
from sqlalchemy import or_

def run_batch_labeling():
    db = SessionLocal()
    docs = db.query(Document).filter(
        or_(
            Document.venue.ilike('%arxiv%'),
            Document.venue.ilike('%unknown%'),
            Document.venue == '',
            Document.venue == None
        )
    ).all()
    
    if not docs:
        print("🎉 全部完成！没有需要打标的论文了。")
        db.close()
        return

    print(f"🚀 发现 {len(docs)} 篇需要重新打标的论文，开始批量处理...")
    
    for i, doc in enumerate(docs):
        print(f"\n[{i+1}/{len(docs)}] ID: {doc.id} | {doc.title}")
        print(f"   当前 Venue: {doc.venue}")
        
        try:
            res = analyze_paper(doc.file_path)
            new_venue = res.get('venue', 'Unknown')
            new_ccf = res.get('ccf_partition', '')
            
            print(f"   ✅ 解析 Venue: {new_venue} (CCF: {new_ccf})")
            
            doc.venue = new_venue
            if new_ccf: doc.ccf_partition = new_ccf
            
            for k in ['zh_title', 'paper_type', 'abstract', 'en_abstract', 'research_field', 'research_direction']:
                if res.get(k): setattr(doc, k, res.get(k))
                    
            if res.get('en_keywords'):
                doc.en_keywords = ", ".join(res.get('en_keywords'))
                
            db.commit()
            
            # 为了防止被 API 封禁，每次处理完休息一小会
            time.sleep(2)
        except Exception as e:
            print(f"   ❌ 处理失败: {e}")
            db.rollback()
            
    db.close()
    print("\n✅ 批量打标工作全部完成！")

if __name__ == "__main__":
    run_batch_labeling()
