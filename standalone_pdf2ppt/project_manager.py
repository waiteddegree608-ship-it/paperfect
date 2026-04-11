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
        out_dir = os.path.join(proj_dir, "figures")
        img_dir = os.path.join(proj_dir, "images")
        os.makedirs(out_dir, exist_ok=True)
        os.makedirs(img_dir, exist_ok=True)
        doc = fitz.open(pdf_path)
        
        # Match Figure X or Fig. X
        fig_pattern = re.compile(r"(?:Figure|Fig\.?)\s*(\d+)", re.IGNORECASE)
        
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
                    
                    # Filter for real body text blocks (to ignore vector text inside charts)
                    # A block is body text if it has at least 2 lines OR its font matches main font exactly
                    # AND it is not the header metadata
                    body_blocks = []
                    for b in text_blocks:
                        if text_b["bbox"] == b["bbox"]: continue # Skip the caption itself
                        
                        b_rect = fitz.Rect(b["bbox"])
                        if b_rect.y1 > caption_rect.y0: continue # Skip text below caption
                        
                        is_body = False
                        if len(b["lines"]) >= 2:
                            is_body = True
                        else:
                            for l in b["lines"]:
                                for s in l["spans"]:
                                    if round(s["size"]) == main_fs:
                                        is_body = True
                                        
                        # Ignore header/footer (y < 60)
                        if b_rect.y0 < 60:
                            is_body = False
                            
                        if is_body:
                            body_blocks.append(b_rect)
                            
                    # Use full width for all figures safely
                    top_y = 60 # top margin
                    
                    above_blocks = [r for r in body_blocks if r.y1 <= caption_rect.y0 - 2]
                    if above_blocks:
                        top_y = max(r.y1 for r in above_blocks)
                    
                    # CRITICAL FIX: If there are raster images between top_y and caption, 
                    # the figure must encompass them! This fixes cases where vector text masqueraded as body text
                    figure_image_blocks = [fitz.Rect(b["bbox"]) for b in image_blocks if b.get('type') == 1]
                    for img_rect in figure_image_blocks:
                        # If this image is part of the figure (sits above caption)
                        if img_rect.y1 <= caption_rect.y0 + 50:
                            if img_rect.y0 < top_y and img_rect.y0 > 60: # Must be higher than the false top_y
                                top_y = min(top_y, img_rect.y0)
                    
                    # Extra padding to include the highest parts of the figure
                    top_y = top_y - 5
                    
                    # Set full width bounds (margin to margin) for simplicity and robust capture
                    crop_rect = fitz.Rect(30, top_y, page.rect.width - 30, caption_rect.y0)
                    
                    if top_y >= caption_rect.y0 - 20: 
                        continue # Invalid extraction

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
                    out_path = os.path.join(out_dir, filename)
                    pix_crop.save(out_path)
                    
                    # Copy to images dir for annotation processing
                    import shutil
                    img_path = os.path.join(img_dir, filename)
                    shutil.copy(out_path, img_path)
                    
                    print(f"[ProjectManager] Extracted SMART layout figure {filename} on page {page_index+1} (Size: {pix_crop.width}x{pix_crop.height})")
                    
        # release file lock
        try:
            doc.close()
        except:
            pass

if __name__ == "__main__":
    pm = ProjectManager(base_dir=r"E:\workspace\reader\projects")
    pm.extract_semantic_figures(r"E:\workspace\reader\测试\计算机+人工智能\FashionTex.pdf", pm.create_project("FashionTex"))
