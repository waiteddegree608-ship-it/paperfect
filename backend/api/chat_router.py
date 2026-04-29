import re
from fastapi import APIRouter
from pydantic import BaseModel
from openai import OpenAI
from backend.core.config import load_config
from backend.services.file_manager import get_item_by_name

router = APIRouter()

class ChatRequest(BaseModel):
    book_name: str
    message: str
    chat_history: list

def simple_rag_search(kb_path, query):
    with open(kb_path, "r", encoding="utf-8") as f:
         content = f.read()
         
    chunks = re.split(r'\n##\s+|\n###\s+', content)
    
    stopwords = ["的", "了", "吗", "呢", "什么是", "怎么", "?", "？"]
    keywords = set([w for w in query if w not in stopwords])
    if not keywords: keywords = set(query)
    
    scored_chunks = []
    for chunk in chunks:
        score = sum([2 for kw in keywords if kw in chunk])
        if score > 0:
            scored_chunks.append((score, chunk))
            
    scored_chunks.sort(key=lambda x: x[0], reverse=True)
    top_chunks = [c[1][:1000] for c in scored_chunks[:3]]
    return "\n======\n".join(top_chunks)

@router.post("/api/chat")
async def chat_api(req: ChatRequest):
    book = get_item_by_name(req.book_name)
    if not book: return {"reply": "Book not found"}
    
    try:
        context = simple_rag_search(book["kb_path"], req.message)
        
        sys_prompt = f"""你是【{req.book_name}】专属私教助教。
请严格基于底下提取的【知识库内部切片信息】来回答用户，如果里面没提到，请不要生搬硬造。

【提取到的教材切片信息】：
{context}
"""
        messages = [{"role": "system", "content": sys_prompt}]
        for hist in req.chat_history:
            messages.append({"role": hist["role"], "content": hist["content"]})
        messages.append({"role": "user", "content": req.message})
        
        cfg = load_config()
        chat_client = OpenAI(api_key=cfg["chat_api_key"], base_url=cfg["chat_api_url"])
        
        response = chat_client.chat.completions.create(
            model=cfg.get("chat_model", "Qwen/Qwen3-VL-235B-A22B-Thinking"),
            messages=messages,
            max_tokens=2048,
            temperature=0.7
        )
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        return {"reply": f"API调用遇到错误：{str(e)}"}
