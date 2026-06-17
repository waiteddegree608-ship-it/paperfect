import os
import re
import fitz

class ProjectManager:
    def __init__(self, base_dir="projects"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)
        
    def create_project(self, project_name: str) -> str:
        safe_name = "".join([c for c in project_name if c.isalnum() or c in (' ', '-', '_')]).rstrip()
        proj_dir = os.path.join(self.base_dir, safe_name)
        os.makedirs(proj_dir, exist_ok=True)
        os.makedirs(os.path.join(proj_dir, "images"), exist_ok=True)
        return proj_dir
        
    def extract_semantic_figures(self, pdf_path: str, proj_dir: str):
        img_dir = os.path.join(proj_dir, "images")
        os.makedirs(img_dir, exist_ok=True)
        
        doc = fitz.open(pdf_path)
        try:
            # Match Figure X or Fig. X at the beginning of the text
            fig_pattern = re.compile(r"^\s*(?:Figure|Fig\.?)\s*(\d+)", re.IGNORECASE)
        
            for page_index in range(len(doc)):
                page = doc[page_index]
                blocks = page.get_text("dict")["blocks"]
                text_blocks = [b for b in blocks if getattr(b, "get", lambda x: None)("type") == 0]
                image_blocks = [b for b in blocks if getattr(b, "get", lambda x: None)("type") == 1]
            
                # Find the dominant font size on the page to identify main body paragraphs
                font_sizes = {}
                for tb in text_blocks:
                    for line in tb["lines"]:
                        for span in line["spans"]:
                            fs = round(span["size"])
                            font_sizes[fs] = font_sizes.get(fs, 0) + len(span["text"])
            
                if not font_sizes:
                    continue
                
                main_fs = max(font_sizes, key=font_sizes.get)
            
                for i, text_b in enumerate(text_blocks):
                    text_content = ""
                    for line in text_b["lines"]:
                        for span in line["spans"]:
                            text_content += span["text"] + " "
                    text_content = text_content.strip()
                
                    match = fig_pattern.search(text_content[:30])
                    if match:
                        fig_num = match.group(1)
                        caption_rect = fitz.Rect(text_b["bbox"])
                    
                        # Heuristic for full width: > 50% of page width
                        is_full_width = (caption_rect.width > page.rect.width * 0.5)
                    
                        # Filter for real body text blocks
                        real_body_blocks = []
                        for b in text_blocks:
                            r = fitz.Rect(b["bbox"])
                            if r.y1 > caption_rect.y0: continue
                            
                            char_count = 0
                            main_char_count = 0
                            for l in b["lines"]:
                                for s in l["spans"]:
                                    text = s["text"]
                                    char_count += len(text)
                                    if round(s["size"]) == main_fs: 
                                        main_char_count += len(text)
                            
                            # A real body block should have enough characters and mostly main font
                            if char_count > 40 and main_char_count / char_count > 0.8:
                                real_body_blocks.append(r)
                            
                        # Find the lowest body block above the caption that horizontally overlaps
                        above_blocks = sorted([
                            r for r in real_body_blocks 
                            if r.y1 <= caption_rect.y0 - 2 and 
                               max(0, min(r.x1, caption_rect.x1) - max(r.x0, caption_rect.x0)) > 20
                        ], key=lambda r: r.y1, reverse=True)

                        top_y = 60
                        if above_blocks:
                            top_y = above_blocks[0].y1 + 5
                    
                        # Determine if figure spans one or two columns
                        col_width = page.rect.width / 2
                        is_left_col = caption_rect.x1 < col_width + 50
                        is_right_col = caption_rect.x0 > col_width - 50
                        
                        if is_left_col and not is_right_col:
                            crop_rect = fitz.Rect(20, top_y, col_width + 10, caption_rect.y0)
                        elif is_right_col and not is_left_col:
                            crop_rect = fitz.Rect(col_width - 10, top_y, page.rect.width - 20, caption_rect.y0)
                        else:
                            crop_rect = fitz.Rect(20, top_y, page.rect.width - 20, caption_rect.y0)
                    
                        if top_y >= caption_rect.y0 - 15: 
                            continue # Invalid extraction, figure is too small

                        crop_rect = crop_rect.intersect(page.rect)
                    
                        if crop_rect.height < 50:
                            continue
                        
                        # Extract high quality pixmap
                        try:
                            pix_crop = page.get_pixmap(dpi=300, clip=crop_rect)
                        except TypeError:
                            # Fallback for older PyMuPDF versions
                            pix_crop = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=crop_rect)
                        
                        filename = f"Figure_{fig_num}.png"
                        # Only save to images directory
                        img_path = os.path.join(img_dir, filename)
                        pix_crop.save(img_path)
                    
                        print(f"[ProjectManager] Extracted SMART layout figure {filename} on page {page_index+1} (Size: {pix_crop.width}x{pix_crop.height})")
                        
        finally:
            # release file lock
            try:
                doc.close()
            except:
                pass

if __name__ == "__main__":
    pm = ProjectManager(base_dir=r"E:\workspace\reader\projects")
    pm.extract_semantic_figures(r"E:\workspace\reader\测试\计算机+人工智能\FashionTex.pdf", pm.create_project("FashionTex"))