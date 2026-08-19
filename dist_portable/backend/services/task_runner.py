import os
import sys
import asyncio
import shutil
import random
from backend.core.config import get_base_dir, load_config
from backend.services.file_manager import active_tasks, active_tasks_progress

def get_python_executable():
    """Prefer venv / runtime python; fall back to this process (frozen paperfect.exe)."""
    import sys
    base = get_base_dir()
    candidates = [
        os.path.join(base, "venv", "Scripts", "python.exe"),
        os.path.join(base, "runtime", "python", "python.exe"),
        os.path.join(base, "python", "python.exe"),
    ]
    for c in candidates:
        if c and os.path.isfile(c):
            return c
    return sys.executable


def get_node_executable():
    """Resolve Node for PPT generation (bundled runtime first, then PATH)."""
    base = get_base_dir()
    candidates = [
        os.path.join(base, "runtime", "node", "node.exe"),
        os.path.join(base, "runtime", "node", "node"),
        os.path.join(base, "node", "node.exe"),
        "node",
    ]
    for c in candidates:
        if c == "node":
            return c
        if os.path.isfile(c):
            return c
    return "node"


def python_cmd_for_script(script_path, *script_args):
    """
    Build argv to run a .py file.
    When the interpreter is the frozen paperfect.exe, use --script so main.py
    dispatches via runpy instead of starting uvicorn.
    """
    import sys
    py = get_python_executable()
    script_path = os.path.abspath(script_path)
    args = [str(a) for a in script_args]
    frozen_self = getattr(sys, "frozen", False) and os.path.normcase(os.path.abspath(py)) == os.path.normcase(
        os.path.abspath(sys.executable)
    )
    # Also treat named paperfect.exe without venv as frozen helper
    looks_like_app_exe = os.path.basename(py).lower() in ("paperfect.exe", "paperfect_backend.exe")
    if frozen_self or looks_like_app_exe:
        return [py, "--script", script_path] + args
    return [py, "-u", script_path] + args

def force_print(*args, **kwargs):
    text = " ".join(map(str, args))
    try:
        print(text, **kwargs, file=sys.stdout, flush=True)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding), **kwargs, file=sys.stdout, flush=True)

async def _read_stream(stream, prefix="", book_name=None):
    # Print the prefix first
    if prefix:
        force_print(prefix, end="")
    
    last_char_was_cr = False
    
    while True:
        try:
            chunk = await stream.read(1)
        except Exception:
            break
            
        if not chunk:
            break
            
        try:
            char = chunk.decode('utf-8', errors='ignore')
            if char:
                # If we encounter a carriage return (used by progress bars), we must print it 
                # and then reprint the prefix so the next line has the prefix too.
                if char == '\r':
                    sys.stdout.write('\r')
                    sys.stdout.write(prefix)
                    sys.stdout.flush()
                    last_char_was_cr = True
                elif char == '\n':
                    sys.stdout.write('\n')
                    sys.stdout.write(prefix)
                    sys.stdout.flush()
                    last_char_was_cr = False
                else:
                    sys.stdout.write(char)
                    sys.stdout.flush()
                    last_char_was_cr = False
        except Exception:
            pass


async def run_subprocess(name, cmd, cwd=None, book_name=None):
    force_print(f"[{name}] Starting: {' '.join(cmd)}")
    import subprocess
    creationflags = 0
    if sys.platform == 'win32':
        creationflags = subprocess.CREATE_NO_WINDOW
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=creationflags
    )
    
    await asyncio.gather(
        _read_stream(process.stdout, prefix=f"[{name}] ", book_name=book_name),
        _read_stream(process.stderr, prefix=f"[{name} ERR] ", book_name=book_name)
    )
    
    await process.wait()
    if process.returncode != 0:
        raise RuntimeError(f"{name} failed with exit code {process.returncode}")
    force_print(f"[{name}] Completed successfully.")
    return ""

