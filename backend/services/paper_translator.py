# coding=utf-8
import os
import sys

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import asyncio
import shutil
import re
import fitz
from openai import AsyncOpenAI
from backend.core.config import load_config

# Find a suitable CJK font on the system
font_candidates = [
    r"C:\Windows\Fonts\msyh.ttc",      # Microsoft YaHei
    r"C:\Windows\Fonts\simsun.ttc",     # SimSun
    r"C:\Windows\Fonts\simhei.ttf",     # SimHei
    r"C:\Windows\Fonts\STSONG.TTF",     # STSong
]
font_file = None
for fp in font_candidates:
    if os.path.exists(fp):
        font_file = fp
        break

# Global flag to quickly skip LLM calls if balance is insufficient
llm_balance_failed = False


def _looks_chinese(text: str) -> bool:
    if not text:
        return False
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    return cjk >= max(8, int(0.35 * len(text)))


def _skip_block(text: str) -> bool:
    clean = (text or "").strip()
    if not clean or len(clean) < 8 or clean.isdigit():
        return True
    if _looks_chinese(clean):
        return True
    lower_clean = clean.lower()
    if any(m in lower_clean for m in ["uist '", "chi '", "proceedings of", "copyright held by", "acm isbn"]):
        if len(clean) < 60:
            return True
    return False


def _pack_batches(indices_texts, max_chars=1600):
    batches = []
    cur, n = [], 0
    for idx, text in indices_texts:
        if cur and n + len(text) > max_chars:
            batches.append(cur)
            cur, n = [], 0
        cur.append((idx, text))
        n += len(text) + 8
    if cur:
        batches.append(cur)
    return batches


def _parse_json_array(text, expect_len):
    if not text:
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except Exception:
        m = re.search(r"\[[\s\S]*\]", cleaned)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except Exception:
            return None
    if not isinstance(data, list) or len(data) != expect_len:
        return None
    return [str(x) if x is not None else "" for x in data]


async def translate_batch_async(client, model, items, semaphore):
    """items: list[(idx, text)] -> list[str] translations in same order."""
    global llm_balance_failed
    texts = [t for _, t in items]
    if not client or not client.api_key or llm_balance_failed:
        return texts
    numbered = "\n".join(f"{i+1}. {t}" for i, t in enumerate(texts))
    from backend.services.model_pick import extra_body_for_model
    extra = extra_body_for_model(model)
    async with semaphore:
        for attempt in range(2):
            try:
                kwargs = dict(
                    model=model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are a professional academic translator. Translate each numbered English paragraph "
                                "into fluent Simplified Chinese. Keep abbreviations, citations like [12], figure/table "
                                "names, and math as-is. Output ONLY a JSON array of strings, same length and order. "
                                "No markdown."
                            ),
                        },
                        {"role": "user", "content": numbered},
                    ],
                    temperature=0.1,
                    max_tokens=min(4096, 80 + 350 * len(texts)),
                )
                if extra:
                    kwargs["extra_body"] = extra
                response = await client.chat.completions.create(**kwargs)
                raw = (response.choices[0].message.content or "").strip()
                parsed = _parse_json_array(raw, len(texts))
                if parsed:
                    return [p.strip() or orig for p, orig in zip(parsed, texts)]
            except Exception as e:
                err_msg = str(e).lower()
                print(f"[Block Translate] batch attempt {attempt+1} failed: {e}", flush=True)
                if "balance" in err_msg or "insufficient" in err_msg or "403" in err_msg:
                    llm_balance_failed = True
                    break
                await asyncio.sleep(0.4)
    return texts

def _pick_translated_pdf(out_dir, input_pdf, output_pdf):
    base = os.path.splitext(os.path.basename(input_pdf))[0]
    candidates = [
        os.path.join(out_dir, f"{base}-mono.pdf"),
        os.path.join(out_dir, f"{base}_mono.pdf"),
        os.path.join(out_dir, f"{base}.zh-CN.mono.pdf"),
        os.path.join(out_dir, f"{base}.zh.mono.pdf"),
        os.path.join(out_dir, f"{base}-zh.pdf"),
        output_pdf,
    ]
    try:
        for c in os.listdir(out_dir):
            low = c.lower()
            if low.endswith(".pdf") and ("mono" in low or "zh" in low or "translated" in low):
                candidates.insert(0, os.path.join(out_dir, c))
    except OSError:
        pass
    src_abs = os.path.abspath(input_pdf)
    for c in candidates:
        if os.path.isfile(c) and os.path.getsize(c) > 1024 and os.path.abspath(c) != src_abs:
            if os.path.abspath(c) != os.path.abspath(output_pdf):
                shutil.copy2(c, output_pdf)
            print(f"[Translate] layout translator wrote {output_pdf}")
            return True
    return False


