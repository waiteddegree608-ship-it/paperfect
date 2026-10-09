import os
import sys
import base64
from typing import List
import fitz  # PyMuPDF
from backend.core.config import opencode_headers
from backend.services.skill_registry import load_skill
from openai import OpenAI

def is_billing_error(err) -> bool:
    blob = f"{type(err).__name__} {err}".lower()
    return any(
        x in blob
        for x in (
            "creditserror",
            "insufficient balance",
            "insufficient credits",
            "payment required",
            "quota exceeded",
            "余额不足",
        )
    )


def billing_error_message() -> str:
    return "服务商拒绝了此请求：请检查账户额度、Key 权限以及所选模型是否可用。"


class PaperReaderBot:
    def __init__(self, api_key: str = None, base_url: str = None, model_name: str = None):
        from backend.core.config import load_config
        cfg = load_config()
        configured_keys = cfg.get("parse_api_key") or []
        self.api_key = api_key if api_key is not None else (configured_keys[0] if configured_keys else "")
        if not self.api_key:
            raise ValueError("未找到解析 API Key，请在设置中配置。")
        url = base_url or cfg["parse_api_url"]
        self.client = OpenAI(api_key=self.api_key, base_url=url, default_headers=opencode_headers("paperfect-parse"))
        self.model_name = model_name or cfg["parse_model"]
        self.api_keys = configured_keys if url.rstrip("/") == cfg["parse_api_url"].rstrip("/") and self.api_key in configured_keys else [self.api_key]



    def _extract_paper_text(self, doc, limit: int) -> str:
        full_text = ""
        for i, page in enumerate(doc):
            if i >= limit:
                break
            full_text += f"\n--- Page {i+1} ---\n"
            blocks = page.get_text("blocks")
            blocks = [b for b in blocks if b[6] == 0]
            width = page.rect.width
            height = page.rect.height
            mid = width / 2
            left_col, right_col, full_width = [], [], []
            for b in blocks:
                x0, y0, x1, y1, text, block_no, block_type = b
                if y0 < 45 or y1 > height - 45:
                    continue
                if (x1 - x0) > width * 0.6:
                    full_width.append(b)
                elif x1 <= mid or x0 < mid - 20:
                    left_col.append(b)
                else:
                    right_col.append(b)
            full_width_sorted = sorted(full_width, key=lambda x: x[1])
            left_col_sorted = sorted(left_col, key=lambda x: x[1])
            right_col_sorted = sorted(right_col, key=lambda x: x[1])
            top_full = [b for b in full_width_sorted if b[1] < height / 3]
            bottom_full = [b for b in full_width_sorted if b[1] >= height / 3]
            page_blocks = top_full + left_col_sorted + right_col_sorted + bottom_full
            for b in page_blocks:
                b_text = b[4].strip().replace("-\n", "").replace("- \n", "")
                full_text += b_text + "\n\n"
        return full_text

    def _stream_text(self, response) -> str:
        result_text = ""
        reasoning_text = ""
        for chunk in response:
            if not (chunk.choices and chunk.choices[0].delta):
                continue
            delta = chunk.choices[0].delta
            piece = getattr(delta, "content", None) or ""
            if piece:
                result_text += piece
                print(piece, end="", file=sys.stderr, flush=True)
            reason = getattr(delta, "reasoning_content", None) or ""
            if reason:
                reasoning_text += reason
        print("\n", file=sys.stderr, flush=True)
        return result_text or reasoning_text

    def _complete_text(self, paper_text: str, prompt_text: str) -> str:
        from backend.services.model_pick import (
            extra_body_variants,
            strip_think,
            reasoning_max_tokens,
            is_reasoning_model,
        )
        extras = extra_body_variants(self.model_name)
        max_tokens = reasoning_max_tokens(4096, self.model_name, cap=8192)
        timeout = 300.0 if is_reasoning_model(self.model_name) else 180.0
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a professional academic assistant. Read the extracted paper text "
                    "and generate a structured Markdown report based on the user's requirements."
                    + load_skill("paper-reading").split("Return JSON")[0]
                    + "For this call, output Markdown following the requested sections, with physical page citations."
                ),
            },
            {
                "role": "user",
                "content": f"【论文文本内容】:\n{paper_text}\n\n【生成要求】:\n{prompt_text}",
            },
        ]
        import time
        keys = list(self.api_keys or [self.api_key])
        retries = max(4, len(extras))
        last_err = None
        for attempt in range(retries):
            key = keys[attempt % len(keys)]
            extra = extras[attempt] if attempt < len(extras) else None
            local = OpenAI(
                api_key=key,
                base_url=str(self.client.base_url),
                default_headers=opencode_headers("paperfect-parse"),
            )
            try:
                kwargs = dict(
                    model=self.model_name,
                    messages=messages,
                    stream=True,
                    timeout=timeout,
                    max_tokens=max_tokens,
                )
                if extra:
                    kwargs["extra_body"] = extra
                response = local.chat.completions.create(**kwargs)
                result_text = strip_think(self._stream_text(response))
                if len(result_text) < 32:
                    raise RuntimeError(
                        "empty parse output (thinking trace likely ate the answer)"
                    )
                return result_text
            except Exception as e:
                last_err = e
                print(f"\n[API Error] Attempt {attempt+1}/{retries} failed: {e}", file=sys.stderr, flush=True)
                if is_billing_error(e):
                    raise RuntimeError(billing_error_message()) from e
                if attempt < retries - 1:
                    print(f"Rotated Parser API key to: ...{key[-6:]}", file=sys.stderr, flush=True)
                    time.sleep(2)
        if last_err and is_billing_error(last_err):
            raise RuntimeError(billing_error_message()) from last_err
        raise RuntimeError(f"Parse API failed after {retries} attempts: {last_err}")

    def get_stage1_md(self, file_path: str, stage1_prompt: str, max_pages: int = None, jobs: list = None) -> str:
        try:
            print(f"[{file_path}] 打开 PDF 并准备分析 ...")
            doc = fitz.open(file_path)
            try:
                n_pages = len(doc)
                limit = n_pages if not max_pages else max(1, min(int(max_pages), n_pages))
                if limit < n_pages:
                    print(f"[{file_path}] 仅解析正文 {limit}/{n_pages} 页（跳过参考文献及之后）", file=sys.stderr, flush=True)
                use_vision = os.environ.get("PAPERFECT_PARSE_VL", "").strip().lower() in ("1", "true", "yes")
                is_deepseek = "deepseek" in str(self.model_name).lower() or "deepseek" in str(self.client.base_url).lower()

                if is_deepseek or not use_vision:
                    print(f"[{file_path}] 使用文本抽取生成解读，模型={self.model_name} ...", file=sys.stderr, flush=True)
                    full_text = self._extract_paper_text(doc, limit)
                    from backend.services.stage_progress import write_progress
                    job_list = list(jobs or [])
                    if not job_list:
                        job_list = [{"title": "学术解析", "prompt": stage1_prompt}]
                    n_jobs = max(1, len(job_list))
                    print(
                        f"=========== [阶段 1] {n_jobs} 段提示词并行解读 ... ===========",
                        file=sys.stderr,
                        flush=True,
                    )
                    write_progress(None, 0, n_jobs, f"0/{n_jobs}")
                    results = [""] * n_jobs
                    done = {"n": 0}

                    def _one(idx_job):
                        idx, job = idx_job
                        title = job.get("title") or f"第{idx+1}节"
                        print(f"\n--- 并行解读 [{idx+1}/{n_jobs}] {title} ---\n", file=sys.stderr, flush=True)
                        text = self._complete_text(full_text, job.get("prompt") or "")
                        return idx, title, text

                    from backend.services.model_pick import is_reasoning_model
                    from concurrent.futures import ThreadPoolExecutor, as_completed
                    default_cc = 2 if is_reasoning_model(self.model_name) else 8
                    workers = min(n_jobs, max(1, int(os.environ.get("PARSE_CONCURRENCY", str(default_cc)) or default_cc)))
                    with ThreadPoolExecutor(max_workers=workers) as ex:
                        futs = [ex.submit(_one, (i, job)) for i, job in enumerate(job_list)]
                        for fut in as_completed(futs):
                            idx, title, text = fut.result()
                            results[idx] = f"## {title}\n\n{text}".strip()
                            done["n"] += 1
                            write_progress(None, done["n"], n_jobs, f"{done['n']}/{n_jobs}")
                    md_report = "\n\n---\n\n".join(results)
                    write_progress(None, n_jobs, n_jobs, "解读完成")
                    print("=> 成功生成 学术报告 Markdown！", file=sys.stderr, flush=True)
                    return md_report

                # Otherwise, fallback to the original VL image-based parsing
                print(f"[{file_path}] 正在切割并编码 PDF ...")
                base64_images = []
                # 1.5x JPEG is enough for layout VL and uses far less RAM than 2x of every page
                mat = fitz.Matrix(1.5, 1.5)
                for i, page in enumerate(doc):
                    if i >= limit:
                        break
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("jpeg")
                    b64_str = base64.b64encode(img_data).decode('utf-8')
                    base64_images.append(b64_str)
                
                def _call_vl(prompt_text):
                    from backend.services.model_pick import (
                        extra_body_variants,
                        strip_think,
                        reasoning_max_tokens,
                        is_reasoning_model,
                    )
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
                    
                    messages = [{"role": "system", "content": load_skill("paper-reading").split("Return JSON")[0] + "For this call output Markdown, with physical PDF page citations."}, {"role": "user", "content": content}]
                    import time
                    extras = extra_body_variants(self.model_name)
                    max_tokens = reasoning_max_tokens(4096, self.model_name, cap=8192)
                    timeout = 300.0 if is_reasoning_model(self.model_name) else 180.0
                    retries = max(6, len(extras))
                    last_err = None
                    for attempt in range(retries):
                        try:
                            extra = extras[attempt] if attempt < len(extras) else None
                            kwargs = dict(
                                model=self.model_name,
                                messages=messages,
                                stream=True,
                                timeout=timeout,
                                max_tokens=max_tokens,
                            )
                            if extra:
                                kwargs["extra_body"] = extra
                            response = self.client.chat.completions.create(**kwargs)
                            full_text = strip_think(self._stream_text(response))
                            if len(full_text) < 32:
                                raise RuntimeError(
                                    "empty parse output (thinking trace likely ate the answer)"
                                )
                            return full_text
                        except Exception as e:
                            last_err = e
                            print(f"\n[API Error] Attempt {attempt+1}/{retries} failed: {e}", file=sys.stderr, flush=True)
                            if attempt < retries - 1:
                                if hasattr(self, "api_keys") and self.api_keys:
                                    try:
                                        idx = self.api_keys.index(self.client.api_key)
                                        next_idx = (idx + 1) % len(self.api_keys)
                                    except ValueError:
                                        next_idx = 0
                                    self.client.api_key = self.api_keys[next_idx]
                                    print("Rotated parser API key", file=sys.stderr, flush=True)
                                print("Retrying in 5 seconds...", file=sys.stderr, flush=True)
                                time.sleep(5)
                    raise RuntimeError(f"Parse API failed after {retries} attempts: {last_err}")

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

