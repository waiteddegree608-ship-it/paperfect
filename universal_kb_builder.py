import os
import re
import argparse
import random
import time
import base64
import queue
import json
import fitz  # PyMuPDF
from concurrent.futures import ThreadPoolExecutor, as_completed
from openai import OpenAI

def load_config():
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    print("[Warning] No config.json found! Using emergency defaults.")
    return {}

_CFG = load_config()
_raw_keys = _CFG.get("parse_api_key", [])

if isinstance(_raw_keys, str):
    API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]
else:
    API_KEYS = [k.strip() for k in _raw_keys if k.strip()]

if not API_KEYS:
    print("[Warning] No API keys loaded from config.json")
    API_KEYS = []

BASE_URL = _CFG.get("parse_api_url", "https://api.siliconflow.cn/v1")
MODEL_NAME = _CFG.get("parse_model", "Qwen/Qwen3-VL-235B-A22B-Thinking")

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def call_vl_api_iterative(client, image_path, previous_context, subject_name):
    base64_image = encode_image(image_path)
    
    # 根据教材名称动态注入角色和目标
    prompt = f"你是【{subject_name}】领域的专家。请基于【上文提取的内容】，对【当前图片】进行详细解析。\n" \
             "1. 提取当前图片中的所有核心文字、公式。\n" \
             "2. 如果有图表，请详细解释其变化的含义。\n" \
             "3. 输出为Markdown格式，不要重复上文中已提取过的内容，但要保持知识大纲的连续性。\n\n" \
             f"【上文提取的内容】: {previous_context[-2000:]}...\n"
             
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
            ],
        }
    ]

    retries = 10
    backoff = 2
    
    for attempt in range(retries):
        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
                max_tokens=4096
            )
            return response.choices[0].message.content
        except Exception as e:
            error_str = str(e)
            # 如果是速率限制 (TPM limit/429)，直接进入深度睡眠等待接口额度重置
            if "rate limit" in error_str.lower() or "tpm" in error_str.lower() or "429" in error_str:
                wait_time = 30 + (10 * attempt)
            else:
                wait_time = backoff * (1.5 ** attempt)
            
            log(f"API Warning on {os.path.basename(image_path)}. Retry in {int(wait_time)}s... (Details: {error_str[:50]}...)")
            time.sleep(wait_time)
            
    log(f"Critical Limit: Skipping {image_path} after max retries.")
    return "> [⚠️ 触发大模型速率限制，此页强制跳过解析，以保护主程序不中端跳出。]\n"

def process_folder_task(task_name, image_paths, md_dir, subject_name):
    log(f"Started task: {task_name} with {len(image_paths)} pages.")
    
    accumulated_knowledge = ""
    page_results = []
    
    for idx, img_path in enumerate(image_paths):
        log(f"[{task_name}] Processing image {idx+1}/{len(image_paths)}...")
        try:
            current_key = random.choice(API_KEYS)
            client = OpenAI(api_key=current_key, base_url=BASE_URL)
            
            result = call_vl_api_iterative(client, img_path, accumulated_knowledge, subject_name)
            
            page_results.append(f"### Page/Slide {idx+1}\n\n{result}\n")
            accumulated_knowledge += result + "\n"
            
            # 为了防止单个账号瞬间打爆 TPM 限额，页面间强制增加平滑冷却时间
            time.sleep(12)
            
        except Exception as e:
            log(f"[{task_name}] CRITICAL FAILURE on image {idx+1}: {e}")
            return False 
            
    out_path = os.path.join(md_dir, f"{task_name}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# {task_name}\n\n" + "\n---\n".join(page_results))
        
    log(f"Finished task: {task_name}")
    return True

def get_pdf_structure(filepath):
    doc = fitz.open(filepath)
    sections = {}
    
    # 动态支持多种层级结构的正则匹配（章节、Unit、Quiz等）
    markers = [
        r"(?i)^chapter\s*(\d+)",
        r"^第\s*([0-9一二三四五六七八九十百]+)\s*章",
        r"(?i)^unit\s*(\d+)",
        r"(?i)^part\s*(\d+)",
        r"(?i)^quiz\s*(\d+)",
        r"^测验\s*(\d+)"
    ]
    
    for i in range(len(doc)):
        text = doc[i].get_text("text").split('\n')
        for line in text[:20]: # 扫描前 20 行
            line = line.strip()
            if not line: continue
            
            found = False
            for marker in markers:
                match = re.search(marker, line)
                if match:
                    num = match.group(1)
                    
                    # 简单将中文数字映射（如果是复杂情况可能需要更强的库，但这里先直观保留）
                    if marker.startswith("^第"):
                        word_type = "Chapter"
                    elif "quiz" in marker or "测验" in marker:
                        word_type = "Quiz"
                    elif "unit" in marker:
                        word_type = "Unit"
                    else:
                        word_type = "Chapter"
                        
                    key = f"{word_type}_{num}"
                    if key not in sections:
                        sections[key] = i + 1
                        found = True
                    break
            if found:
                break
                
    total_pages = len(doc)
    
    # Fallback: 如果什么都没匹配到，则每隔15页强制分成一个 Chunk，防止大文件卡死
    if not sections:
        log("No structural markers found. Falling back to 15-page chunks.")
        for i in range(0, total_pages, 15):
             sections[f"Chunk_{(i//15)+1}"] = i + 1
             
    # 按页码升序排列
    sorted_sections = sorted(sections.items(), key=lambda x: x[1])
    return sorted_sections, total_pages