def _try_pdf2zh_next_cli(input_pdf, output_pdf, body_end_page=None):
    """PDFMathTranslate-next (pdf2zh-next): supports Python 3.10–3.13."""
    import subprocess
    cfg = load_config()
    out_dir = os.path.dirname(output_pdf) or "."
    os.makedirs(out_dir, exist_ok=True)
    exe = os.path.join(os.path.dirname(sys.executable), "pdf2zh_next.exe")
    if os.path.isfile(exe):
        prefix = [exe]
    else:
        prefix = [sys.executable, "-m", "pdf2zh_next"]
    cmd = prefix + [os.path.abspath(input_pdf), "--output", os.path.abspath(out_dir),
           "--lang-in", "en", "--lang-out", "zh-CN"]
    if body_end_page:
        cmd += ["--pages", f"1-{int(body_end_page)}"]
    env = os.environ.copy()
    env_key = cfg.get("chat_api_key") or env.get("CHAT_API_KEY") or env.get("OPENAI_API_KEY")
    if isinstance(env_key, (list, tuple)):
        env_key = env_key[0] if env_key else ""
    env_url = cfg.get("chat_api_url") or env.get("CHAT_API_URL") or env.get("OPENAI_BASE_URL")
    model = cfg.get("chat_model") or env.get("OPENAI_MODEL") or "gpt-4o-mini"
    if env_key:
        cmd += [
            "--openai",
            "--openai-api-key", str(env_key),
            "--openai-model", str(model),
        ]
        env["OPENAI_API_KEY"] = str(env_key)
        if env_url:
            url = str(env_url).rstrip("/")
            if not url.endswith("/v1"):
                url = url + "/v1"
            cmd += ["--openai-base-url", url]
            env["OPENAI_BASE_URL"] = url
        env["OPENAI_MODEL"] = str(model)
    else:
        cmd.append("--google")
    print(f"[Translate] Running pdf2zh-next ...")
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=1800)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-2000:]
        raise RuntimeError(f"pdf2zh-next exited {proc.returncode}: {err}")
    if _pick_translated_pdf(out_dir, input_pdf, output_pdf):
        return True
    raise RuntimeError("pdf2zh-next finished but no translated PDF was found")


def _try_pdf2zh_legacy(input_pdf, output_pdf, body_end_page=None):
    """Old pdf2zh (<3.13). Kept for environments that still have it."""
    cfg = load_config()
    try:
        from pdf2zh import translate as pdf2zh_translate
    except Exception:
        from pdf2zh.high_level import translate as pdf2zh_translate
    out_dir = os.path.dirname(output_pdf) or "."
    os.makedirs(out_dir, exist_ok=True)
    pages = list(range(int(body_end_page))) if body_end_page else None
    env_key = cfg.get("chat_api_key") or os.environ.get("CHAT_API_KEY") or os.environ.get("OPENAI_API_KEY")
    env_url = cfg.get("chat_api_url") or os.environ.get("CHAT_API_URL") or os.environ.get("OPENAI_BASE_URL")
    model = cfg.get("chat_model") or "gpt-4o-mini"
    kwargs = dict(files=[input_pdf], output=out_dir, lang_in="en", lang_out="zh", thread=4)
    if pages:
        kwargs["pages"] = pages
    if env_key:
        os.environ.setdefault("OPENAI_API_KEY", env_key if isinstance(env_key, str) else (env_key[0] if env_key else ""))
        if env_url:
            os.environ.setdefault("OPENAI_BASE_URL", env_url)
        kwargs["service"] = "openai"
        kwargs["model"] = model
    else:
        kwargs["service"] = "google"
    print(f"[Translate] Running legacy pdf2zh ({kwargs.get('service')}) ...")
    try:
        pdf2zh_translate(**kwargs)
    except TypeError:
        kwargs.pop("pages", None)
        kwargs.pop("model", None)
        pdf2zh_translate(**kwargs)
    return _pick_translated_pdf(out_dir, input_pdf, output_pdf)


