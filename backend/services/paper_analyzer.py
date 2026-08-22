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
            
        url = f"https://api.semanticscholar.org/graph/v1/paper/{clean_id}?fields=title,venue,abstract,year,authors,externalIds,publicationVenue,publicationDate"
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
        url = f"https://api.crossref.org/works?query.title={q}&select=title,container-title,event,published-print,published-online,issued&rows=1"
        response = requests.get(
            url,
            timeout=8,
            headers={"User-Agent": "Paperfect/1.0 (mailto:paperfect@local)"},
        )
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
                    year = ""
                    for key in ("published-print", "published-online", "issued"):
                        parts = ((item.get(key) or {}).get("date-parts") or [[]])
                        if parts and parts[0]:
                            year = str(parts[0][0])
                            break
                    return {"venue": venue, "year": year}
    except Exception as e:
        print(f"Crossref API title search error for {title}: {e}")
    return None

def extract_local_fallback_abstract(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for i in range(min(2, len(doc))):
            text += doc[i].get_text("text")
        doc.close()
        
        match = re.search(r'(?i)\b(?:abstract|摘要)\b(.*)', text, re.DOTALL)
        if match:
            abstract_text = match.group(1).strip()
            intro_match = re.search(r'(?i)\b(?:1\.?\s+)?introduction\b', abstract_text)
            if intro_match:
                abstract_text = abstract_text[:intro_match.start()].strip()
            abstract_text = re.sub(r'\s+', ' ', abstract_text)
            if len(abstract_text) > 50:
                return abstract_text[:1200]
    except Exception:
        pass
    return ""

def _extract_json_object(text: str):
    if not text:
        raise ValueError("empty model output")
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text, flags=re.DOTALL)
    cleaned = re.sub(r"<think>[\s\S]*", "", cleaned).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned.strip())
    except Exception:
        pass
    start = cleaned.find("{")
    if start < 0:
        raise ValueError("no JSON object in model output")
    depth = 0
    in_str = False
    esc = False
    for i, ch in enumerate(cleaned[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return json.loads(cleaned[start : i + 1])
    raise ValueError("unterminated JSON object")


def apply_analysis_to_document(db, doc, analysis):
    """Write analyzer result onto a Document. Metadata is committed even if tags collide.

    When `analysis` is a filename-derived stub (see `_is_fallback` in analyze_paper,
    produced when there is no API key or every LLM attempt failed), we only ever
    fill in fields that are currently empty on `doc` -- we never let a failed
    retry/re-heal downgrade previously-good metadata (title/venue/abstract/...)
    back to a bare filename or "Unknown".
    """
    from backend.models.database import Tag
    if not doc or not analysis:
        return
    is_fallback = bool(analysis.get("_is_fallback"))

    def _blocked(current):
        # In fallback mode, skip fields that already hold real data.
        return is_fallback and bool(current)

    en_title = analysis.get("en_title")
    if en_title and en_title != "Unknown Title" and not _blocked(doc.title):
        doc.title = en_title
    if analysis.get("zh_title") and not _blocked(doc.zh_title):
        doc.zh_title = analysis.get("zh_title")
    if analysis.get("venue") and not _blocked(doc.venue):
        doc.venue = analysis.get("venue")
    if analysis.get("paper_type") and not _blocked(doc.paper_type):
        doc.paper_type = analysis.get("paper_type")
    if analysis.get("jcr_partition") is not None and not _blocked(doc.jcr_partition):
        doc.jcr_partition = analysis.get("jcr_partition") or ""
    if analysis.get("ccf_partition") is not None and not _blocked(doc.ccf_partition):
        doc.ccf_partition = analysis.get("ccf_partition") or ""
    if analysis.get("core_type") is not None and not _blocked(doc.core_type):
        doc.core_type = analysis.get("core_type") or ""
    f_val = analysis.get("research_field", "")
    if f_val and not _blocked(doc.research_field):
        doc.research_field = json.dumps(f_val, ensure_ascii=False) if isinstance(f_val, dict) else str(f_val)
    d_val = analysis.get("research_direction", "")
    if d_val and not _blocked(doc.research_direction):
        doc.research_direction = json.dumps(d_val, ensure_ascii=False) if isinstance(d_val, dict) else str(d_val)
    if analysis.get("abstract") and not _blocked(doc.abstract):
        doc.abstract = analysis.get("abstract")
    if analysis.get("en_abstract") and not _blocked(doc.en_abstract):
        doc.en_abstract = analysis.get("en_abstract")
    if analysis.get("en_keywords") is not None and not _blocked(doc.en_keywords):
        doc.en_keywords = json.dumps(analysis.get("en_keywords") or [], ensure_ascii=False)
    if analysis.get("authors") is not None and not _blocked(doc.authors):
        doc.authors = json.dumps(analysis.get("authors") or [], ensure_ascii=False)
    if analysis.get("year") and not _blocked(doc.year):
        doc.year = str(analysis.get("year"))
    if analysis.get("doi") and not _blocked(doc.doi):
        doc.doi = analysis.get("doi")
    db.commit()

    seen = set()
    for kw in analysis.get("zh_keywords") or []:
        kw = (kw or "").strip()
        if not kw or kw in seen:
            continue
        seen.add(kw)
        tag = db.query(Tag).filter(Tag.name == kw, Tag.category == "Keywords").first()
        if not tag:
            tag = Tag(name=kw, category="Keywords")
            db.add(tag)
            db.flush()
        if tag not in doc.tags:
            doc.tags.append(tag)
    try:
        db.commit()
    except Exception as e:
        print(f"[Analyze] tag attach skipped ({e})", flush=True)
        db.rollback()


def _weak_venue(name: str) -> bool:
    s = (name or "").strip().lower()
    return (not s) or s in ("unknown", "arxiv", "preprint", "arxiv preprint") or "arxiv.org" in s


def _year_from_text(text: str) -> str:
    years = [int(y) for y in re.findall(r"\b((?:19|20)\d{2})\b", text or "")]
    years = [y for y in years if 1990 <= y <= 2035]
    if not years:
        return ""
    return str(max(years))


def _enrich_publication_meta(result: dict, page_text: str, identifier, s2_metadata, arxiv_metadata):
    """Prefer conference/journal + year over a bare 'arxiv' label; fill CCF."""
    from backend.services.venue_matcher import match_venue, scan_ccf_in_text

    candidates = []
    if s2_metadata:
        pv = s2_metadata.get("publicationVenue") or {}
        if isinstance(pv, dict) and pv.get("name"):
            candidates.append(pv.get("name"))
        if s2_metadata.get("venue"):
            candidates.append(s2_metadata.get("venue"))
        if s2_metadata.get("year") and not result.get("year"):
            result["year"] = str(s2_metadata.get("year"))
        names = []
        for a in s2_metadata.get("authors") or []:
            if isinstance(a, dict) and a.get("name"):
                names.append(a["name"])
            elif isinstance(a, str) and a.strip():
                names.append(a.strip())
        if names and not result.get("authors"):
            result["authors"] = names
        if s2_metadata.get("title"):
            cur = (result.get("en_title") or "").strip()
            if (not cur) or cur.lower().endswith(".pdf") or len(cur) < 16:
                result["en_title"] = s2_metadata["title"]
        if s2_metadata.get("abstract") and not result.get("en_abstract"):
            result["en_abstract"] = s2_metadata["abstract"]
    if arxiv_metadata:
        if arxiv_metadata.get("year") and not result.get("year"):
            result["year"] = str(arxiv_metadata["year"])
        if arxiv_metadata.get("venue_hints"):
            candidates.append(arxiv_metadata["venue_hints"])
        if arxiv_metadata.get("title"):
            cur = (result.get("en_title") or "").strip()
            if (not cur) or cur.lower().endswith(".pdf") or len(cur) < 16:
                result["en_title"] = arxiv_metadata["title"]
        if arxiv_metadata.get("abstract") and not result.get("en_abstract"):
            result["en_abstract"] = arxiv_metadata["abstract"]
    if result.get("venue"):
        candidates.append(result.get("venue"))
    candidates.append((page_text or "")[:3000])

    blob = " \n ".join(str(c) for c in candidates if c)
    ccf, jcr, acr = scan_ccf_in_text(blob)
    if not acr:
        for c in candidates:
            ccf, jcr, acr = match_venue(str(c or ""))
            if acr:
                break

    if _weak_venue(result.get("venue") or "") and result.get("en_title"):
        xref = fetch_crossref_metadata_by_title(result["en_title"])
        if xref:
            if xref.get("year") and not result.get("year"):
                result["year"] = str(xref["year"])
            xv = xref.get("venue") or ""
            if xv and not _weak_venue(xv):
                candidates.insert(0, xv)
                c2, j2, a2 = scan_ccf_in_text(xv) if not acr else (ccf, jcr, acr)
                if a2:
                    ccf, jcr, acr = c2, j2, a2
                elif not acr:
                    result["venue"] = xv

    if not result.get("year"):
        result["year"] = _year_from_text(blob) or _year_from_text(page_text or "")

    result["core_type"] = result.get("core_type") or ""
    if acr:
        year = (result.get("year") or "").strip()
        result["venue"] = f"{acr} {year}".strip() if year else acr
        result["ccf_partition"] = ccf
        result["jcr_partition"] = jcr
        result["matched_venue"] = acr
        print(f"[Venue] resolved → {result['venue']} CCF={ccf or '-'} JCR={jcr or '-'}", flush=True)
    else:
        if _weak_venue(result.get("venue") or ""):
            result["venue"] = "arXiv preprint" if (identifier or "").startswith("ARXIV:") else (result.get("venue") or "Unknown")
        ccf, jcr, matched = match_venue(result.get("venue") or "")
        result["ccf_partition"] = ccf
        result["jcr_partition"] = jcr
        result["matched_venue"] = matched
        if matched:
            print(f"[Venue] '{result.get('venue')}' → {matched} CCF={ccf or '-'}", flush=True)


def analyze_paper(pdf_path: str):
    """
    Extract title, venue, abstract, and keywords from the first few pages of a PDF paper.
    """
    config = load_config()
    from backend.services.model_pick import pick_fast_text_model, extra_body_for_model, reasoning_max_tokens
    api_key = config.get("paper_api_key") or config.get("chat_api_key") or config.get("parse_api_key")
    if isinstance(api_key, list):
        api_key = api_key[0] if api_key else ""
    base_url = config.get("paper_api_url") or config.get("chat_api_url") or config.get("parse_api_url")
    model = pick_fast_text_model(config)
    
    local_abstract = extract_local_fallback_abstract(pdf_path)
    title_fallback = os.path.basename(pdf_path).replace(".pdf", "")
    
    fallback_result = {
        "en_title": title_fallback, 
        "zh_title": title_fallback,
        "venue": "Unknown", 
        "abstract": local_abstract, 
        "en_abstract": local_abstract,
        "keywords": [],
        "zh_keywords": [],
        "en_keywords": [],
        # Marks this as a low-quality stub (filename-derived) result so callers
        # (see apply_analysis_to_document) never let it clobber previously-good
        # metadata on a re-heal/retry of an already-analyzed document.
        "_is_fallback": True,
    }
    
    if not api_key:
        print("No API key available for paper analysis. Using local extraction fallback.")
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
        arxiv_metadata = None
        
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
                
        print(f"[Analyze] model={model} url={base_url}", flush=True)
        client = OpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
        
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
        11. Extract author names into `authors` (array of strings, original order, family-name last if possible). Use Prior Knowledge if provided.
        12. Extract publication year as `year` (4-digit string). Use Prior Knowledge if provided.
        13. Extract DOI as `doi` if present (e.g. "10.xxxx/..."), else empty string.
        
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
            "research_direction": {{"zh": "微观研究方向", "en": "Micro research direction"}},
            "authors": ["Alice Example", "Bob Example"],
            "year": "2024",
            "doi": ""
        }}
        
        Text:
        {text[:4000]}
        """
        
        extra = extra_body_for_model(model)
        max_tokens = reasoning_max_tokens(2048, model)
        content = ""
        result = None
        last_err = None
        for attempt in range(2):
            kwargs = dict(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=max_tokens,
            )
            # Only try the CoT-disable hint once; some gateways reject unknown
            # extra_body fields for certain models, so drop it after a failure.
            if extra and attempt == 0:
                kwargs["extra_body"] = extra
            try:
                response = client.chat.completions.create(**kwargs)
                content = (response.choices[0].message.content or "").strip()
                result = _extract_json_object(content)
                break
            except Exception as e:
                last_err = e
                print(f"[Analyze] JSON/LLM attempt {attempt+1} failed: {e}", flush=True)
                prompt = prompt + "\n\nReturn ONLY a single JSON object. No markdown."
        if result is None:
            raise last_err or ValueError("analyze_paper produced no JSON")
        
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
        for k in ["en_title", "zh_title", "venue", "paper_type", "en_abstract", "abstract", "research_field", "research_direction", "year", "doi"]:
            if k not in result:
                result[k] = ""
        for k in ["en_keywords", "zh_keywords", "keywords", "authors"]:
            if k not in result:
                result[k] = []
        if isinstance(result.get("authors"), str):
            result["authors"] = [a.strip() for a in re.split(r"[,;]| and ", result["authors"]) if a.strip()]
        if identifier and identifier.startswith("DOI:"):
            result["doi"] = result.get("doi") or identifier.replace("DOI:", "").strip()

        _enrich_publication_meta(result, text, identifier, s2_metadata, arxiv_metadata)
        return result
    except Exception as e:
        print(f"Error analyzing paper {pdf_path}: {e}")
        try:
            from backend.services.venue_matcher import match_venue
            ccf, jcr, matched = match_venue(fallback_result.get("venue") or "")
            fallback_result["ccf_partition"] = ccf
            fallback_result["jcr_partition"] = jcr
            fallback_result["matched_venue"] = matched
        except Exception:
            pass
        return fallback_result
