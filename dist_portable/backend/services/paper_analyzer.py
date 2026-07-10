import fitz
import json
import re
import os
import requests
import time
import difflib
from openai import OpenAI
from backend.core.config import load_config, get_base_dir

def extract_identifier(text: str):
    """提取文本前部的 DOI 或 ArXiv ID"""
    # 匹配 DOI (e.g. 10.1109/CVPR52688.2022.01035)
    doi_match = re.search(r'\b(10\.\d{4,9}/[-._;()/:a-zA-Z0-9]+)\b', text)
    if doi_match:
        return f"DOI:{doi_match.group(1)}"
    
    # 匹配 ArXiv (e.g. arXiv:2203.01194 or arxiv.org/abs/2203.01194)
    arxiv_match = re.search(r'(?:arxiv:\s*|arxiv\.org/abs/)(\d{4}\.\d{4,5}(?:v\d+)?)', text, re.I)
    if arxiv_match:
        return f"ARXIV:{arxiv_match.group(1)}"
        
    return None

def fetch_arxiv_metadata(arxiv_id: str):
    """从 ArXiv API 获取元数据，专门解析 comment 以获取被接收的会议/期刊"""
    try:
        import urllib.request
        import xml.etree.ElementTree as ET
        
        clean_id = arxiv_id.replace("ARXIV:", "").strip()
        clean_id = re.sub(r'v\d+$', '', clean_id)
        
        url = f"http://export.arxiv.org/api/query?id_list={clean_id}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        response = urllib.request.urlopen(req, timeout=5)
        xml_data = response.read()
        
        tree = ET.fromstring(xml_data)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'arxiv': 'http://arxiv.org/schemas/atom'}
        
        entry = tree.find('.//atom:entry', ns)
        if entry is not None:
            title = entry.find('atom:title', ns)
            abstract = entry.find('atom:summary', ns)
            published = entry.find('atom:published', ns)
            
            comment = entry.find('arxiv:comment', ns)
            journal_ref = entry.find('arxiv:journal_ref', ns)
            
            data = {}
            if title is not None: data['title'] = title.text.replace('\n', ' ').strip()
            if abstract is not None: data['abstract'] = abstract.text.replace('\n', ' ').strip()
            if published is not None: data['year'] = published.text[:4]
            
            venue_hints = []
            if journal_ref is not None and journal_ref.text:
                venue_hints.append(f"Journal Ref: {journal_ref.text}")
            if comment is not None and comment.text:
                venue_hints.append(f"Comment: {comment.text}")
                
            if venue_hints:
                data['venue_hints'] = " | ".join(venue_hints)
                
            return data
    except Exception as e:
        print(f"ArXiv API error for {arxiv_id}: {e}")
    return None

def fetch_s2_metadata(identifier: str):
    """从 Semantic Scholar 获取高置信度元数据"""
    try:
        clean_id = identifier
        if identifier.startswith("ARXIV:"):
            clean_id = re.sub(r'v\d+$', '', identifier)
            
        url = f"https://api.semanticscholar.org/graph/v1/paper/{clean_id}?fields=title,venue,abstract,year"
        # 增加重试次数和等待时间应对 429
        for attempt in range(3):
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                if data and data.get("title"):
                    return data
            elif response.status_code == 429: # Too Many Requests
                time.sleep(2.5) # 官方要求1秒1个请求，稳妥起见等2.5秒
            else:
                break
    except Exception as e:
        print(f"S2 API error for {identifier}: {e}")
    return None

def fetch_crossref_metadata_by_title(title: str):
    """通过标题回退检索 Crossref (无严格速率限制，作为兜底)"""
    try:
        import urllib.parse
        q = urllib.parse.quote(title)
        url = f"https://api.crossref.org/works?query.title={q}&select=title,container-title,event&rows=1"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            items = data.get("message", {}).get("items", [])
            if items:
                item = items[0]
                found_title = item.get("title", [""])[0] if item.get("title") else ""
                
                # 必须检查标题相似度，防止 Crossref 返回完全无关的模糊匹配论文
                similarity = difflib.SequenceMatcher(None, title.lower(), found_title.lower()).ratio()
                if similarity < 0.8:
                    return None
                    
                venue = ""
                if "event" in item and "name" in item["event"]:
                    venue = item["event"]["name"]
                    if "acronym" in item["event"]:
                        venue = item["event"]["acronym"] + " " + venue
                elif "container-title" in item and item["container-title"]:
                    venue = item["container-title"][0]
                
                if venue:
                    return {"venue": venue}
    except Exception as e:
        print(f"Crossref API title search error for {title}: {e}")
    return None

