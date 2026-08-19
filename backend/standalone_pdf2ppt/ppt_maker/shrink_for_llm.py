# coding=utf-8
"""Shrink an image to a JPEG data-URL for VL prompts (stdout)."""
import base64
import sys

import fitz

path = sys.argv[1]
max_edge = int(sys.argv[2]) if len(sys.argv) > 2 else 768
quality = int(sys.argv[3]) if len(sys.argv) > 3 else 65

doc = fitz.open(path)
page = doc[0]
pix = page.get_pixmap(alpha=False)
scale = min(1.0, float(max_edge) / max(pix.width, pix.height, 1))
if scale < 0.98:
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
jpg = pix.tobytes("jpeg")
doc.close()
sys.stdout.write("data:image/jpeg;base64," + base64.b64encode(jpg).decode("ascii"))
