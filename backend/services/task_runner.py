import os
import sys
import asyncio
import shutil
import random
from backend.core.config import get_base_dir, load_config
from backend.services.file_manager import active_tasks

async def run_subprocess(name, cmd, cwd=None):
    print(f"[{name}] Starting: {' '.join(cmd)}")
    process = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        print(f"[{name}] Error ({process.returncode}):\n{stderr.decode('utf-8', errors='ignore')}")
        raise RuntimeError(f"{name} failed with exit code {process.returncode}")
    print(f"[{name}] Completed successfully.")
    return stdout.decode('utf-8', errors='ignore')

async def async_run_builder(pdf_path: str, book_name: str, item_type: str, prompt_type: str = "提示词汇总", ppt_mode: str = "creative"):
    task_id = f"{item_type}s_{book_name}"
    try:
        if item_type == "book":
            script_path = os.path.join(get_base_dir(), "universal_kb_builder.py")
            await run_subprocess("Book Builder", [sys.executable, script_path, pdf_path])
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

            # Step 1: Translate and Parse in parallel
            async def run_translate():
                script_path = os.path.join(base_dir, "tools", "paper_translator.py")
                await run_subprocess("Translate", [sys.executable, script_path, pdf_path, translated_pdf])

            async def run_parse():
                # We need to run the python code for parsing.
                # Since llm_client and project_manager are quite tied, we will wrap it in a function here
                # but to avoid blocking the event loop, we run it in an executor, or call a wrapper script.
                # For simplicity, we create a temporary wrapper or run it using asyncio.to_thread
                def parse_sync():
                    import sys
                    sys.path.insert(0, os.path.join(base_dir, "standalone_pdf2ppt"))
                    from project_manager import ProjectManager
                    from llm_client import PaperReaderBot
                    from prompts import get_stage1_prompt
                    
                    pm = ProjectManager(base_dir=target_dir)
                    # Extract to global images folder
                    images_dir = os.path.join(target_dir, "images")
                    os.makedirs(images_dir, exist_ok=True)
                    # For compatibility, we use work_dir for extraction then move
                    pm.extract_semantic_figures(pdf_path, work_dir)
                    
                    cfg = load_config()
                    parse_api_key_val = cfg.get("parse_api_key", [""])
                    valid_keys = [k for k in parse_api_key_val if k]
                    api_key = random.choice(valid_keys) if valid_keys else ""
                    base_url = cfg.get("parse_api_url", "https://api.siliconflow.cn/v1")
                    model = cfg.get("parse_model", "Qwen/Qwen3-VL-235B-A22B-Thinking") 
                    
                    bot = PaperReaderBot(api_key=api_key, base_url=base_url, model_name=model)
                    prompt = get_stage1_prompt(prompt_type)
                    md_report = bot.get_stage1_md(pdf_path, prompt) 
                    
                    with open(kb_file, "w", encoding="utf-8") as f:
                        f.write(md_report)
                    shutil.copy(kb_file, parsed_md)
                    sys.path.pop(0)

                print("\n========== Step 1: Extract Figures & Gen Deep Parsing MD ==========")
                await asyncio.to_thread(parse_sync)
                print("[Parse] Completed successfully.")

            print("\n========== Phase 1: Translate & Parse Parallel ==========")
            await asyncio.gather(run_translate(), run_parse())

            # Step 2: PPT and Annotate in parallel
            async def run_ppt():
                print(f"\n========== Step 3: Compiling PPTX ==========")
                ppt_script = os.path.join(base_dir, "standalone_pdf2ppt", "ppt_maker", "generate_full_ppt.js")
                # Need to pass figures_dir, but project_manager puts them in work_dir/figures
                figures_dir = os.path.join(work_dir, "figures")
                cfg = load_config()
                parse_api_key_val = cfg.get("parse_api_key", [""])
                api_key = random.choice(parse_api_key_val) if parse_api_key_val else ""
                
                cmd = ["node", ppt_script, kb_file, figures_dir, out_ppt, ppt_mode, api_key]
                cwd = os.path.join(base_dir, "standalone_pdf2ppt", "ppt_maker")
                
                for attempt in range(3):
                    try:
                        await run_subprocess("PPT Compiler", cmd, cwd=cwd)
                        break
                    except Exception as e:
                        if attempt < 2:
                            print(f"PPT Compilation failed: {e}. Retrying ({attempt+2}/3)...")
                            await asyncio.sleep(2)
                        else:
                            raise e

            async def run_annotate():
                print(f"\n========== Step 4: Generate Annotated PDF ==========")
                annotator_script = os.path.join(base_dir, "tools", "pdf_annotator.py")
                # pdf_annotator.py expects work_dir
                await run_subprocess("Annotator", [sys.executable, annotator_script, work_dir])
                
                ann_in_work = os.path.join(work_dir, f"{book_name}_annotated.pdf")
                if os.path.exists(ann_in_work):
                    shutil.move(ann_in_work, annotated_pdf)

            print("\n========== Phase 2: PPT & Annotate Parallel ==========")
            await asyncio.gather(run_ppt(), run_annotate())
            
            # Clean up work_dir
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
            except:
                pass
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error running processing: {e}")
    finally:
        active_tasks.discard(task_id)

def submit_task(pdf_path: str, book_name: str, item_type: str, prompt_type: str = "提示词汇总", ppt_mode: str = "creative"):
    task_id = f"{item_type}s_{book_name}"
    if task_id not in active_tasks:
        active_tasks.add(task_id)
        # In a real FastAPI app, we can use BackgroundTasks, or asyncio.create_task
        # Because we might be calling this from a sync route if we don't await, we use create_task
        loop = asyncio.get_event_loop()
        loop.create_task(async_run_builder(pdf_path, book_name, item_type, prompt_type, ppt_mode))