def _try_pdf2zh(input_pdf, output_pdf, body_end_page=None):
    """Layout translator is optional: it is accurate but much slower than block translate."""
    if os.environ.get("PAPERFECT_USE_PDF2ZH", "").strip().lower() not in ("1", "true", "yes"):
        print("[Translate] Skipping pdf2zh-next (set PAPERFECT_USE_PDF2ZH=1 to enable). Using parallel block translate.")
        return False
    errors = []
    try:
        import pdf2zh_next  # noqa: F401
        return _try_pdf2zh_next_cli(input_pdf, output_pdf, body_end_page)
    except Exception as e:
        errors.append(f"pdf2zh-next: {e}")
        print(f"[Translate] pdf2zh-next skipped ({e})")
    try:
        return _try_pdf2zh_legacy(input_pdf, output_pdf, body_end_page)
    except Exception as e:
        errors.append(f"pdf2zh: {e}")
        print(f"[Translate] legacy pdf2zh skipped ({e})")
    print("[Translate] no layout translator available: " + " | ".join(errors))
    return False


async def translate_pdf_async(input_pdf, output_pdf):
    print(f"[Block Translate] Starting translation for: {input_pdf}")
    cfg = load_config()
    body_end = None
    try:
        from backend.services.pdf_body import detect_body_range
        info = detect_body_range(input_pdf)
        body_end = info.get("body_end_page") if info.get("confidence") == "heading" else None
        if body_end:
            print(f"[Block Translate] Skipping pages after {body_end} (references).")
    except Exception as e:
        print(f"[Block Translate] body-range detect skipped: {e}")

    try:
        if _try_pdf2zh(input_pdf, output_pdf, body_end):
            return
    except Exception as e:
        print(f"[Translate] pdf2zh failed ({e}); falling back to block translator.")

    
    from backend.services.model_pick import pick_fast_text_model
    api_key = cfg.get("translate_api_key") or cfg.get("chat_api_key") or os.environ.get("CHAT_API_KEY", "")
    if isinstance(api_key, list):
        api_key = api_key[0] if api_key else ""
    api_url = cfg.get("translate_api_url") or cfg.get("chat_api_url") or os.environ.get("CHAT_API_URL", "https://opencode.ai/zen/go/v1")
    model = pick_fast_text_model(cfg)
    n_conc = max(4, int(os.environ.get("TRANSLATE_CONCURRENCY", "50") or 50))
    print(f"[Block Translate] model={model} (parallel blocks, semaphore={n_conc})", flush=True)
    
    client = None
    if api_key:
        client = AsyncOpenAI(api_key=api_key, base_url=api_url, timeout=90.0)
        
    semaphore = asyncio.Semaphore(n_conc)
    
    doc = fitz.open(input_pdf)
    all_blocks = []
    
    # Step 1: Extract all text blocks from body pages only
    last_page_idx = (body_end - 1) if body_end else (len(doc) - 1)
    for page_idx in range(len(doc)):
        if page_idx > last_page_idx:
            continue
        page = doc[page_idx]
        blocks_dict = page.get_text("dict")["blocks"]
        
        for block_idx, block in enumerate(blocks_dict):
            if block.get("type") == 0:  # Text block
                text_parts = []
                sizes = []
                colors = []
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        text_parts.append(span.get("text", ""))
                        sizes.append(span.get("size", 9.0))
                        colors.append(span.get("color", 0))
                
                block_text = "".join(text_parts).strip()
                if not block_text:
                    continue
                    
                avg_size = sum(sizes) / len(sizes) if sizes else 9.0
                c_int = colors[0] if colors else 0
                r = ((c_int >> 16) & 255) / 255.0
                g = ((c_int >> 8) & 255) / 255.0
                b = (c_int & 255) / 255.0
                rgb_color = (r, g, b)
                
                all_blocks.append({
                    'page_idx': page_idx,
                    'rect': fitz.Rect(block['bbox']),
                    'orig_text': block_text,
                    'avg_size': avg_size,
                    'color': rgb_color
                })
                
    print(f"[Block Translate] Extracted {len(all_blocks)} text blocks from {len(doc)} pages.")

    from backend.services.stage_progress import write_progress
    to_translate = []
    for i, b in enumerate(all_blocks):
        if _skip_block(b["orig_text"]):
            b["translated_text"] = b["orig_text"]
        else:
            to_translate.append((i, b["orig_text"]))
    batches = _pack_batches(to_translate, max_chars=2200)
    write_progress(None, 0, max(1, len(batches)))
    print(f"[Block Translate] {len(to_translate)} blocks in {len(batches)} batched LLM calls, concurrency={n_conc}.", flush=True)

    done = {"n": 0}

    async def _run_batch(batch):
        result = await translate_batch_async(client, model, batch, semaphore)
        done["n"] += 1
        write_progress(None, done["n"], max(1, len(batches)))
        return batch, result

    batch_results = await asyncio.gather(*[_run_batch(b) for b in batches]) if batches else []
    for batch, trans in batch_results:
        for (idx, _orig), zh in zip(batch, trans):
            all_blocks[idx]["translated_text"] = zh or all_blocks[idx]["orig_text"]
    for b in all_blocks:
        if "translated_text" not in b:
            b["translated_text"] = b["orig_text"]
        
    print("[Block Translate] Translation finished. Reconstructing PDF layout...")
    
    # Step 3: Cover original text and insert translated text
    # NOTE: page.apply_redactions() can crash on pages with images in Lab / ICC /
    # Separation / DeviceN colorspaces ("only Gray, RGB, and CMYK colorspaces supported").
    # Prefer redaction that never rewrites images; fall back to white fill overlays.
    global font_file
    if not font_file:
        print("[Block Translate] Warning: No CJK font found on system, using default fonts.")

    def _apply_page_redactions(page):
        """Remove/cover text under redaction annots without rewriting exotic images."""
        # MuPDF redaction re-encodes overlapping images; Lab/ICC/Separation/etc. raise:
        #   FzErrorArgument: only Gray, RGB, and CMYK colorspaces supported
        # Skip image/graphics rewriting — we only need original text gone.
        img_none = getattr(fitz, "PDF_REDACT_IMAGE_NONE", 0)
        gfx_none = getattr(fitz, "PDF_REDACT_LINE_ART_NONE", 0)
        kwargs_try = [
            {"images": img_none, "graphics": gfx_none},
            {"images": img_none},
            {},
        ]
        last_err = None
        for kw in kwargs_try:
            try:
                page.apply_redactions(**kw)
                return True
            except TypeError:
                # Older pymupdf may not accept these kwargs
                try:
                    page.apply_redactions()
                    return True
                except Exception as e:
                    last_err = e
                    break
            except Exception as e:
                last_err = e
                continue
        if last_err:
            print(f"[Block Translate] apply_redactions failed: {last_err}")
        return False

    def _cover_with_white(page, rects):
        """Fallback when redaction is impossible: paint opaque white boxes over text."""
        for r in rects:
            try:
                # shape under content can fail; use annotation-free draw on page
                page.draw_rect(r, color=(1, 1, 1), fill=(1, 1, 1), width=0, overlay=True)
            except Exception as e:
                print(f"[Block Translate] white cover failed: {e}")

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_blocks = [b for b in all_blocks if b['page_idx'] == page_idx]
        if not page_blocks:
            continue

        rects = [pb['rect'] for pb in page_blocks]

        # Mark original text areas for redaction (white fill)
        for r in rects:
            try:
                page.add_redact_annot(r, fill=(1, 1, 1))
            except Exception as e:
                print(f"[Block Translate] add_redact_annot failed on page {page_idx+1}: {e}")

        ok = _apply_page_redactions(page)
        if not ok:
            # Clear any leftover redact annots then paint white covers
            try:
                for annot in list(page.annots() or []):
                    if annot.type[0] == fitz.PDF_ANNOT_REDACT:
                        page.delete_annot(annot)
            except Exception:
                pass
            _cover_with_white(page, rects)

        # Write translated text boxes
        for pb in page_blocks:
            scaled_size = pb['avg_size'] * 0.95
            if scaled_size < 6.0:
                scaled_size = 6.0

            try:
                page.insert_textbox(
                    pb['rect'], pb['translated_text'],
                    fontfile=font_file,
                    fontname="msyh" if font_file else "helv",
                    fontsize=scaled_size,
                    color=pb['color'],
                )
            except Exception as e:
                print(f"[Block Translate] Error inserting text on page {page_idx+1}: {e}")

    # Step 4: Save final PDF
    # garbage=4 can also choke on odd colorspaces in some builds — degrade gracefully
    try:
        doc.save(output_pdf, garbage=4, deflate=True)
    except Exception as e:
        print(f"[Block Translate] save(garbage=4) failed ({e}); retrying simple save...")
        doc.save(output_pdf, deflate=True)
    doc.close()
    print(f"[Block Translate] Completed successfully! Saved to: {output_pdf}")

def translate_pdf(input_pdf, output_pdf):
    asyncio.run(translate_pdf_async(input_pdf, output_pdf))

if __name__ == "__main__":
    if len(sys.argv) > 2:
        translate_pdf(sys.argv[1], sys.argv[2])
