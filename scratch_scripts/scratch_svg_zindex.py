import re

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, "r", encoding="utf-8") as f:
    content = f.read()

pattern_svg = r'<svg className="absolute inset-0 w-full h-full pointer-events-none" style=\{\{ zIndex: 10 \}\}>'
new_svg = '<svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 30 }}>'

content = content.replace(pattern_svg, new_svg)

with open(app_tsx_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched SVG zIndex!")
