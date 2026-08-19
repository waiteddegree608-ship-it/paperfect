import os
import glob
import argparse
import fitz  # PyMuPDF
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from backend.core.config import load_config

cfg = load_config()

from dotenv import dotenv_values
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
env_dict = dotenv_values(env_path)

def get_keys_list():
    raw_val = env_dict.get("ANNOTATOR_API_KEY") or env_dict.get("CHAT_API_KEY") or env_dict.get("PARSE_API_KEY") or ""
    raw_val = raw_val.strip().strip("'").strip('"')
    if not raw_val:
        return []
    return [k.strip().strip("'").strip('"') for k in raw_val.split(",") if k.strip()]

API_KEYS = get_keys_list()
import random
API_KEY = random.choice(API_KEYS) if API_KEYS else ""

BASE_URL = cfg.get("annotator_api_url") or cfg.get("chat_api_url") or "https://opencode.ai/zen/go/v1"
if not BASE_URL: BASE_URL = "https://opencode.ai/zen/go/v1"

from backend.services.model_pick import pick_fast_text_model, extra_body_for_model, reasoning_max_tokens, strip_think

MODEL_NAME = pick_fast_text_model(cfg)
if not MODEL_NAME:
    MODEL_NAME = "gemini-2.5-flash"

# ================= 预设颜色 =================
COLOR_MAP = {
    "yellow": (1.0, 1.0, 0.0),    # 高亮：核心创新点
    "red": (1.0, 0.0, 0.0),       # 波浪线：缺陷挑战
    "blue": (0.0, 0.0, 1.0),      # 下划线：重要方法/指标
    "green": (0.0, 1.0, 0.0)      # 便签：总结解析
}

def load_markdown(md_path):
    with open(md_path, "r", encoding="utf-8") as f:
        return f.read()

def _extract_json_array(text):
    """Robustly extract a JSON array from LLM response text."""
    text = text.strip()
    # Method 1: direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for v in obj.values():
                if isinstance(v, list):
                    return v
        return None
    except json.JSONDecodeError:
        pass

    # Method 2: extract from ```json ... ``` fenced blocks
    import re as _re
    pattern = r'```(?:json)?\s*([\[\{].*?[\]\}])\s*```'
    matches = _re.findall(pattern, text, _re.DOTALL)
    for match in matches:
        try:
            obj = json.loads(match)
            if isinstance(obj, list):
                return obj
            if isinstance(obj, dict):
                for v in obj.values():
                    if isinstance(v, list):
                        return v
        except json.JSONDecodeError:
            continue

    # Method 3: find any JSON array in the text
    pattern2 = r'(\[\s*\{.*?\}\s*\])'
    matches2 = _re.findall(pattern2, text, _re.DOTALL)
    for match in matches2:
        try:
            obj = json.loads(match)
            if isinstance(obj, list):
                return obj
        except json.JSONDecodeError:
            continue

    return None


def _kb_excerpt(md_content, max_chars=4000):
    if not md_content:
        return ""
    if len(md_content) <= max_chars:
        return md_content
    return md_content[:max_chars] + "\n\n...(report truncated for this page)..."


def _looks_refs_page(text: str, page_num: int, page_count: int) -> bool:
    head = (text or "")[:700]
    if re.search(r"^\s*(references|bibliography|参考文献)\s*$", head, re.I | re.M):
        return True
    if page_num >= max(8, int(page_count * 0.72)) and len(re.findall(r"\[\d{1,3}\]", text or "")) >= 12:
        return True
    return False