def analyze_paper(pdf_path: str):
    """
    Extract title, venue, abstract, and keywords from the first few pages of a PDF paper.
    """
    config = load_config()
    api_key = config.get("paper_api_key") or config.get("chat_api_key")
    base_url = config.get("paper_api_url") or config.get("chat_api_url")
    model = config.get("paper_model") or config.get("chat_model")
    
    fallback_result = {"title": "Unknown Title", "venue": "Unknown", "abstract": "", "keywords": []}
    
    if not api_key:
        print("No API key available for paper analysis.")
        return fallback_result
        
    try:
        doc = fitz.open(pdf_path)
        text = ""
        # 根据需求扩大扫描页数到3页
        for i in range(min(3, len(doc))):
            text += doc[i].get_text("text")
        doc.close()
        
        if not text.strip():
            return fallback_result
            
        # 1. 尝试提取唯一标识符并请求 API 获取先验知识
        identifier = extract_identifier(text)
        s2_metadata = None
        s2_context_str = ""
        
        if identifier:
            print(f"Identified paper ID: {identifier}, querying APIs...")
            
            if identifier.startswith("ARXIV:"):
                arxiv_metadata = fetch_arxiv_metadata(identifier)
                if arxiv_metadata:
                    s2_context_str += f"""
                    [Prior Knowledge from ArXiv API]
                    Title: {arxiv_metadata.get('title', '')}
                    Year: {arxiv_metadata.get('year', '')}
                    Abstract: {arxiv_metadata.get('abstract', '')}
                    Venue Hints (IMPORTANT FOR VENUE EXTRACTION): {arxiv_metadata.get('venue_hints', '')}
                    """
            
            s2_metadata = fetch_s2_metadata(identifier)
            if s2_metadata:
                s2_context_str += f"""
                [Prior Knowledge from Semantic Scholar API]
                Title: {s2_metadata.get('title', '')}
                Venue: {s2_metadata.get('venue', '')}
                Year: {s2_metadata.get('year', '')}
                Abstract: {s2_metadata.get('abstract', '')}
                """
                
            if s2_context_str:
                s2_context_str += "\nIMPORTANT INSTRUCTION: Use the above Prior Knowledge for `en_title`, `venue`, and `en_abstract` where possible. Specially, pay attention to 'Venue Hints' or 'Venue' from Prior Knowledge to extract the correct journal or conference name."
                
        client = OpenAI(api_key=api_key, base_url=base_url)
        
        prompt = f"""
        You are an academic paper analyzer. Analyze the following text extracted from the beginning of a paper.
        Extract the required fields precisely.
        {s2_context_str}
        
        IMPORTANT: 
        1. Extract the original English title as `en_title`. (Use Prior Knowledge if provided).
        2. Translate the title into Simplified Chinese as `zh_title`.
        3. Extract the original English abstract as `en_abstract`. (Use Prior Knowledge if provided).
        4. Translate the abstract into Simplified Chinese as `abstract`.
        5. Extract original English keywords into `en_keywords`.
        6. Extract/Translate all keywords into Simplified Chinese into `zh_keywords`.
        7. Extract the publication venue (journal or conference name, e.g. "IEEE Transactions...", "CVPR 2023", "Nature") as `venue`. Do not include the year, just the name. 
           CRITICAL: If Prior Knowledge provides a venue, use it! If no Prior Knowledge is provided and you must extract it from the text, DO NOT guess "arxiv" unless the text EXPLICITLY says "arXiv" or "Preprint". If you are unsure or cannot find a clear journal/conference name, MUST output "Unknown".
        8. Based on the abstract and title, determine if the paper is a review paper or a research paper. Output "综述" or "研究" in `paper_type`.
        9. Determine the macro research field as a JSON object with "zh" (Simplified Chinese) and "en" (English) keys (e.g. {{"zh": "计算机视觉", "en": "Computer Vision"}}).
        10. Determine the specific research direction as a JSON object with "zh" (Simplified Chinese) and "en" (English) keys (e.g. {{"zh": "3D服装生成", "en": "3D Garment Generation"}}).
        
        Output ONLY raw JSON format (do not use markdown blocks like ```json). It must parse successfully using json.loads().
        
        {{
            "en_title": "Original English Title",
            "zh_title": "论文的中文翻译标题",
            "venue": "Venue name",
            "paper_type": "研究" (or "综述"),
            "en_abstract": "Original english abstract",
            "abstract": "论文的中文摘要内容",
            "en_keywords": ["keyword1", "keyword2"],
            "zh_keywords": ["中文关键词1", "中文关键词2"],
            "research_field": {{"zh": "宏观研究领域", "en": "Macro research field"}},
            "research_direction": {{"zh": "微观研究方向", "en": "Micro research direction"}}
        }}
        
        Text:
        {text[:4000]}
        """
        
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )
        
        content = response.choices[0].message.content.strip()
        
        # Clean markdown code blocks if the model ignored instructions
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
            
        result = json.loads(content.strip())
        
        # Apply Keyword Dictionary Mapping for Chinese keywords
        dict_path = os.path.join(get_base_dir(), "data", "keyword_dict.json")
        kw_dict = {}
        if os.path.exists(dict_path):
            with open(dict_path, "r", encoding="utf-8") as f:
                try:
                    kw_dict = json.load(f)
                except Exception:
                    pass
        
        mapped_keywords = []
        dict_updated = False
        for kw in result.get("zh_keywords", []):
            if kw in kw_dict:
                mapped_keywords.append(kw_dict[kw])
            else:
                kw_dict[kw] = kw
                mapped_keywords.append(kw)
                dict_updated = True
                
        if dict_updated:
            with open(dict_path, "w", encoding="utf-8") as f:
                json.dump(kw_dict, f, ensure_ascii=False, indent=4)
                
        result["keywords"] = list(set(mapped_keywords)) # Keep for backwards compatibility
        result["zh_keywords"] = list(set(mapped_keywords))
        
        # Ensure correct keys
        for k in ["en_title", "zh_title", "venue", "paper_type", "en_abstract", "abstract", "research_field", "research_direction"]:
            if k not in result:
                result[k] = ""
        for k in ["en_keywords", "zh_keywords", "keywords"]:
            if k not in result:
                result[k] = []
                
        # 2. 如果之前获取的信息或 LLM 仍然输出了 arxiv 或 unknown，执行标题兜底查询
        if result.get("en_title") and result.get("en_title") != "Unknown Title":
            ai_venue = result.get("venue", "").lower()
            if not ai_venue or "arxiv" in ai_venue or "unknown" in ai_venue:
                print(f"Fallback: Searching Crossref by title: {result['en_title']}")
                s2_search_res = fetch_crossref_metadata_by_title(result["en_title"])
                if s2_search_res:
                    s2_venue = s2_search_res.get("venue")
                    if s2_venue and "arxiv" not in s2_venue.lower() and "unknown" not in s2_venue.lower():
                        print(f"  -> Found better venue via title search: {s2_venue}")
                        result["venue"] = s2_venue
                        # 如果需要，这里也可以进一步覆盖英文摘要等
                
        # Venue Dictionary Matching
        venue_dict_path = os.path.join(get_base_dir(), "data", "venue_dict.json")
        result["ccf_partition"] = ""
        result["jcr_partition"] = ""
        result["core_type"] = ""
        
        if os.path.exists(venue_dict_path):
            with open(venue_dict_path, "r", encoding="utf-8") as f:
                try:
                    v_dict = json.load(f)
                    ai_venue = result["venue"].strip()
                    matched = None
                    
                    ai_venue_clean = ai_venue.lower()
                    words = set(re.findall(r'\b[A-Za-z]+\b', ai_venue))
                    
                    # 1. Exact acronym match (highest priority)
                    for k, v in v_dict.items():
                        if k in words and k.upper() == k and len(k) > 1:
                            matched = v
                            break
                            
                    # 2. Fuzzy and proportional substring match
                    if not matched:
                        best_match = None
                        best_score = 0
                        for k, v in v_dict.items():
                            k_lower = k.lower()
                            score = difflib.SequenceMatcher(None, ai_venue_clean, k_lower).ratio()
                            
                            # if one is a substring of another, weight the score by proportional coverage
                            if k_lower in ai_venue_clean:
                                score = max(score, len(k_lower) / max(len(ai_venue_clean), 1))
                            elif ai_venue_clean in k_lower:
                                score = max(score, len(ai_venue_clean) / max(len(k_lower), 1))
                                
                            if score > best_score:
                                best_score = score
                                best_match = v
                                
                        if best_score > 0.55:
                            matched = best_match
                        
                    if matched:
                        result["ccf_partition"] = matched.get("ccf", "")
                        result["jcr_partition"] = matched.get("jcr", "")
                        result["core_type"] = matched.get("core", "")
                except Exception as e:
                    print(f"Venue dict error: {e}")
                
        return result
    except Exception as e:
        print(f"Error analyzing paper {pdf_path}: {e}")
        return {"en_title": "Unknown Title", "title": "Unknown Title"}
