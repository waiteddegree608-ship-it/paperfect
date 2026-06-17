import os
import fitz
import json
import tempfile
import argparse
import subprocess
from llm_client import PaperReaderBot
from prompts import get_stage1_prompt
from project_manager import ProjectManager

def main():
    parser = argparse.ArgumentParser(description="Standalone Paper PDF to Summary MD & PPTX Processor")
    parser.add_argument("pdf_path", help="Path to the research paper PDF")
    parser.add_argument("--api_key", required=True, help="SiliconFlow or OpenAI API Key")
    parser.add_argument("--base_url", default="https://api.siliconflow.cn/v1", help="API Base URL")
    parser.add_argument("--mode", default="creative", choices=["simple", "creative"], help="PPT Generation mode")
    parser.add_argument("--model", default="Qwen/Qwen3-VL-235B-A22B-Thinking", help="LLM for MD extraction")
    args = parser.parse_args()

    pdf_path = os.path.abspath(args.pdf_path)
    if not os.path.exists(pdf_path):
        print(f"Error: {pdf_path} not found.")
        return

    proj_name = os.path.splitext(os.path.basename(pdf_path))[0]
    proj_dir = os.path.abspath(os.path.join("projects", proj_name))
    os.makedirs(proj_dir, exist_ok=True)
    figures_dir = os.path.join(proj_dir, "figures")
    
    print(f"========== Step 1: Extracting Figures from PDF ==========")
    pm = ProjectManager(base_dir="projects")
    pm.extract_semantic_figures(pdf_path, proj_dir)

    print(f"\n========== Step 2: Generaing Deep Summary MD ==========")
    bot = PaperReaderBot(api_key=args.api_key, base_url=args.base_url, model_name=args.model)
    prompt = get_stage1_prompt()
    
    # We only need the first stage text output. Our PaperReaderBot parses the PDF natively.
    md_report = bot.get_stage1_md(pdf_path, prompt) # Custom hook, ignoring stage 2 & 3
    
    md_file_path = os.path.join(proj_dir, f"输出结果_{proj_name}.md")
    with open(md_file_path, "w", encoding="utf-8") as f:
        f.write(md_report)
    print(f"MD Report saved to {md_file_path}")

    print(f"\n========== Step 3: Compiling PPTX ==========")
    ppt_script = os.path.abspath(os.path.join("ppt_maker", "generate_full_ppt.js"))
    out_ppt = os.path.join(proj_dir, f"{proj_name}_Presentation[{args.mode}].pptx")
    
    subprocess.run([
        "node", ppt_script, 
        md_file_path, 
        figures_dir, 
        out_ppt, 
        args.mode, 
        args.api_key
    ], check=True)
    
    print(f"\n========== DONE! ==========")
    print(f"Find your files in: {proj_dir}")

if __name__ == "__main__":
    main()