def _chunk(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def get_ai_annotations_for_pages(client, batch, md_content, lang="zh", max_retries=1):
    """One request for several pages. Returns {page_num_1based: [anns]}."""
    md_content = _kb_excerpt(md_content)
    pages_blob = []
    for pno, ptext in batch:
        pages_blob.append(f"### PAGE {pno}\n{(ptext or '')[:1600]}")
    joined = "\n\n".join(pages_blob)
    if lang == "en":
        sys_prompt = (
            "Annotate an academic PDF. Use the short report. "
            "For EACH page output 1-3 anchors. target_text = exact 5-12 words from that page. "
            "Types: highlight/yellow = contribution; squiggly/red = limitation; "
            "underline/blue = method/metric; sticky_note/green = summary. "
            "Output ONLY JSON: {\"pages\":{\"3\":[{\"target_text\":\"...\",\"annotation_type\":\"highlight\","
            "\"color\":\"yellow\",\"note_content\":\"...\"}]}}"
        )
        user_msg = f"Report:\n{md_content}\n\nPages:\n{joined}"
    else:
        sys_prompt = (
            "给学术PDF做页内批注。结合短报告，每一页找1-3处锚点。"
            "target_text 必须是该页原文连续5-12个英文词。"
            "类型：highlight/yellow=贡献；squiggly/red=缺陷；underline/blue=方法指标；sticky_note/green=总结。"
            "只输出JSON：{\"pages\":{\"3\":[{\"target_text\":\"...\",\"annotation_type\":\"highlight\","
            "\"color\":\"yellow\",\"note_content\":\"中文点评\"}]}}"
        )
        user_msg = f"报告：\n{md_content}\n\n各页：\n{joined}"

    extra = extra_body_for_model(MODEL_NAME)
    max_tokens = reasoning_max_tokens(1400, MODEL_NAME)
    for attempt in range(max_retries + 1):
        try:
            print(f"[{MODEL_NAME}] batch pages {[p for p, _ in batch]} try={attempt}", flush=True)
            kwargs = dict(
                model=MODEL_NAME,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=0.2,
                max_tokens=max_tokens,
            )
            if extra and attempt == 0:
                kwargs["extra_body"] = extra
            response = client.chat.completions.create(**kwargs)
            reply = (response.choices[0].message.content or "").strip()
            reply = strip_think(reply)
            data = None
            try:
                data = json.loads(reply)
            except Exception:
                m = re.search(r"\{[\s\S]*\}", reply)
                if m:
                    try:
                        data = json.loads(m.group(0))
                    except Exception:
                        data = None
            out = {}
            pages = (data or {}).get("pages") if isinstance(data, dict) else None
            if isinstance(pages, dict):
                for k, v in pages.items():
                    try:
                        out[int(k)] = v if isinstance(v, list) else []
                    except Exception:
                        continue
            if out:
                return out
            arr = _extract_json_array(reply)
            if arr:
                out[batch[0][0]] = arr
                return out
        except Exception as e:
            print(f"  [ERROR] annotate batch failed: {e}", flush=True)
            if attempt < max_retries:
                _rate_limit_sleep(e)
                continue
    return {}


def _rate_limit_sleep(err):
    import time
    err_str = str(err)
    sleep_time = 4.0
    match = re.search(r'[Pp]lease retry in ([\d\.]+)s', err_str)
    if match:
        try:
            sleep_time = float(match.group(1)) + 1.0
        except ValueError:
            pass
    else:
        match_after = re.search(r'[Pp]lease retry after (\d+)s', err_str)
        if match_after:
            try:
                sleep_time = float(match_after.group(1)) + 1.0
            except ValueError:
                pass
    time.sleep(sleep_time)


def get_ai_annotations_for_page(client, page_text, md_content, page_num, max_retries=2, lang="zh"):
    md_content = _kb_excerpt(md_content)
    if lang == "en":
        sys_prompt = f"""
# Role
You are a top-tier AI academic reading assistant. Based on the provided deep analysis report, you actively find annotation anchors in the original English PDF text, extract exact character strings, and provide specific annotation plans.

# Annotation Guidelines
Carefully read the analysis report and strictly compare it with the current page's English text. Follow these annotation rules:
1. Squiggly line (squiggly) + Red (red): Existing defects, challenges, limitations (pain points, prior work limitations)
2. Highlight (highlight) + Yellow (yellow): Core innovations, major contributions (main motivation, key contributions)
3. Underline (underline) + Blue (blue): Important methods, modules, datasets, metrics (specific architectural designs, module names, evaluation data)
4. Sticky note (sticky_note) + Green (green): Overall summary or deep analysis (longer summarizing insights or core paragraph summaries)

# Constraints & JSON Format
- target_text MUST be an exact, verbatim substring from the Current Page Text below! Extract the most distinctive 5 to 15 consecutive English words to ensure reliable matching.
- CRITICAL: Do NOT skip annotation just because the page content is detailed or not extensively covered in the analysis report. Find AT LEAST 1-3 noteworthy sentences per page, even if just explaining an algorithm step, parameter setting, or related work classification. Unless the page is purely a reference list, NEVER return an empty array []!
- Output MUST be a valid JSON array only. Example format:
[
  {{
    "target_text": "Extract exact words from the provided page text here...",
    "annotation_type": "highlight",
    "color": "yellow",
    "note_content": "Your concise English annotation combining insights from the analysis report."
  }}
]

====== Deep Analysis Report ======
{md_content}
"""
        user_msg = f"This is the plain text extracted from page {page_num}. Please find places to annotate and output a valid JSON array:\n\n{page_text}"
    else:
        sys_prompt = f"""
# Role
你是一个顶级的 AI 学术阅读助教。你的任务是基于我提供的【中文深度解析报告】，在原始的英文 PDF 论文文本中主动寻找需要批注的锚点，提取原文精确字符串，并给出具体的批注方案。

# Annotation Guidelines
请仔细阅读【中文深度解析报告】，并严格对照当前页面的英文原文，按照以下规范进行批注：
1. 波浪线 (squiggly) + 红色 (red)：【现有缺陷、挑战、问题】（对应解析中提到的当前痛点与挑战、前人工作的局限性）
2. 高亮 (highlight) + 黄色 (yellow)：【核心创新点、重大贡献】（对应解析中本文提出的主要动机、核心贡献与关键创新）
3. 下划线 (underline) + 蓝色 (blue)：【重要方法、网络模块、数据集与指标】（对应解析中介绍的具体结构设计、特有模块名、评测指标数据等客观事实）
4. 便条 (sticky_note) + 绿色 (green)：【全局总结或深度剖析】（用于较长的总结性观点或是对某个大段落的核心概括。将其挂载在相关段首、或是整体架构说明旁）

# Constraints & JSON Format
- target_text 必须**一字不差**地来源于下面提供的当前页纯文本 (Current Page Text)！截取最具标志性的 5 到 15 个连续英文单词，以此确保能在页面中被无误地检索定位。
- 【极其重要】你**绝对不能**仅仅因为当前页内容较为细节或没有在"深度解析报告"里大篇幅提及，就放弃批注！无论如何，请为当前页寻找**至少 1-3 处值得注意的句子**进行批注，哪怕仅仅是解释一个算法步骤、参数设置或是给相关工作分类。除非该页完全是纯参考文献列表，否则严禁返回空数组 []！
- 你的输出必须且仅仅是合法的 JSON 数组，直接输出 JSON。示例格式如下：
[
  {{
    "target_text": "Extract exact words from the provided page text here...",
    "annotation_type": "highlight",
    "color": "yellow",
    "note_content": "【中文注解】请在这里填入结合解析文件而浓缩出的精华点评。"
  }}
]

======【中文深度解析报告】======
{md_content}
"""
        user_msg = f"这是第 {page_num} 页提取出来的纯文本，请找出需要标注的地方并输出合法的JSON数组：\n\n{page_text}"

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": user_msg}
    ]


    extra = extra_body_for_model(MODEL_NAME)
    max_tokens = reasoning_max_tokens(2048, MODEL_NAME)
    for attempt in range(max_retries + 1):
        try:
            retry_label = f" (retry {attempt})" if attempt > 0 else ""
            print(f"[{MODEL_NAME}] Requesting annotations for page {page_num}...{retry_label}", flush=True)
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                temperature=0.2,
                max_tokens=max_tokens,
                # Only try the CoT-disable hint once; drop it after a failure in
                # case the gateway rejects the extra_body field for this model.
                **({"extra_body": extra} if (extra and attempt == 0) else {}),
            )

            reply = strip_think((response.choices[0].message.content or "").strip())
            annotations = _extract_json_array(reply)
            
            if annotations is None:
                print(f"  [WARN] Page {page_num}: JSON extraction failed. Reply preview: {reply[:200]}", flush=True)
                if attempt < max_retries:
                    import time; time.sleep(2)
                    continue
                return []
            
            print(f"  Page {page_num}: {len(annotations)} annotations extracted", flush=True)
            return annotations

        except Exception as e:
            print(f"  [ERROR] Page {page_num} API call failed: {e}", flush=True)
            if attempt < max_retries:
                if 'API_KEYS' in globals() and API_KEYS:
                    import random
                    client.api_key = random.choice(API_KEYS)
                    print(f"  [Rotated Key] Rotated API key to: ...{client.api_key[-6:]}", flush=True)
                _rate_limit_sleep(e)
                continue
            return []

