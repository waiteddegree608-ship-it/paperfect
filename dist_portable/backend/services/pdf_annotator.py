import os
import glob
import argparse
import fitz  # PyMuPDF
import re
import json
from openai import OpenAI
from dotenv import load_dotenv

def load_config():
    # Load .env from root directory (ddl)
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env")
    load_dotenv(env_path)

load_config()

# 我们优先使用 ANNOTATOR_API_KEY，如果没有则回退到 CHAT_API_KEY
API_KEY = os.environ.get("ANNOTATOR_API_KEY") or os.environ.get("CHAT_API_KEY", "")

BASE_URL = os.environ.get("ANNOTATOR_API_URL") or os.environ.get("CHAT_API_URL", "https://api.siliconflow.cn/v1")
if not BASE_URL: BASE_URL = "https://api.siliconflow.cn/v1"

MODEL_NAME = os.environ.get("ANNOTATOR_MODEL") or os.environ.get("CHAT_MODEL", "Qwen/Qwen2.5-72B-Instruct")
if not MODEL_NAME: MODEL_NAME = "Qwen/Qwen2.5-72B-Instruct"

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

def get_ai_annotations_for_page(client, page_text, md_content, page_num):
    sys_prompt = f"""
# Role
你是一个顶级的 AI 学术阅读助教。你的任务是基于我提供的【中文深度解析报告】，在原始的英文 PDF 论文文本中主动寻找需要批注的锚点，提取原文精确字符串，并给出具体的批注方案。

# Annotation Guidelines (标注规范)
请仔细阅读【中文深度解析报告】，并严格对照当前页面的英文原文，按照以下规范进行批注：
1. 🔴 波浪线 (squiggly) + 红色 (red)：【现有缺陷、挑战、问题】（对应解析中提到的当前痛点与挑战、前人工作的局限性）
2. 🟡 高亮 (highlight) + 黄色 (yellow)：【核心创新点、重大贡献】（对应解析中本文提出的主要动机、核心贡献与关键创新）
3. 🔵 下划线 (underline) + 蓝色 (blue)：【重要方法、网络模块、数据集与指标】（对应解析中介绍的具体结构设计、特有模块名、评测指标数据等客观事实）
4. 📝 便条 (sticky_note) + 绿色 (green)：【全局总结或深度剖析】（用于较长的总结性观点或是对某个大段落的核心概括。将其挂载在相关段首、或是整体架构说明旁）

# Constraints & JSON Format
- target_text 必须**一字不差**地来源于下面提供的当前页纯文本 (Current Page Text)！截取最具标志性的 5 到 15 个连续英文单词，以此确保能在页面中被无误地检索定位。
- 【极其重要】你**绝对不能**仅仅因为当前页内容较为细节或没有在“深度解析报告”里大篇幅提及，就放弃批注！无论如何，请为当前页寻找**至少 1-3 处值得注意的句子**进行批注，哪怕仅仅是解释一个算法步骤、参数设置或是给相关工作分类。除非该页完全是纯参考文献列表，否则严禁返回空数组 []！
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

    messages = [
        {"role": "system", "content": sys_prompt},
        {"role": "user", "content": f"这是第 {page_num} 页提取出来的纯文本，请找出需要标注的地方并输出合法的JSON数组：\n\n{page_text}"}
    ]

    try:
        print(f"[{MODEL_NAME}] 正在请求第 {page_num} 页的标注数据...", flush=True)
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.2, 
            max_tokens=2048,
            response_format={"type": "json_object"} if "72b" in MODEL_NAME.lower() else None # 强化 JSON 输出
        )
        
        reply = response.choices[0].message.content.strip()
        
        if "```json" in reply:
            reply = reply.split("```json")[-1].split("```")[0].strip()
        elif "```" in reply:
             reply = reply.split("```")[-1].split("```")[0].strip()
             
        try:
            annotations = json.loads(reply)
            # 有时模型会包装在一个 key 里比如 {"annotations": [...]}
            if isinstance(annotations, dict):
                for k, v in annotations.items():
                    if isinstance(v, list):
                        annotations = v
                        break
        except json.JSONDecodeError:
            print(f"第 {page_num} 页 JSON 解析失败。大模型原始返回:\n{reply}", flush=True)
            return []

        if not isinstance(annotations, list):
            return []
        return annotations

    except Exception as e:
        print(f"解析第 {page_num} 页大模型返回结果时出错: {e}", flush=True)
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
    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)
    md_content = load_markdown(md_path)
    
    doc = fitz.open(pdf_path)
    max_pages = len(doc)
    print(f"PDF 共 {max_pages} 页，全书批注流程已启动！", flush=True)

    # 逐页处理
    for page_num in range(max_pages):
        page = doc[page_num]
        page_text = page.get_text("text")
        page_text = re.sub(r'\n{3,}', '\n\n', page_text)
        
        if len(page_text.strip()) < 50:
            print(f"第 {page_num + 1} 页文字过少，大概全是图片，跳过。", flush=True)
            continue
            
        annotations = get_ai_annotations_for_page(client, page_text, md_content, page_num + 1)
        
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
                
                if annot_type == "highlight":
                    highlight = page.add_highlight_annot(text_instances)
                    highlight.set_colors(stroke=color_rgb)
                    if note_content: 
                        highlight.set_info(title="AI 助教", content=note_content)
                    highlight.update()
                    
                elif annot_type == "underline":
                    underline = page.add_underline_annot(text_instances)
                    underline.set_colors(stroke=color_rgb)
                    if note_content:
                        underline.set_info(title="AI 助教", content=note_content)
                    underline.update()
                    
                elif annot_type == "squiggly":
                    squiggly = page.add_squiggly_annot(text_instances)
                    squiggly.set_colors(stroke=color_rgb)
                    if note_content:
                        squiggly.set_info(title="AI 助教", content=note_content)
                    squiggly.update()
                    
                elif annot_type == "sticky_note":
                    rect = text_instances[0]
                    point = fitz.Point(rect.x0, rect.y0)
                    note = page.add_text_annot(point, note_content, icon="Note")
                    note.set_colors(stroke=color_rgb)
                    note.set_info(title="深度总结")
                    note.update()
                    
                success_count += 1
            else:
                print(f"[警告] 第 {page_num + 1} 页未定位到矩形: '{target_text[:30]}...'", flush=True)

        print(f"第 {page_num + 1} 页批注渲染: {success_count}/{len(annotations)}", flush=True)
        
        # 实时保存（防崩溃，渐进式输出）
        doc.save(output_pdf_path)

    doc.close()
    print(f"\n处理完成。批注文件已安全保存为：\n{output_pdf_path}\n=======================================================\n", flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI PDF Annotator Service")
    parser.add_argument("dir", help="Target reading directory containing the PDF and MD files")
    args = parser.parse_args()
    apply_annotations_to_pdf(args.dir)
