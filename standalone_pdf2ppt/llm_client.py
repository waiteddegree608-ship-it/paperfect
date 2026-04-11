import os
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

    def process_paper_two_stage(self, file_path: str, stage1_prompt: str, stage2_prompt_builder) -> tuple:
        try:
            print(f"[{file_path}] 正在切割并编码 PDF ...")
            doc = fitz.open(file_path)
            base64_images = []
            
            static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_images")
            os.makedirs(static_dir, exist_ok=True)
            
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("jpeg")
                b64_str = base64.b64encode(img_data).decode('utf-8')
                base64_images.append(b64_str)
                with open(os.path.join(static_dir, f"page_{i}.jpg"), "wb") as f:
                    f.write(img_data)
            
            print(f"PDF 渲染完成，共转换 {len(base64_images)} 页。")

            # 封装视觉调用
            def _call_vl(prompt_text):
                content = []
                # 传入图片
                for j, b64 in enumerate(base64_images):
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": "high"
                        }
                    })
                # 附加指令
                content.append({"type": "text", "text": prompt_text})
                
                messages = [{"role": "user", "content": content}]
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages
                )
                
                # We need to clean the thinking block effectively if exist
                text = response.choices[0].message.content
                import re
                text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
                return text.strip()

            print("=========== [阶段 1] 深度解读报告生成中，这可能需要两分钟 ... ===========")
            md_report = _call_vl(stage1_prompt)
            print("=> 成功生成 学术报告 Markdown！")
            
            print("=========== [阶段 2] Galgame 人设交互剧本生成中，这可能需要两分钟 ... ===========")
            stage2_prompt = stage2_prompt_builder(md_report)
            
            # Use json_object format for stage 2
            content = []
            for j, b64 in enumerate(base64_images):
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "low" # Reduce cost for stage 2 since it mainly needs the text
                    }
                })
            content.append({"type": "text", "text": stage2_prompt})
            
            messages = [{"role": "user", "content": content}]
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                response_format={"type": "json_object"}
            )
            
            json_script = response.choices[0].message.content
            print("=> 成功生成 Galgame 剧本 JSON！")
            
            return md_report, json_script
            
        except Exception as e:
            raise RuntimeError(f"在处理论文双重解析时发生错误: {str(e)}")
        finally:
            if 'doc' in locals() and hasattr(doc, 'close'):
                try:
                    doc.close()
                except:
                    pass

    def get_stage1_md(self, file_path: str, stage1_prompt: str) -> str:
        try:
            print(f"[{file_path}] 正在切割并编码 PDF ...")
            doc = fitz.open(file_path)
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
                            "detail": "high"
                        }
                    })
                content.append({"type": "text", "text": prompt_text})
                
                messages = [{"role": "user", "content": content}]
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages
                )
                
                text = response.choices[0].message.content
                import re
                text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
                return text.strip()

            print("=========== [阶段 1] 深度解读报告生成中 ... ===========")
            md_report = _call_vl(stage1_prompt)
            print("=> 成功生成 学术报告 Markdown！")
            return md_report
            
        except Exception as e:
            raise RuntimeError(f"处理时发生错误: {str(e)}")
        finally:
            if 'doc' in locals() and hasattr(doc, 'close'):
                try:
                    doc.close()
                except:
                    pass

    def process_paper_three_stage(self, file_path: str, stage1_prompt: str, stage2_prompt_builder, stage3_prompt_builder) -> tuple:
        try:
            print(f"[{file_path}] 正在切割并编码 PDF ...")
            doc = fitz.open(file_path)
            base64_images = []
            
            static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "temp_images")
            os.makedirs(static_dir, exist_ok=True)
            
            for i, page in enumerate(doc):
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                img_data = pix.tobytes("jpeg")
                b64_str = base64.b64encode(img_data).decode('utf-8')
                base64_images.append(b64_str)
                with open(os.path.join(static_dir, f"page_{i}.jpg"), "wb") as f:
                    f.write(img_data)
            
            print(f"PDF 渲染完成，共转换 {len(base64_images)} 页。")

            # 封装视觉调用
            def _call_vl(prompt_text, detail="high"):
                content = []
                for _, b64 in enumerate(base64_images):
                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64}",
                            "detail": detail
                        }
                    })
                content.append({"type": "text", "text": prompt_text})
                
                messages = [{"role": "user", "content": content}]
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages
                )
                text = response.choices[0].message.content
                import re
                return re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

            print("=========== [阶段 1] 深度解读报告生成中 ... ===========")
            md_report = _call_vl(stage1_prompt, detail="high")
            print("=> 成功生成 学术报告 Markdown！")
            
            print("=========== [阶段 2] 纯学术结构化剧本生成中 ... ===========")
            stage2_prompt = stage2_prompt_builder(md_report)
            
            content2 = []
            for _, b64 in enumerate(base64_images):
                content2.append({
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}",
                        "detail": "low" # Reduce cost
                    }
                })
            content2.append({"type": "text", "text": stage2_prompt})
            
            response2 = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": content2}],
                response_format={"type": "json_object"}
            )
            raw_json_script = response2.choices[0].message.content
            import re
            raw_json_script = re.sub(r'<think>.*?</think>', '', raw_json_script, flags=re.DOTALL).strip()
            print("=> 成功生成 纯学术剧本 JSON！")
            
            print("=========== [阶段 3] 角色个性化台词洗稿润色中 ... ===========")
            stage3_prompt = stage3_prompt_builder(raw_json_script)
            # Text only for stage 3
            response3 = self.client.chat.completions.create(
                model=self.model_name,
                messages=[{"role": "user", "content": stage3_prompt}],
                response_format={"type": "json_object"}
            )
            final_json_script = response3.choices[0].message.content
            final_json_script = re.sub(r'<think>.*?</think>', '', final_json_script, flags=re.DOTALL).strip()
            print("=> 成功生成 个性化人设融合剧本！")
            
            return md_report, raw_json_script, final_json_script
            
        except Exception as e:
            raise RuntimeError(f"在处理论文三重解析时发生错误: {str(e)}")
        finally:
            if 'doc' in locals() and hasattr(doc, 'close'):
                try:
                    doc.close()
                except:
                    pass

    def chat_with_character(self, sys_prompt: str, history: List[dict], user_msg: str, pdf_path: str = None) -> dict:
        try:
            # For real-time chat with image context, use the VL model
            chat_model = "Qwen/Qwen3-VL-235B-A22B-Thinking"
            # It's better to pass instructions via user role when sending images, but system works too.
            messages = [{"role": "system", "content": sys_prompt}]
            
            # Add user history
            for msg in history:
                messages.append({"role": msg["role"], "content": msg["content"]})
            
            # Combine image content + user message
            content_list = []
            
            if pdf_path and os.path.exists(pdf_path):
                import fitz
                import base64
                doc = fitz.open(pdf_path)
                for i, page in enumerate(doc):
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                    img_data = pix.tobytes("jpeg")
                    b64_str = base64.b64encode(img_data).decode('utf-8')
                    content_list.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{b64_str}",
                            "detail": "high" # Unleash full vision capability as requested by user
                        }
                    })
                doc.close()
                
            content_list.append({"type": "text", "text": user_msg})
            
            messages.append({"role": "user", "content": content_list})
            
            response = self.client.chat.completions.create(
                model=chat_model,
                messages=messages,
                response_format={"type": "json_object"}
            )
            
            text_resp = response.choices[0].message.content
            import re
            text_resp = re.sub(r'<think>.*?</think>', '', text_resp, flags=re.DOTALL).strip()
            
            import json
            parsed = json.loads(text_resp)
            return parsed
        except Exception as e:
            return {"text": f"脑际连接有些故障，无法读取学术网络。({str(e)})", "emotion": "sad"}