def apply_annotations_to_pdf(directory_path):
    print(f"\n=======================================================", flush=True)
    print(f"开始处理目录: {directory_path}", flush=True)
    
    if not os.path.exists(directory_path):
        print(f"[错误] 找不到目录: {directory_path}", flush=True)
        return

    # 智能寻找 PDF 和 MD 文件
    pdf_files = [f for f in glob.glob(os.path.join(directory_path, "*.pdf")) if "annotated" not in f]
    md_files = glob.glob(os.path.join(directory_path, "*.md"))

    if not pdf_files:
        print(f"[错误] 目录下找不到源 PDF 文件", flush=True)
        return
    if not md_files:
        print(f"[错误] 目录下找不到对应的 MD 解析文件", flush=True)
        return

    pdf_path = pdf_files[0]
    md_path = md_files[0]
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_pdf_path = os.path.join(directory_path, f"{pdf_name}_annotated.pdf")

    print(f"找到源 PDF: {pdf_path}", flush=True)
    print(f"找到解析文档: {md_path}", flush=True)
    print(f"输出目标路径: {output_pdf_path}", flush=True)

    # 初始化 OpenAI 客户端
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=90.0)
    md_content = load_markdown(md_path)
    
    # Auto-detect language of deep analysis report
    cjk_re = re.compile(r'[\u4e00-\u9fff]')
    lang = "en" if not cjk_re.search(md_content[:1500]) else "zh"
    print(f"Auto-detected report language: {lang}", flush=True)
    
    doc = fitz.open(pdf_path)
    max_pages = len(doc)
    body_end = max_pages
    try:
        from backend.services.pdf_body import detect_body_range
        info = detect_body_range(pdf_path)
        if info.get("confidence") == "heading" and info.get("body_end_page"):
            body_end = int(info["body_end_page"])
            print(f"正文截至第 {body_end} 页，跳过参考文献及之后。", flush=True)
    except Exception as e:
        print(f"[Annotate] body detect skipped: {e}", flush=True)
    print(f"PDF 共 {max_pages} 页，将批注 1–{body_end} 页。", flush=True)

    jobs = []
    for page_num in range(body_end):
        page = doc[page_num]
        page_text = page.get_text("text")
        page_text = re.sub(r'\n{3,}', '\n\n', page_text)
        if len(page_text.strip()) < 50:
            print(f"第 {page_num + 1} 页文字过少，大概全是图片，跳过。", flush=True)
            continue
        if _looks_refs_page(page_text, page_num + 1, max_pages):
            print(f"第 {page_num + 1} 页像参考文献，跳过。", flush=True)
            continue
        jobs.append((page_num + 1, page_text[:4500]))

    from concurrent.futures import ThreadPoolExecutor, as_completed
    workers = max(1, min(int(os.environ.get("ANNOTATE_CONCURRENCY", "50") or 50), len(jobs) or 1))
    print(f"并行批注 pages={len(jobs)} workers={workers} model={MODEL_NAME}", flush=True)

    def _one(job):
        pno, ptext = job
        local = OpenAI(api_key=API_KEY, base_url=BASE_URL, timeout=90.0)
        if API_KEYS:
            import random as _rnd
            local.api_key = _rnd.choice(API_KEYS)
        anns = get_ai_annotations_for_page(local, ptext, md_content, pno, lang=lang)
        return pno, anns or []

    page_anns = {}
    from backend.services.stage_progress import write_progress
    write_progress(None, 0, max(1, len(jobs)))
    finished = 0
    if jobs:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futs = [ex.submit(_one, j) for j in jobs]
            for fut in as_completed(futs):
                try:
                    pno, anns = fut.result()
                    page_anns[int(pno) - 1] = anns or []
                    finished += 1
                except Exception as e:
                    print(f"[Annotate] worker failed: {e}", flush=True)
                    finished += 1
                write_progress(None, min(finished, len(jobs)), max(1, len(jobs)))

    all_ai_annotations = []
    for page_num in range(body_end):
        page = doc[page_num]
        annotations = page_anns.get(page_num) or []
        success_count = 0
        for ann in annotations:
            target_text = ann.get("target_text", "")
            annot_type = ann.get("annotation_type", "")
            color_name = ann.get("color", "yellow")
            note_content = ann.get("note_content", "")
            
            if not target_text:
                continue
                
            text_instances = page.search_for(target_text)
            if not text_instances:
                fallback_text = " ".join(target_text.split()[:5])
                text_instances = page.search_for(fallback_text)
            
            if text_instances:
                color_rgb = COLOR_MAP.get(color_name, COLOR_MAP["yellow"])
                
                # Calculate percentage rects relative to page size
                rects_pct = []
                for r in text_instances:
                    rects_pct.append({
                        "left": (r.x0 / page.rect.width) * 100,
                        "top": (r.y0 / page.rect.height) * 100,
                        "width": ((r.x1 - r.x0) / page.rect.width) * 100,
                        "height": ((r.y1 - r.y0) / page.rect.height) * 100
                    })
                
                normalized_type = "highlight"
                if annot_type == "underline":
                    normalized_type = "underline"
                elif annot_type == "squiggly":
                    normalized_type = "squiggly"
                elif annot_type == "sticky_note":
                    normalized_type = "note"

                all_ai_annotations.append({
                    "id": f"ai_{page_num+1}_{success_count}_{len(all_ai_annotations)}",
                    "type": normalized_type,
                    "pageNumber": page_num + 1,
                    "text": target_text,
                    "rects": rects_pct,
                    "note_content": note_content or "",
                    "is_ai": True
                })

                if annot_type == "highlight":
                    highlight = page.add_highlight_annot(text_instances)
                    highlight.set_colors(stroke=color_rgb)
                    if note_content: 
                        title = "AI Assistant" if lang == "en" else "AI 助教"
                        highlight.set_info(title=title, content=note_content)
                    highlight.update()
                    
                elif annot_type == "underline":
                    underline = page.add_underline_annot(text_instances)
                    underline.set_colors(stroke=color_rgb)
                    if note_content:
                        title = "AI Assistant" if lang == "en" else "AI 助教"
                        underline.set_info(title=title, content=note_content)
                    underline.update()
                    
                elif annot_type == "squiggly":
                    squiggly = page.add_squiggly_annot(text_instances)
                    squiggly.set_colors(stroke=color_rgb)
                    if note_content:
                        title = "AI Assistant" if lang == "en" else "AI 助教"
                        squiggly.set_info(title=title, content=note_content)
                    squiggly.update()
                    
                elif annot_type == "sticky_note":
                    rect = text_instances[0]
                    point = fitz.Point(rect.x0, rect.y0)
                    note = page.add_text_annot(point, note_content, icon="Note")
                    note.set_colors(stroke=color_rgb)
                    title = "Summary" if lang == "en" else "深度总结"
                    note.set_info(title=title)
                    note.update()
                    
                success_count += 1
            else:
                print(f"[警告] 第 {page_num + 1} 页未定位到矩形: '{target_text[:30]}...'", flush=True)

        print(f"第 {page_num + 1} 页批注渲染: {success_count}/{len(annotations)}", flush=True)
        
        # 实时保存（防崩溃，渐进式输出）
        doc.save(output_pdf_path)

    doc.close()
    
    # Save annotations.json
    json_path = os.path.join(directory_path, "annotations.json")
    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(all_ai_annotations, f, ensure_ascii=False, indent=2)
        print(f"AI annotations metadata saved to: {json_path}", flush=True)
    except Exception as e:
        print(f"[错误] 写入 annotations.json 失败: {e}", flush=True)

    print(f"\n处理完成。批注文件已安全保存为：\n{output_pdf_path}\n=======================================================\n", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI PDF Annotator Service")
    parser.add_argument("dir", help="Target reading directory containing the PDF and MD files")
    args = parser.parse_args()
    apply_annotations_to_pdf(args.dir)
