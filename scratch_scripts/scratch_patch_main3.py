import re

main_py_path = r"E:\workspace\ddl\web_ui\main.py"

with open(main_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the greedy has_text_frame in export_json_for_pptx_main
# we want to only count it as text if it has ANY text, OR if it's NOT a line/auto shape.
# Actually, let's just reverse the order: check for PICTURE, LINE, AUTO_SHAPE FIRST, then text!
# Or we can just change "if shape.has_text_frame:" to "if shape.has_text_frame and shape.text.strip():"

# Let's see the exact text:
pattern = r'(\s+if shape\.has_text_frame:)(\s*el\["type"\] = "text")'

def replacement(m):
    return m.group(1).replace("if shape.has_text_frame:", "if shape.has_text_frame and shape.text.strip():") + m.group(2)

new_content = re.sub(pattern, replacement, content, count=1)

with open(main_py_path, 'w', encoding='utf-8') as f:
    f.write(new_content)
print("Patched main.py")
