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
    lang: str = "zh"

def simple_rag_search(kb_path, query):
    with open(kb_path, "r", encoding="utf-8") as f:
         content = f.read()
         
    # Auto-detect language of Knowledge Base
    import re
    cjk_re = re.compile(r'[\u4e00-\u9fff]')
    kb_is_english = not bool(cjk_re.search(content[:1500]))
    query_has_chinese = bool(cjk_re.search(query))
    
    # If KB is English but query has Chinese, translate query to English
    search_query = query
    if kb_is_english and query_has_chinese:
        try:
            from backend.core.config import load_config
            cfg = load_config()
            client = OpenAI(api_key=cfg["chat_api_key"], base_url=cfg["chat_api_url"])
            model = cfg.get("chat_model", "Qwen/Qwen2.5-72B-Instruct")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Translate the user query into a concise English search query for academic papers. Output ONLY the English translation, no other text."},
                    {"role": "user", "content": query}
                ],
                temperature=0.1,
                max_tokens=100
            )
            search_query = response.choices[0].message.content.strip()
            print(f"[RAG] Translated query '{query}' -> '{search_query}'", flush=True)
        except Exception as e:
            print(f"[RAG] Failed to translate query: {e}", flush=True)

    chunks = re.split(r'\n##\s+|\n###\s+', content)
    
    # Extract keywords
    if kb_is_english:
        words = re.findall(r'\b\w+\b', search_query.lower())
        stopwords = {"what", "is", "the", "of", "this", "article", "paper", "in", "a", "an", "and", "or", "for", "to", "on", "with", "at", "by", "from", "about"}
        keywords = set([w for w in words if w not in stopwords and len(w) > 2])
        if not keywords:
            keywords = set(words)
    else:
        stopwords = ["的", "了", "吗", "呢", "什么是", "怎么", "?", "？"]
        keywords = set([w for w in search_query if w not in stopwords])
        if not keywords:
            keywords = set(search_query)
            
    scored_chunks = []
    for chunk in chunks:
        score = 0
        chunk_lower = chunk.lower() if kb_is_english else chunk
        for kw in keywords:
            if kb_is_english:
                if kw in chunk_lower:
                    score += 2
            else:
                if kw in chunk:
                    score += 2
        if score > 0:
            scored_chunks.append((score, chunk))
            
    if not scored_chunks:
        print("[RAG] No keywords matched, returning first 3 chunks as fallback", flush=True)
        top_chunks = [c[:1000] for c in chunks[:4] if c.strip()]
    else:
        scored_chunks.sort(key=lambda x: x[0], reverse=True)
        top_chunks = [c[1][:1000] for c in scored_chunks[:3]]
        
    return "\n======\n".join(top_chunks)

@router.post("/api/chat")
async def chat_api(req: ChatRequest):
    book = get_item_by_name(req.book_name)
    if not book: return {"reply": "Book not found"}
    
    try:
        context = simple_rag_search(book["kb_path"], req.message)
        
        if req.lang == 'en':
            sys_prompt = f"""Answer the user's question strictly based on the knowledge base excerpts below.
Do not introduce yourself. Output the answer directly. If not found, say so honestly.

[Knowledge Base Excerpts]:
{context}
"""
        else:
            sys_prompt = f"""请严格基于底下提取的【知识库内部切片信息】来直接回答用户的问题。
不要进行任何自我介绍，不要添加任何不相关的寒暄或废话，直接输出答案。如果知识库中没有提到，请直接说明没有找到相关信息，不要生搬硬造。

【知识库内部切片信息】：
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
        error_msg = f"API error: {str(e)}" if req.lang == 'en' else f"API调用遇到错误：{str(e)}"
        return {"reply": error_msg}

class TranslateRequest(BaseModel):
    book_name: str
    selected_text: str
    lang: str = "zh"

@router.post("/api/realtime_translate")
async def realtime_translate_api(req: TranslateRequest):
    book = get_item_by_name(req.book_name)
    if not book: return {"translation": "Book not found"}
    
    try:
        if req.lang == 'en':
            sys_prompt = """You are a professional academic translation expert.
Translate the given academic text into clear, professional English.
Only output the final translation. Do not include any explanation or markup."""
            user_msg = f"Translate the following:\n{req.selected_text}"
        else:
            sys_prompt = """你是一个专业的学术翻译专家。
请将用户发给你的这段英文学术文献翻译成专业、流畅的中文。
注意：只需输出最精准的中文翻译结果，绝对不要输出任何内部标记，也不要包含任何解释性废话。直接给出最终的中文翻译即可。"""
            user_msg = f"请翻译以下句子：\n{req.selected_text}"
        
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg}
        ]
        
        cfg = load_config()
        
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
        error_msg = f"API error: {str(e)}" if req.lang == 'en' else f"API调用遇到错误：{str(e)}"
        return {"translation": error_msg}

