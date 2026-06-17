import os
import sys
import base64
from typing import List
import fitz  # PyMuPDF
from openai import OpenAI

class PaperReaderBot:
    def __init__(self, api_key: str = None, base_url: str = None, model_name: str = None):
        self.api_key = api_key or os.environ.get("SILICONFLOW_API_KEY")
        if not self.api_key:
            raise ValueError("未找到 API Key，请配置环境变量 SILICONFLOW_API_KEY 或传入 key。")
        
        # 使用 OpenAi 兼容接口调用硅基流动
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=base_url or "https://api.siliconflow.cn/v1"
        )
        self.model_name = model_name or "Qwen/Qwen3-VL-235B-A22B-Thinking"


    def get_stage1_md(self, file_path: str, stage1_prompt: str) -> str:
        try:
            print(f"[{file_path}] 正在切割并编码 PDF ...")
            doc = fitz.open(file_path)
            try:
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
                    
                    retries = 3
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
                                print("Retrying in 5 seconds...", file=sys.stderr, flush=True)
                                time.sleep(5)
                            else:
                                raise RuntimeError(f"SiliconFlow API failed after {retries} attempts: {e}")

                print("=========== [阶段 1] 深度解读报告生成中 ... ===========", file=sys.stderr, flush=True)
                md_report = _call_vl(stage1_prompt)
                print("=> 成功生成 学术报告 Markdown！", file=sys.stderr, flush=True)
                return md_report
            finally:
                doc.close()  # VERY IMPORTANT: Release the file lock!
            
        except Exception as e:
            raise RuntimeError(f"处理时发生错误: {str(e)}")
        finally:
            if 'doc' in locals() and hasattr(doc, 'close'):
                try:
                    doc.close()
                except:
                    pass

