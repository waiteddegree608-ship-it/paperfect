import re

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update the shape/arrow mapping
old_arrow_logic = r"""} else if \(el\.type === 'shape' && \(el\.content === 'arrow' \|\| el\.content === 'line'\)\) \{
                   const sx = el\.position\.x \* SCALE;
                   const sy = el\.position\.y \* SCALE;
                   const ew = el\.size\.width \* SCALE;
                   const eh = el\.size\.height \* SCALE;
                   
                   // Approximate mapping from bounding box to arrow coordinates
                   // without flipH/flipV data, assume top-left to bottom-right
                   newEls\.push\(\{
                      id: el\.id \|\| Math\.random\(\)\.toString\(36\)\.substr\(2, 9\),
                      type: 'arrow',
                      startX: sx,
                      startY: sy,
                      endX: sx \+ ew,
                      endY: sy \+ eh,
                      color: el\.style\?\.stroke \|\| '#3b82f6',
                      width: el\.style\?\.strokeWidth \|\| 3,
                      isSelected: false
                   \}\);
                \}"""

new_arrow_logic = """} else if (el.type === 'shape' && (el.content === 'arrow' || el.content === 'line')) {
                   const sx = el.position.x * SCALE;
                   const sy = el.position.y * SCALE;
                   const ew = el.size.width * SCALE;
                   const eh = el.size.height * SCALE;
                   
                   const flipH = el.style?.flipH;
                   const flipV = el.style?.flipV;
                   
                   let startX = sx;
                   let endX = sx + ew;
                   let startY = sy;
                   let endY = sy + eh;
                   
                   if (flipH) { startX = sx + ew; endX = sx; }
                   if (flipV) { startY = sy + eh; endY = sy; }

                   newEls.push({
                      id: el.id || Math.random().toString(36).substr(2, 9),
                      type: 'arrow',
                      startX,
                      startY,
                      endX,
                      endY,
                      color: el.style?.stroke || '#3b82f6',
                      width: el.style?.strokeWidth || 3,
                      isSelected: false
                   });
                }"""

content = re.sub(old_arrow_logic, new_arrow_logic, content)

# 2. Fix the overflow: 'hidden' truncation
content = content.replace("overflow: 'hidden'", "overflow: 'visible'")

with open(app_tsx_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Updated App.tsx with flipH/flipV and overflow: visible")
