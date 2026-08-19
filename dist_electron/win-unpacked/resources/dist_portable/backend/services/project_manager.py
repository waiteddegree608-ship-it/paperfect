import os
import re
import json
import fitz


class ProjectManager:
    def __init__(self, base_dir="projects"):
        self.base_dir = os.path.abspath(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def create_project(self, project_name: str) -> str:
        safe_name = "".join([c for c in project_name if c.isalnum() or c in (" ", "-", "_")]).rstrip()
        proj_dir = os.path.join(self.base_dir, safe_name)
        os.makedirs(proj_dir, exist_ok=True)
        os.makedirs(os.path.join(proj_dir, "images"), exist_ok=True)
        return proj_dir

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _union_rects(rects):
        if not rects:
            return None
        u = fitz.Rect(rects[0])
        for r in rects[1:]:
            u |= fitz.Rect(r)
        return u

    @staticmethod
    def _h_overlap(a: fitz.Rect, b: fitz.Rect) -> float:
        return max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))

    @staticmethod
    def _expand(rect: fitz.Rect, pad: float, page_rect: fitz.Rect) -> fitz.Rect:
        r = fitz.Rect(rect.x0 - pad, rect.y0 - pad, rect.x1 + pad, rect.y1 + pad)
        return r & page_rect

    def _collect_graphic_rects(self, page) -> list:
        """Collect raster image rects + sizable vector drawing rects on a page."""
        rects = []
        # Raster images
        try:
            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    for r in page.get_image_rects(xref):
                        rr = fitz.Rect(r)
                        if rr.get_area() > 80:
                            rects.append(rr)
                except Exception:
                    pass
        except Exception:
            pass

        # Vector drawings (common for architecture diagrams)
        try:
            for d in page.get_drawings():
                rr = fitz.Rect(d.get("rect"))
                if rr.is_empty or rr.get_area() < 120:
                    continue
                # Skip full-page background-ish strokes
                if rr.width > page.rect.width * 0.95 and rr.height > page.rect.height * 0.95:
                    continue
                rects.append(rr)
        except Exception:
            pass

        # Also type=1 image blocks from text dict (some PDFs only expose here)
        try:
            for b in page.get_text("dict").get("blocks", []):
                if b.get("type") == 1:
                    rr = fitz.Rect(b["bbox"])
                    if rr.get_area() > 80:
                        rects.append(rr)
        except Exception:
            pass

        return rects

    def _column_mode(self, caption: fitz.Rect, page_rect: fitz.Rect) -> str:
        """Return 'full' | 'left' | 'right' based on caption geometry."""
        pw = page_rect.width
        mid = page_rect.x0 + pw / 2
        cap_w = caption.width
        cap_cx = (caption.x0 + caption.x1) / 2
        # Full-width caption (or nearly)
        if cap_w > pw * 0.52:
            return "full"
        if cap_cx < mid - 8:
            return "left"
        if cap_cx > mid + 8:
            return "right"
        return "full"

    def _filter_by_column(self, rects, mode: str, page_rect: fitz.Rect, caption: fitz.Rect):
        if mode == "full":
            return list(rects)
        mid = page_rect.x0 + page_rect.width / 2
        out = []
        for r in rects:
            cx = (r.x0 + r.x1) / 2
            if mode == "left" and cx <= mid + 15:
                out.append(r)
            elif mode == "right" and cx >= mid - 15:
                out.append(r)
            # Also keep if strong horizontal overlap with caption
            elif self._h_overlap(r, caption) > min(r.width, caption.width) * 0.35:
                out.append(r)
        return out or list(rects)

    def _cluster_near_caption(self, graphic_rects, caption: fitz.Rect, page_rect: fitz.Rect, mode: str):
        """
        Build crop rect from graphics that sit above the caption and belong
        to the same column / multi-panel figure band.
        """
        # Above (or slightly overlapping) the caption
        above = [
            r for r in graphic_rects
            if r.y0 < caption.y0 + 8 and r.y1 <= caption.y1 + 2
            and r.y1 > caption.y0 - page_rect.height  # on same page band
        ]
        # Prefer those not far above (same figure region): within ~55% page height
        near = [r for r in above if caption.y0 - r.y0 < page_rect.height * 0.55]
        pool = near if near else above
        pool = self._filter_by_column(pool, mode, page_rect, caption)
        if not pool:
            return None

        # Seed: graphics closest above caption with h-overlap
        seeded = [
            r for r in pool
            if self._h_overlap(r, caption) > 15 or mode == "full"
        ]
        if not seeded:
            seeded = sorted(pool, key=lambda r: caption.y0 - r.y1)[:6]

        # Grow cluster: include neighbors that touch/near the union (multi-panel)
        cluster = list(seeded)
        changed = True
        while changed:
            changed = False
            u = self._union_rects(cluster)
            if u is None:
                break
            for r in pool:
                if any(r.irect == c.irect for c in cluster):
                    continue
                # proximity to current union
                gap_x = max(0, max(u.x0 - r.x1, r.x0 - u.x1))
                gap_y = max(0, max(u.y0 - r.y1, r.y0 - u.y1))
                if gap_x < 28 and gap_y < 36:
                    cluster.append(r)
                    changed = True
                elif self._h_overlap(r, u) > 20 and gap_y < 50:
                    cluster.append(r)
                    changed = True

        u = self._union_rects(cluster)
        if u is None:
            return None
        # Padding: more horizontal for multi-panel half-column figures
        pad_x = 14 if mode != "full" else 16
        pad_y_top = 8
        # Keep room for (a)(b)(c) sub-captions sitting between drawings and main "Figure N" line
        bottom = min(caption.y0 - 2, u.y1 + 32)
        crop = fitz.Rect(u.x0 - pad_x, u.y0 - pad_y_top, u.x1 + pad_x, bottom)
        return crop & page_rect

    def _heuristic_text_crop(self, page, text_blocks, caption: fitz.Rect, mode: str, main_fs: int):
        """Fallback when no graphic rects found — improved column-aware band."""
        page_rect = page.rect
        mid = page_rect.x0 + page_rect.width / 2

        real_body = []
        for b in text_blocks:
            r = fitz.Rect(b["bbox"])
            if r.y1 > caption.y0 - 2:
                continue
            char_count = 0
            main_char = 0
            for line in b.get("lines", []):
                for s in line.get("spans", []):
                    t = s.get("text") or ""
                    char_count += len(t)
                    if round(s.get("size", 0)) == main_fs:
                        main_char += len(t)
            if char_count > 40 and main_char / max(char_count, 1) > 0.75:
                real_body.append(r)

        # Same-column body blocks only for half-width figures
        def in_col(r):
            if mode == "full":
                return True
            cx = (r.x0 + r.x1) / 2
            if mode == "left":
                return cx <= mid + 20
            return cx >= mid - 20

        above = sorted(
            [
                r
                for r in real_body
                if in_col(r)
                and r.y1 <= caption.y0 - 2
                and (mode == "full" or self._h_overlap(r, caption) > 12)
            ],
            key=lambda r: r.y1,
            reverse=True,
        )

        top_y = page_rect.y0 + 48
        if above:
            # Don't jump over a large gap (that would swallow half the page of text)
            candidate = above[0].y1 + 4
            if caption.y0 - candidate < page_rect.height * 0.5:
                top_y = candidate
            else:
                # large gap → only take a reasonable band above caption
                top_y = max(page_rect.y0 + 40, caption.y0 - page_rect.height * 0.42)

        if mode == "left":
            crop = fitz.Rect(page_rect.x0 + 16, top_y, mid + 6, caption.y0 - 1)
        elif mode == "right":
            crop = fitz.Rect(mid - 6, top_y, page_rect.x1 - 16, caption.y0 - 1)
        else:
            crop = fitz.Rect(page_rect.x0 + 16, top_y, page_rect.x1 - 16, caption.y0 - 1)
        return crop & page_rect

    def extract_semantic_figures(self, pdf_path: str, proj_dir: str):
        """
        Extract paper figures with caption-aware, column-aware crops.

        Priority:
          1) Union of raster images + vector drawings above each "Figure N" caption
          2) Multi-panel cluster growth (fixes half-width / multi-panel cuts)
          3) Text-block heuristic fallback (improved vs old full-page swallow)
        """
        img_dir = os.path.join(proj_dir, "images")
        os.makedirs(img_dir, exist_ok=True)
        metadata = {}

        doc = fitz.open(pdf_path)
        try:
            fig_pattern = re.compile(r"^\s*(?:Figure|Fig\.?)\s*(\d+)", re.IGNORECASE)

            for page_index in range(len(doc)):
                page = doc[page_index]
                page_rect = page.rect
                blocks = page.get_text("dict").get("blocks", [])
                text_blocks = [b for b in blocks if b.get("type") == 0]

                graphic_rects = self._collect_graphic_rects(page)

                # Dominant body font size
                font_sizes = {}
                for tb in text_blocks:
                    for line in tb.get("lines", []):
                        for span in line.get("spans", []):
                            fs = round(span.get("size") or 0)
                            font_sizes[fs] = font_sizes.get(fs, 0) + len(span.get("text") or "")
                if not font_sizes:
                    continue
                main_fs = max(font_sizes, key=font_sizes.get)

                for text_b in text_blocks:
                    text_content = ""
                    for line in text_b.get("lines", []):
                        for span in line.get("spans", []):
                            text_content += (span.get("text") or "") + " "
                    text_content = text_content.strip()
                    match = fig_pattern.search(text_content[:40])
                    if not match:
                        continue

                    fig_num = match.group(1)
                    caption_rect = fitz.Rect(text_b["bbox"])
                    mode = self._column_mode(caption_rect, page_rect)

                    crop_rect = self._cluster_near_caption(
                        graphic_rects, caption_rect, page_rect, mode
                    )
                    method = "graphics-cluster"
                    if crop_rect is None or crop_rect.height < 40 or crop_rect.width < 40:
                        crop_rect = self._heuristic_text_crop(
                            page, text_blocks, caption_rect, mode, main_fs
                        )
                        method = "text-heuristic"

                    if crop_rect is None:
                        continue
                    crop_rect = crop_rect & page_rect
                    if crop_rect.height < 40 or crop_rect.width < 40:
                        continue
                    # Reject absurd full-page-ish crops that are mostly body text
                    if crop_rect.height > page_rect.height * 0.72 and method == "text-heuristic":
                        # tighten to lower band above caption
                        tight_top = max(crop_rect.y0, caption_rect.y0 - page_rect.height * 0.38)
                        crop_rect = fitz.Rect(crop_rect.x0, tight_top, crop_rect.x1, crop_rect.y1) & page_rect
                        if crop_rect.height < 40:
                            continue

                    try:
                        pix_crop = page.get_pixmap(dpi=300, clip=crop_rect)
                    except TypeError:
                        pix_crop = page.get_pixmap(matrix=fitz.Matrix(4, 4), clip=crop_rect)

                    filename = f"Figure_{fig_num}.png"
                    img_path = os.path.join(img_dir, filename)
                    # Prefer larger / more complete extraction if re-encountered
                    new_area = pix_crop.width * pix_crop.height
                    if os.path.exists(img_path):
                        try:
                            from PIL import Image as _PILImage
                            with _PILImage.open(img_path) as _im:
                                old_area = _im.size[0] * _im.size[1]
                            if old_area >= new_area * 0.95:
                                continue
                        except Exception:
                            pass
                    pix_crop.save(img_path)
                    metadata[filename] = {
                        "page": page_index + 1,
                        "column": mode,
                        "method": method,
                        "bbox": [crop_rect.x0, crop_rect.y0, crop_rect.x1, crop_rect.y1],
                    }
                    print(
                        f"[ProjectManager] Extracted {filename} p{page_index+1} "
                        f"{mode}/{method} {pix_crop.width}x{pix_crop.height}"
                    )

            meta_path = os.path.join(img_dir, "figures_metadata.json")
            # Keep backward-compatible flat page map + rich meta
            flat = {}
            for k, v in metadata.items():
                flat[k] = v["page"] if isinstance(v, dict) else v
            with open(meta_path, "w", encoding="utf-8") as f_meta:
                json.dump({"pages": flat, "details": metadata}, f_meta, indent=2, ensure_ascii=False)
            # Also write simple map for older consumers that expect {Figure_1.png: page}
            with open(os.path.join(img_dir, "figures_metadata_simple.json"), "w", encoding="utf-8") as f_s:
                json.dump(flat, f_s, indent=2)
            # Overwrite figures_metadata.json with simple form for ppt_router compat
            # ppt_router expects {filename: page_number}
            with open(meta_path, "w", encoding="utf-8") as f_meta:
                json.dump(flat, f_meta, indent=2, ensure_ascii=False)
            # Save details alongside
            with open(os.path.join(img_dir, "figures_extract_details.json"), "w", encoding="utf-8") as f_d:
                json.dump(metadata, f_d, indent=2, ensure_ascii=False)
            print(f"[ProjectManager] Saved figures metadata ({len(flat)} figures)")

        finally:
            try:
                doc.close()
            except Exception:
                pass


if __name__ == "__main__":
    pm = ProjectManager(base_dir=r"E:\workspace\reader\projects")
    pm.extract_semantic_figures(
        r"E:\workspace\reader\测试\计算机+人工智能\FashionTex.pdf",
        pm.create_project("FashionTex"),
    )