async def async_run_builder(pdf_path: str, book_name: str, item_type: str, prompt_type: str = "提示词汇总", ppt_mode: str = "creative", ppt_lang: str = "zh"):
    task_id = f"{item_type}s_{book_name}"
    
    progress_map = {
        "zh": {
            "init": "初始化",
            "parse": "解析文献",
            "translate": "翻译文献",
            "ppt": "生成PPT",
            "annotate": "生成批注",
            "finalize": "收尾"
        },
        "en": {
            "init": "Initializing",
            "parse": "Parsing",
            "translate": "Translating",
            "ppt": "Generating PPT",
            "annotate": "Generating Annotations",
            "finalize": "Finalizing"
        }
    }
    lang = "en" if ppt_lang == "en" else "zh"
    # Weighted multi-stage progress (parallel-safe: last writer no longer jumps to 90% forever)
    # parse 40% + translate 10% + ppt 25% + annotate 25%  →  overall 0–100
    stage_frac = {"parse": 0.0, "translate": 0.0, "ppt": 0.0, "annotate": 0.0}
    stage_weights = {"parse": 40, "translate": 10, "ppt": 25, "annotate": 25}
    current_label = progress_map[lang]["init"]

    def publish_prog(stage_key=None, label_override=None):
        nonlocal current_label
        if label_override:
            current_label = label_override
        elif stage_key:
            current_label = progress_map[lang].get(stage_key, current_label)
        total = 5  # base after init
        for k, w in stage_weights.items():
            total += stage_frac.get(k, 0.0) * w
        percent = int(max(5, min(99, round(total))))
        active_tasks_progress[task_id] = {"percent": percent, "stage": current_label}

    def update_prog(percent, stage_key):
        """Legacy helper: map coarse checkpoints into stage fractions."""
        # percent here is treated as 0-100 of that stage when stage_key known
        mapping = {
            "init": None,
            "parse": "parse",
            "translate": "translate",
            "ppt": "ppt",
            "annotate": "annotate",
        }
        sk = mapping.get(stage_key)
        if stage_key == "init":
            publish_prog("init")
            return
        if sk:
            # Interpret classic checkpoints as stage completion ratios
            # e.g. parse 15 → early, 35 → mid/late
            if sk == "parse":
                if percent <= 20:
                    stage_frac["parse"] = max(stage_frac["parse"], 0.25)
                elif percent <= 40:
                    stage_frac["parse"] = max(stage_frac["parse"], 0.55)
                else:
                    stage_frac["parse"] = max(stage_frac["parse"], 1.0)
            elif sk == "translate":
                stage_frac["translate"] = max(stage_frac["translate"], min(1.0, percent / 100.0) if percent >= 50 else 0.3)
            elif sk == "ppt":
                if percent <= 60:
                    stage_frac["ppt"] = max(stage_frac["ppt"], 0.15)
                elif percent <= 80:
                    stage_frac["ppt"] = max(stage_frac["ppt"], 0.55)
                else:
                    stage_frac["ppt"] = max(stage_frac["ppt"], 1.0)
            elif sk == "annotate":
                if percent <= 70:
                    stage_frac["annotate"] = max(stage_frac["annotate"], 0.15)
                elif percent <= 90:
                    stage_frac["annotate"] = max(stage_frac["annotate"], 0.45)
                else:
                    stage_frac["annotate"] = max(stage_frac["annotate"], 1.0)
            publish_prog(sk)

    def set_stage_frac(stage_key, frac, label_key=None):
        stage_frac[stage_key] = max(stage_frac.get(stage_key, 0.0), min(1.0, float(frac)))
        publish_prog(label_key or stage_key)

    async def crawl_stage(stage_key, start_frac, end_frac, seconds, stop_event):
        """Slowly advance progress during long subprocesses so UI doesn't freeze at one %."""
        steps = max(1, int(seconds / 2.5))
        for i in range(steps):
            if stop_event.is_set():
                break
            f = start_frac + (end_frac - start_frac) * ((i + 1) / steps)
            set_stage_frac(stage_key, f, stage_key)
            try:
                await asyncio.sleep(2.5)
            except asyncio.CancelledError:
                break

    update_prog(5, "init")
    try:
        if item_type == "book":
            script_path = os.path.join(get_base_dir(), "backend", "services", "universal_kb_builder.py")
            await run_subprocess("Book Builder", python_cmd_for_script(script_path, pdf_path), book_name=book_name)
        else:
            base_dir = get_base_dir()
            target_dir = os.path.join(base_dir, "data", "papers", book_name)
            
            # Paths according to new structure
            raw_pdf = pdf_path
            translated_pdf = os.path.join(target_dir, "translated", f"{book_name}_translated.pdf")
            kb_file = os.path.join(target_dir, "parsed", f"{book_name}_KnowledgeBase.md")
            parsed_md = os.path.join(target_dir, "parsed", f"输出结果_{book_name}.md")
            out_ppt = os.path.join(target_dir, "pptx", f"{book_name}_Full_Presentation.pptx")
            annotated_pdf = os.path.join(target_dir, "marked", f"{book_name}_annotated.pdf")
            
            for sub in ["translated", "parsed", "pptx", "marked", "images", "cache"]:
                os.makedirs(os.path.join(target_dir, sub), exist_ok=True)

            # Provide a work_dir for legacy scripts that expect it
            work_dir = os.path.join(target_dir, "raw")

            def _file_ok(path, min_bytes=64):
                try:
                    return os.path.isfile(path) and os.path.getsize(path) >= min_bytes
                except OSError:
                    return False

            # Step 1: Translate and Parse in parallel
            async def run_translate():
                # Resume: skip if translated PDF already exists
                if _file_ok(translated_pdf, min_bytes=1024):
                    force_print(f"[Translate] Resume skip — already exists: {translated_pdf}")
                    set_stage_frac("translate", 1.0, "translate")
                    return
                if ppt_lang == "en":
                    force_print("[Translate] Target language is English. Skipping translation and copying original PDF.")
                    shutil.copy(pdf_path, translated_pdf)
                    set_stage_frac("translate", 1.0, "translate")
                    return
                set_stage_frac("translate", 0.1, "translate")
                stop_ev = asyncio.Event()
                crawl = asyncio.create_task(crawl_stage("translate", 0.1, 0.9, 90, stop_ev))
                script_path = os.path.join(get_base_dir(), "backend", "services", "paper_translator.py")
                try:
                    await run_subprocess("Translate", python_cmd_for_script(script_path, pdf_path, translated_pdf), book_name=book_name)
                    set_stage_frac("translate", 1.0, "translate")
                except Exception as e:
                    force_print(f"Translate failed, skipping translation: {e}")
                    set_stage_frac("translate", 1.0, "translate")
                finally:
                    stop_ev.set()
                    crawl.cancel()

            async def run_parse():
                # Resume: if KnowledgeBase already written, skip expensive re-parse
                if _file_ok(kb_file, min_bytes=200):
                    force_print(f"[Parse] Resume skip — KnowledgeBase exists: {kb_file}")
                    set_stage_frac("parse", 1.0, "parse")
                    return

                def parse_sync():
                    from backend.services.project_manager import ProjectManager
                    from backend.services.llm_client import PaperReaderBot
                    from backend.services.prompts import get_stage1_prompt
                    
                    pm = ProjectManager(base_dir=target_dir)
                    images_dir = os.path.join(target_dir, "images")
                    os.makedirs(images_dir, exist_ok=True)
                    
                    set_stage_frac("parse", 0.15, "parse")
                    pm.extract_semantic_figures(pdf_path, work_dir)
                    # Move figures to target_dir/images
                    figures_in_work = os.path.join(work_dir, "images")
                    if os.path.exists(figures_in_work):
                        for f in os.listdir(figures_in_work):
                            shutil.move(os.path.join(figures_in_work, f), os.path.join(images_dir, f))
                    
                    set_stage_frac("parse", 0.40, "parse")
                    cfg = load_config()
                    parse_api_key_val = cfg.get("parse_api_key", [""])
                    valid_keys = [k for k in parse_api_key_val if k]
                    api_key = random.choice(valid_keys) if valid_keys else ""
                    base_url = cfg.get("parse_api_url", "https://api.siliconflow.cn/v1")
                    model = cfg.get("parse_model", "Qwen/Qwen3-VL-235B-A22B-Thinking") 
                    
                    set_stage_frac("parse", 0.55, "parse")
                    bot = PaperReaderBot(api_key=api_key, base_url=base_url, model_name=model)
                    prompt = get_stage1_prompt(prompt_type, ppt_lang)
                    md_report = bot.get_stage1_md(pdf_path, prompt) 
                    
                    with open(kb_file, "w", encoding="utf-8") as f:
                         f.write(md_report)
                    set_stage_frac("parse", 1.0, "parse")
                    sys.path.pop(0)

                force_print("\n========== Step 1: Extract Figures & Gen Deep Parsing MD ==========")
                # Crawl parse progress while LLM runs (thread can't call set_stage mid-LLM easily)
                stop_parse = asyncio.Event()
                crawl_parse = asyncio.create_task(crawl_stage("parse", 0.55, 0.95, 120, stop_parse))
                try:
                    await asyncio.to_thread(parse_sync)
                finally:
                    stop_parse.set()
                    crawl_parse.cancel()
                set_stage_frac("parse", 1.0, "parse")
                force_print("[Parse] Completed successfully.")

            # Step 2: PPT and Annotate in parallel
            async def run_ppt():
                # Resume: keep a non-trivial pptx (blank ones are tiny / marked failed)
                sync_map = os.path.join(target_dir, "pptx", "slide_sync_map.json")
                if _file_ok(out_ppt, min_bytes=8000) and _file_ok(sync_map, min_bytes=8):
                    force_print(f"[PPT] Resume skip — presentation exists: {out_ppt}")
                    set_stage_frac("ppt", 1.0, "ppt")
                    return
                # Remove empty / failed previous pptx so UI doesn't treat as ready
                if os.path.isfile(out_ppt) and not _file_ok(out_ppt, min_bytes=8000):
                    try:
                        os.remove(out_ppt)
                        force_print("[PPT] Removed previous empty/failed PPTX before retry")
                    except OSError:
                        pass

                set_stage_frac("ppt", 0.08, "ppt")
                force_print(f"\n========== Step 3: Compiling PPTX ==========")
                ppt_script = os.path.join(base_dir, "backend", "standalone_pdf2ppt", "ppt_maker", "generate_full_ppt.js")
                figures_dir = os.path.join(target_dir, "images")
                cfg = load_config()
                parse_api_key_val = cfg.get("parse_api_key", [""])
                api_key = random.choice(parse_api_key_val) if parse_api_key_val else ""
                ppt_model = cfg.get("paper_model") or cfg.get("chat_model") or "Qwen/Qwen2.5-72B-Instruct"
                api_url = cfg.get("chat_api_url") or cfg.get("parse_api_url") or "https://api.siliconflow.cn/v1"
                
                cmd = [get_node_executable(), ppt_script, kb_file, figures_dir, out_ppt, ppt_mode, api_key, ppt_model, api_url, ppt_lang]
                cwd = os.path.join(base_dir, "backend", "standalone_pdf2ppt", "ppt_maker")
                
                stop_ev = asyncio.Event()
                crawl = asyncio.create_task(crawl_stage("ppt", 0.10, 0.92, 180, stop_ev))
                max_attempts = 8
                try:
                    for attempt in range(max_attempts):
                        try:
                            await run_subprocess("PPT Compiler", cmd, cwd=cwd)
                            break
                        except Exception as e:
                            if attempt < max_attempts - 1:
                                api_key = random.choice(parse_api_key_val) if parse_api_key_val else ""
                                cmd[6] = api_key
                                force_print(f"PPT Compilation failed: {e}. Retrying with key rotation ({attempt+2}/{max_attempts})...")
                                await asyncio.sleep(8)
                            else:
                                force_print(f"PPT Compilation permanently failed: {e}")
                                raise e
                finally:
                    stop_ev.set()
                    crawl.cancel()
                set_stage_frac("ppt", 1.0, "ppt")

            async def run_annotate():
                if _file_ok(annotated_pdf, min_bytes=1024):
                    force_print(f"[Annotate] Resume skip — annotated PDF exists: {annotated_pdf}")
                    set_stage_frac("annotate", 1.0, "annotate")
                    return
                set_stage_frac("annotate", 0.08, "annotate")
                force_print(f"\n========== Step 4: Generate Annotated PDF ==========")
                annotator_script = os.path.join(base_dir, "backend", "services", "pdf_annotator.py")
                # Copy md to work_dir so pdf_annotator can find it alongside raw pdf
                temp_md = os.path.join(work_dir, f"{book_name}_KnowledgeBase.md")
                if _file_ok(kb_file, min_bytes=50):
                    shutil.copy(kb_file, temp_md)
                stop_ev = asyncio.Event()
                crawl = asyncio.create_task(crawl_stage("annotate", 0.10, 0.92, 240, stop_ev))
                try:
                    await run_subprocess("Annotator", python_cmd_for_script(annotator_script, work_dir), book_name=book_name)
                    ann_in_work = os.path.join(work_dir, f"{book_name}_annotated.pdf")
                    if os.path.exists(ann_in_work):
                        shutil.move(ann_in_work, annotated_pdf)
                    json_in_work = os.path.join(work_dir, "annotations.json")
                    target_json = os.path.join(target_dir, "marked", "annotations.json")
                    if os.path.exists(json_in_work):
                        if os.path.exists(target_json):
                            os.remove(target_json)
                        shutil.move(json_in_work, target_json)
                    set_stage_frac("annotate", 1.0, "annotate")
                except Exception as e:
                    import traceback
                    force_print(f"Annotator failed: {repr(e)}")
                    traceback.print_exc()
                    set_stage_frac("annotate", 1.0, "annotate")
                finally:
                    stop_ev.set()
                    crawl.cancel()

            async def run_parse_and_downstream():
                try:
                    await run_parse()
                except Exception as e:
                    force_print(f"Parse failed, aborting downstream tasks: {e}")
                    return
                force_print("\n========== Phase 2: PPT & Annotate Parallel ==========")
                await asyncio.gather(run_ppt(), run_annotate(), return_exceptions=True)

            force_print("\n========== Pipeline Started (Optimized) ==========")
            
            translate_task = asyncio.create_task(run_translate())
            
            # Run parse -> ppt & annotate
            await run_parse_and_downstream()
            
            # Wait for translation if it hasn't finished yet, so active_tasks isn't cleared too early
            await translate_task

            # Brief 100% flash before cleanup
            active_tasks_progress[task_id] = {
                "percent": 100,
                "stage": progress_map[lang].get("finalize", "Done")
            }
            await asyncio.sleep(0.6)
            
            # Clean up work_dir
            try:
                # Do not delete raw pdf! work_dir is target_dir/raw. We only delete temp files inside it.
                temp_md = os.path.join(work_dir, f"{book_name}_KnowledgeBase.md")
                if os.path.exists(temp_md): os.remove(temp_md)
                figures_in_work = os.path.join(work_dir, "figures")
                if os.path.exists(figures_in_work): shutil.rmtree(figures_in_work, ignore_errors=True)
            except:
                pass
            
    except BaseException as e:
        import traceback
        err_str = traceback.format_exc()
        traceback.print_exc()
        force_print(f"Error running processing: {e}")
    finally:
        active_tasks.discard(task_id)
        active_tasks_progress.pop(task_id, None)

def submit_task(pdf_path: str, book_name: str, item_type: str, prompt_type: str = "提示词汇总", ppt_mode: str = "creative"):
    task_id = f"{item_type}s_{book_name}"
    if task_id not in active_tasks:
        active_tasks.add(task_id)
        # In a real FastAPI app, we can use BackgroundTasks, or asyncio.create_task
        # Because we might be calling this from a sync route if we don't await, we use create_task
        loop = asyncio.get_event_loop()
        loop.create_task(async_run_builder(pdf_path, book_name, item_type, prompt_type, ppt_mode))
