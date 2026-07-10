import os
import sys
import base64
from typing import List
import fitz  # PyMuPDF
from openai import OpenAI

class PaperReaderBot:
    def __init__(self, api_key: str = None, base_url: str = None, model_name: str = None):
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY") or os.environ.get("PARSE_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 API Key，请配置 env 或传入 key。")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url or "https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        self.model_name = model_name or "gemini-2.5-flash"
        
        try:
            from backend.core.config import load_config
            cfg = load_config()
            self.api_keys = cfg.get("parse_api_key") or [self.api_key]
        except Exception:
            self.api_keys = [self.api_key]


    def get_stage1_md(self, file_path: str, stage1_prompt: str) -> str:
        try:
            print(f"[{file_path}] 打开 PDF 并准备分析 ...")
            doc = fitz.open(file_path)
            try:
                # Check if we should use text-only extraction for DeepSeek models
                is_deepseek = "deepseek" in str(self.model_name).lower() or "deepseek" in str(self.client.base_url).lower()
                
                if is_deepseek:
                    print(f"[{file_path}] 检测到 DeepSeek 引擎，正在使用版面自适应算法提取文本 ...", file=sys.stderr, flush=True)
                    full_text = ""
                    for i, page in enumerate(doc):
                        full_text += f"\n--- Page {i+1} ---\n"
                        # Extract raw blocks
                        blocks = page.get_text("blocks")
                        # Filter text blocks (type 0)
                        blocks = [b for b in blocks if b[6] == 0]
                        
                        width = page.rect.width
                        height = page.rect.height
                        mid = width / 2
                        
                        left_col = []
                        right_col = []
                        full_width = []
                        
                        for b in blocks:
                            x0, y0, x1, y1, text, block_no, block_type = b
                            # Filter out headers and footers (within 45pt margins)
                            if y0 < 45 or y1 > height - 45:
                                continue
                            
                            # Categorize columns
                            if (x1 - x0) > width * 0.6:
                                full_width.append(b)
                            elif x1 <= mid or x0 < mid - 20:
                                left_col.append(b)
                            else:
                                right_col.append(b)
                                
                        # Sort by top-down y coordinate
                        full_width_sorted = sorted(full_width, key=lambda x: x[1])
                        left_col_sorted = sorted(left_col, key=lambda x: x[1])
                        right_col_sorted = sorted(right_col, key=lambda x: x[1])
                        
                        top_full = [b for b in full_width_sorted if b[1] < height / 3]
                        bottom_full = [b for b in full_width_sorted if b[1] >= height / 3]
                        
                        page_blocks = top_full + left_col_sorted + right_col_sorted + bottom_full
                        
                        for b in page_blocks:
                            b_text = b[4].strip()
                            b_text = b_text.replace("-\n", "").replace("- \n", "")
                            full_text += b_text + "\n\n"
                    
                    def _call_text(prompt_text):
                        messages = [
                            {
                                "role": "system",
                                "content": "You are a professional academic assistant. Read the extracted paper text and generate a structured Markdown report based on the user's requirements."
                            },
                            {
                                "role": "user",
                                "content": f"【论文文本内容】:\n{full_text}\n\n【生成要求】:\n{prompt_text}"
                            }
                        ]
                        
                        import sys
                        import time
                        
                        retries = 6
                        for attempt in range(retries):
                            try:
                                response = self.client.chat.completions.create(
                                    model=self.model_name,
                                    messages=messages,
                                    stream=True,
                                    timeout=60.0
                                )
                                
                                result_text = ""
                                for chunk in response:
                                    if chunk.choices and chunk.choices[0].delta.content:
                                        content = chunk.choices[0].delta.content
                                        result_text += content
                                        print(content, end="", file=sys.stderr, flush=True)
                                print("\n", file=sys.stderr, flush=True)
                                return result_text.strip()
                            except Exception as e:
                                print(f"\n[API Error] Attempt {attempt+1}/{retries} failed: {e}", file=sys.stderr, flush=True)
                                if attempt < retries - 1:
                                    if hasattr(self, "api_keys") and self.api_keys:
                                        try:
                                            idx = self.api_keys.index(self.client.api_key)
                                            next_idx = (idx + 1) % len(self.api_keys)
                                        except ValueError:
                                            next_idx = 0
                                        self.client.api_key = self.api_keys[next_idx]
                                        print(f"Rotated Parser API key to: ...{self.client.api_key[-6:]}", file=sys.stderr, flush=True)
                                    time.sleep(5)
                                else:
                                    raise RuntimeError(f"DeepSeek API failed after {retries} attempts: {e}")
                                    
                    print("=========== [阶段 1] 深度解读报告生成中 (DeepSeek Text Mode) ... ===========", file=sys.stderr, flush=True)
                    md_report = _call_text(stage1_prompt)
                    print("=> 成功生成 学术报告 Markdown！", file=sys.stderr, flush=True)
                    return md_report

                # Otherwise, fallback to the original VL image-based parsing
                print(f"[{file_path}] 正在切割并编码 PDF ...")
                base64_images = []
                for i, page in enumerate(doc):
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_data = pix.tobytes("jpeg")
                    b64_str = base64.b64encode(img_data).decode('utf-8')
                    base64_images.append(b64_str)
                
                def _call_vl(prompt_text):
                    content = []
                    for j, b64 in enumerate(base64_images):
                        content.append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{b64}",
                                "detail": "low"
                            }
                        })
                    content.append({"type": "text", "text": prompt_text})
                    
                    messages = [{"role": "user", "content": content}]
                    import sys
                    import time
                    import re
                    
                    retries = 6
                    for attempt in range(retries):
                        try:
                            response = self.client.chat.completions.create(
                                model=self.model_name,
                                messages=messages,
                                stream=True,
                                timeout=30.0
                            )
                            
                            full_text = ""
                            for chunk in response:
                                if chunk.choices and chunk.choices[0].delta.content:
                                    content = chunk.choices[0].delta.content
                                    full_text += content
                                    print(content, end="", file=sys.stderr, flush=True)
                            print("\n", file=sys.stderr, flush=True)
                            
                            text = re.sub(r'<think>.*?</think>', '', full_text, flags=re.DOTALL)
                            return text.strip()
                        except Exception as e:
                            print(f"\n[API Error] Attempt {attempt+1}/{retries} failed: {e}", file=sys.stderr, flush=True)
                            if attempt < retries - 1:
                                if hasattr(self, "api_keys") and self.api_keys:
                                    try:
                                        idx = self.api_keys.index(self.client.api_key)
                                        next_idx = (idx + 1) % len(self.api_keys)
                                    except ValueError:
                                        next_idx = 0
                                    self.client.api_key = self.api_keys[next_idx]
                                    print(f"Rotated Parser API key to: ...{self.client.api_key[-6:]}", file=sys.stderr, flush=True)
                                print("Retrying in 5 seconds...", file=sys.stderr, flush=True)
                                time.sleep(5)
                            else:
                                raise RuntimeError(f"SiliconFlow API failed after {retries} attempts: {e}")

                print("=========== [阶段 1] 深度解读报告生成中 ... ===========", file=sys.stderr, flush=True)
                md_report = _call_vl(stage1_prompt)
                print("=> 成功生成 学术报告 Markdown！", file=sys.stderr, flush=True)
                return md_report
            finally:
                doc.close()
            
        except Exception as e:
            raise RuntimeError(f"处理时发生错误: {str(e)}")
        finally:
            if 'doc' in locals() and hasattr(doc, 'close'):
                try:
                    doc.close()
                except:
                    pass

