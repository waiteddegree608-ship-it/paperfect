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
            model=cfg.get("chat_model", "Qwen/Qwen2.5-72B-Instruct"),
            messages=messages,
            max_tokens=2048,
            temperature=0.7
        )
        return {"reply": response.choices[0].message.content}
    except Exception as e:
        return {"reply": f"API调用遇到错误：{str(e)}"}

class TranslateRequest(BaseModel):
    book_name: str
    selected_text: str

@router.post("/api/realtime_translate")
async def realtime_translate_api(req: TranslateRequest):
    book = get_item_by_name(req.book_name)
    if not book: return {"translation": "Book not found"}
    
    try:
        context = simple_rag_search(book["kb_path"], req.selected_text)
        
        sys_prompt = f"""你是一个专业的学术翻译专家。请严格基于底下提取的【论文上下文信息】来翻译用户选中的句子，确保专业术语的准确性和语句的流畅。
        如果上下文中有帮助理解该句子的内容，请参考它。

【论文上下文信息】：
{context[:2000]}  # 限制上下文长度防止噪声过大
"""
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"请翻译以下句子：\n{req.selected_text}\n\n注意：只需输出最精准的中文翻译结果，绝对不要输出 <begin_of_box>、<end_of_box> 等任何 XML/HTML/内部标记，也不要包含解释性废话或重复原文。直接给出中文翻译即可。"}
        ]
        
        cfg = load_config()
        
        # fallback to chat model if translate model is not fully configured, though translate is preferred.
        api_url = cfg.get("translate_api_url") or cfg.get("chat_api_url")
        api_key = cfg.get("translate_api_key") or cfg.get("chat_api_key")
        model = cfg.get("translate_model") or cfg.get("chat_model") or "Qwen/Qwen2.5-72B-Instruct"

        chat_client = OpenAI(api_key=api_key, base_url=api_url)
        
        response = chat_client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2048,
            temperature=0.3
        )
        return {"translation": response.choices[0].message.content}
    except Exception as e:
        return {"translation": f"API调用遇到错误：{str(e)}"}

