import re

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, "r", encoding="utf-8") as f:
    content = f.read()

# Make text boxes transparent to mouse if not selecting or text editing
pattern_pointer = r'className=`absolute pointer-events-auto group \$\{currentTool === \'select\' \? \'cursor-move\' : \'\'\}`'
new_pointer = "className={`absolute group ${currentTool === 'select' ? 'cursor-move pointer-events-auto' : currentTool === 'text' ? 'pointer-events-auto cursor-text' : 'pointer-events-none'}`}"

content = content.replace(pattern_pointer, new_pointer)

with open(app_tsx_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched App.tsx pointer events")
