import re

main_py_path = r"E:\workspace\ddl\web_ui\main.py"

with open(main_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Make it completely robust utilizing xpath
pattern = r'(elif shape\.shape_type == MSO_SHAPE_TYPE\.LINE:.*?el\["style"\]\.update\(\{)(.*?)("stroke": stroke_color,)'

def replace_line_shape(m):
    return m.group(1) + """
                        "flipH": bool(shape.element.xpath('.//a:xfrm/@flipH') and shape.element.xpath('.//a:xfrm/@flipH')[0] == '1'),
                        "flipV": bool(shape.element.xpath('.//a:xfrm/@flipV') and shape.element.xpath('.//a:xfrm/@flipV')[0] == '1'),
                        """ + m.group(3)

content = re.sub(pattern, replace_line_shape, content, flags=re.DOTALL)

with open(main_py_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated main.py")
