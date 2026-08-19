# coding=utf-8
import os
import sys

# Ensure project root is in sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import asyncio
import shutil
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

async def translate_block_async(client, model, text, semaphore):
    global llm_balance_failed
    clean = text.strip()
    if not clean or len(clean) < 3 or clean.isdigit():
        return text
        
    lower_clean = clean.lower()
    if any(m in lower_clean for m in ["uist '", "chi '", "proceedings of", "copyright held by", "acm isbn"]):
        if len(clean) < 60:
            return text

    # Step 1: Try LLM first if API key is provided and balance hasn't failed yet
    if client and client.api_key and not llm_balance_failed:
        async with semaphore:
            for attempt in range(2):
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {
                                "role": "system",
                                "content": (
                                    "You are a professional academic translator. Translate the following paragraph of a computer science research paper "
                                    "into clear, natural, and fluent Chinese. Keep any abbreviations, citations (e.g., [12]), references to figures/tables "
                                    "(e.g., Figure 1), English product/system names (e.g., Surf, Beyond the Page, PaperWave), and mathematical symbols/variables as is. "
                                    "Output ONLY the translated Chinese text and nothing else."
                                )
                            },
                            {"role": "user", "content": text}
                        ],
                        temperature=0.1,
                        max_tokens=1500
                    )
                    translation = response.choices[0].message.content.strip()
                    if translation:
                        return translation
                except Exception as e:
                    err_msg = str(e).lower()
                    print(f"[Block Translate] LLM Attempt {attempt+1} failed: {e}")
                    if "balance" in err_msg or "insufficient" in err_msg or "403" in err_msg:
                        llm_balance_failed = True
                        print("[Block Translate] Balance insufficient detected. Switching to Google Fallback permanently for this run.")
                        break
                    await asyncio.sleep(0.5)

    # Step 2: Fallback to free GoogleTranslator (with retry backoff)
    async with semaphore:
        for g_attempt in range(3):
            try:
                from deep_translator import GoogleTranslator
                loop = asyncio.get_event_loop()
                translation = await loop.run_in_executor(
                    None,
                    lambda: GoogleTranslator(source='auto', target='zh-CN').translate(text)
                )
                if translation:
                    return translation.strip()
            except Exception as e:
                print(f"[Block Translate] Google Fallback Attempt {g_attempt+1} failed: {e}")
                if g_attempt < 2:
                    await asyncio.sleep(1.0 + g_attempt * 1.0)

    return text

async def translate_pdf_async(input_pdf, output_pdf):
    print(f"[Block Translate] Starting translation for: {input_pdf}")
    cfg = load_config()
    
    api_key = cfg.get("chat_api_key") or os.environ.get("CHAT_API_KEY", "")
    api_url = cfg.get("chat_api_url") or os.environ.get("CHAT_API_URL", "https://api.siliconflow.cn/v1")
    model = cfg.get("chat_model") or "Qwen/Qwen2.5-72B-Instruct"
    
    client = None
    if api_key:
        client = AsyncOpenAI(api_key=api_key, base_url=api_url)
        
    semaphore = asyncio.Semaphore(10)  # Concurrency limit of 10 requests to protect Google API
    
    doc = fitz.open(input_pdf)
    all_blocks = []
    
    # Step 1: Extract all text blocks from all pages
    for page_idx in range(len(doc)):
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
    
    # Step 2: Translate all blocks in parallel
    tasks = []
    for b in all_blocks:
        tasks.append(translate_block_async(client, model, b['orig_text'], semaphore))
        
    print("[Block Translate] Translating all blocks in parallel...")
    translations = await asyncio.gather(*tasks)
    
    for b, trans in zip(all_blocks, translations):
        b['translated_text'] = trans
        
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
