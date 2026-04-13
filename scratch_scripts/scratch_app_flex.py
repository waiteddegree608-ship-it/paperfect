import re

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix flex-shrink-0
pattern = r'className="relative bg-white shadow-2xl origin-center"'
replacement = 'className="relative bg-white shadow-2xl origin-center flex-shrink-0"'
content = content.replace(pattern, replacement)

# Fix subpixel layout by slightly expanding textEl widths or adding a white-space setting
# Actually, whiteSpace: textEl.maxWidth ? 'pre-wrap' : 'nowrap'
# we want pre-wrap, but we also want margin of safety for widths
old_style = "width: textEl.maxWidth ? `${textEl.maxWidth}px` : undefined"
new_style = "width: textEl.maxWidth ? `${textEl.maxWidth + 4}px` : undefined"

# we had TWO occurrences of the width logic in DOM
content = content.replace(old_style, new_style)

with open(app_tsx_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Patched App.tsx flex-shrink")
