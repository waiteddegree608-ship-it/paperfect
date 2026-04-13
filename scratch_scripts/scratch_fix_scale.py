import re
import os

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update the JSON parser block inside useEffect
fetch_logic_old_pattern = r"const parsedSlides: SlideData\[\] = json\.slides\.map\(\(s: any\) => \{.*?(?=return { slideImage: sImg, elements: newEls };)"

fetch_logic_new = """const parsedSlides: SlideData[] = json.slides.map((s: any) => {
             let sImg: SlideImage | null = null;
             const newEls: CanvasElement[] = [];
             const SCALE = 1280 / 960; // Convert 96 DPI backend points to 128 DPI canvas coords
             
             s.elements.forEach((el: any) => {
                if (el.type === 'image' && !sImg) {
                   sImg = {
                     data: el.content,
                     intrinsicWidth: el.size.width * SCALE,
                     intrinsicHeight: el.size.height * SCALE,
                     x: Math.round(el.position.x * SCALE),
                     y: Math.round(el.position.y * SCALE),
                     width: Math.round(el.size.width * SCALE),
                     height: Math.round(el.size.height * SCALE)
                   };
                } else if (el.type === 'text') {
                   newEls.push({
                     id: el.id || Math.random().toString(36).substr(2, 9),
                     type: 'text',
                     x: Math.round(el.position.x * SCALE),
                     y: Math.round(el.position.y * SCALE),
                     text: el.content || '',
                     color: el.style?.color || '#000000',
                     fontSize: Math.round((el.style?.fontSize || 18) * SCALE),
                     isEditing: false,
                     isSelected: false,
                     maxWidth: Math.round(el.size.width * SCALE)
                   });
                } else if (el.type === 'shape' && (el.content === 'arrow' || el.content === 'line')) {
                   const sx = el.position.x * SCALE;
                   const sy = el.position.y * SCALE;
                   const ew = el.size.width * SCALE;
                   const eh = el.size.height * SCALE;
                   
                   // Approximate mapping from bounding box to arrow coordinates
                   // without flipH/flipV data, assume top-left to bottom-right
                   newEls.push({
                      id: el.id || Math.random().toString(36).substr(2, 9),
                      type: 'arrow',
                      startX: sx,
                      startY: sy,
                      endX: sx + ew,
                      endY: sy + eh,
                      color: el.style?.stroke || '#3b82f6',
                      width: el.style?.strokeWidth || 3,
                      isSelected: false
                   });
                }
             });
             
             """

if re.search(fetch_logic_old_pattern, content, re.DOTALL):
    content = re.sub(fetch_logic_old_pattern, fetch_logic_new, content, flags=re.DOTALL)
else:
    print("Could not find the parser block!")
    exit(1)

with open(app_tsx_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated App.tsx scale and arrow parsing")