def extract_pdf_images(filepath, sorted_sections, total_pages, temp_dir):
    doc = fitz.open(filepath)
    tasks = {}
    
    for i, (name, start_page) in enumerate(sorted_sections):
        end_page = sorted_sections[i+1][1] - 1 if i < len(sorted_sections)-1 else total_pages
        
        p_dir = os.path.join(temp_dir, name)
        if not os.path.exists(p_dir): os.makedirs(p_dir)
        
        assets = []
        for p in range(start_page-1, end_page):
            if p >= total_pages: break
            path = os.path.join(p_dir, f"page_{p+1}.png")
            if not os.path.exists(path):
                doc[p].get_pixmap(matrix=fitz.Matrix(2,2)).save(path)
            assets.append(path)
        if assets:
            tasks[name] = assets
            
    return tasks

def main():
    parser = argparse.ArgumentParser(description="Universal PDF Knowledge Base Builder")
    parser.add_argument("pdf_path", help="Path to the target PDF file")
    args = parser.parse_args()
    
    pdf_path = os.path.abspath(args.pdf_path)
    if not os.path.exists(pdf_path):
        log(f"Error: File {pdf_path} not found.")
        return
        
    # 动态推导输出目录名称
    base_dir = os.path.dirname(pdf_path)
    pdf_name = os.path.splitext(os.path.basename(pdf_path))[0]
    
    # 数据库文件夹名与 PDF 同名
    output_dir = os.path.join(base_dir, pdf_name)
    temp_dir = os.path.join(output_dir, "temp_assets")
    md_dir = os.path.join(output_dir, "markdown_parts")
    
    for d in [output_dir, temp_dir, md_dir]:
        if not os.path.exists(d):
            os.makedirs(d)
            
    # 将教材名称作为 prompt 核心
    subject_name = pdf_name
    log(f"Starting Knowledge Base build for: {subject_name}")
    log(f"Workspace (Database): {output_dir}")
    
    # 1. 解析 PDF 结构并截取图片
    log("Scanning PDF structure...")
    sorted_sections, total_pages = get_pdf_structure(pdf_path)
    
    log(f"Found {len(sorted_sections)} sections. Extracting images...")
    tasks = extract_pdf_images(pdf_path, sorted_sections, total_pages, temp_dir)
    
    # 2. 初始化任务队列，支持断点续传
    task_keys = list(tasks.keys())
    
    # 让名称包含数字的 task 按照数字大小排序 (例如 Chapter_2 在 Chapter_10 之前)
    def natural_keys(text):
        return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]
    task_keys.sort(key=natural_keys)
    
    # 过滤掉已经拥有 .md 结果的任务
    todo_keys = [k for k in task_keys if not os.path.exists(os.path.join(md_dir, f"{k}.md"))]
    log(f"Total sections: {len(task_keys)}. Remaining to process: {len(todo_keys)}")
    
    if not todo_keys:
        log("All sections already processed!")
    else:
        task_queue = queue.Queue()
        for t in todo_keys:
            task_queue.put(t)
            
        def worker_loop(worker_id):
            log(f"Worker {worker_id} started.")
            while not task_queue.empty():
                try:
                    task_name = task_queue.get_nowait()
                except queue.Empty:
                    break
                    
                log(f"Worker {worker_id} picked up {task_name}")
                try:
                    success = process_folder_task(task_name, tasks[task_name], md_dir, subject_name)
                    if not success:
                        log(f"Worker {worker_id} failed on {task_name}.")
                except Exception as e:
                    log(f"Worker {worker_id} crashed on {task_name}: {e}")
                    
                task_queue.task_done()
                
        # 3. 释放线程池并运行
        num_workers = len(API_KEYS)
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(worker_loop, i) for i in range(num_workers)]
            for f in as_completed(futures):
                 pass
                 
    # 4. 融合最终结果文件
    log("Merging final Knowledge Base...")
    final_md_path = os.path.join(output_dir, f"{pdf_name}_KnowledgeBase.md")
    
    with open(final_md_path, "w", encoding="utf-8") as out_f:
        out_f.write(f"# {pdf_name} Knowledge Base\n\n")
        out_f.write("> Generated by Universal VL Knowledge Base Builder\n\n")
        
        for k in task_keys:
            part_md = os.path.join(md_dir, f"{k}.md")
            if os.path.exists(part_md):
                with open(part_md, "r", encoding="utf-8") as in_f:
                    out_f.write(in_f.read() + "\n\n")
                    
    log(f"All workflows completed! Final merged file: {final_md_path}")

if __name__ == "__main__":
    main()
