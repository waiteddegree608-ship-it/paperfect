import re

main_py_path = r"E:\workspace\ddl\web_ui\main.py"

with open(main_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Add flipH and flipV extraction in export_json_for_pptx_main
pattern = r'(elif shape\.shape_type == MSO_SHAPE_TYPE\.LINE:.*?el\["style"\]\.update\(\{)(.*?)("stroke": stroke_color,)'

def replace_line_shape(m):
    return m.group(1) + """
                        "flipH": getattr(shape.element.spPr.xfrm, "flipH", False) if hasattr(shape.element, "spPr") and hasattr(shape.element.spPr, "xfrm") else False,
                        "flipV": getattr(shape.element.spPr.xfrm, "flipV", False) if hasattr(shape.element, "spPr") and hasattr(shape.element.spPr, "xfrm") else False,
                        """ + m.group(3)

content = re.sub(pattern, replace_line_shape, content, flags=re.DOTALL)

with open(main_py_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Added flipH/flipV to main.py endpoint")
