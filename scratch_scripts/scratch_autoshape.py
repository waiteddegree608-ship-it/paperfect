import re
import os

main_py_path = r"E:\workspace\ddl\web_ui\main.py"

with open(main_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace the AUTO_SHAPE block in export_json_for_pptx_main
pattern_shape = r'(elif shape\.shape_type == MSO_SHAPE_TYPE\.AUTO_SHAPE:.*?shape_val = "rectangle"\n)(.*?)(el\["content"\] = shape_val)'

def replace_autoshape(m):
    return m.group(1) + """                    try:
                        ast = getattr(shape, 'auto_shape_type', None)
                        if ast in (33, 34, 35, 36) or ast == 9: # Arrow types or Line
                            shape_val = "arrow"
                    except:
                        if hasattr(shape, 'element') and 'prst="line"' in shape.element.xml:
                            shape_val = "line"
                    
                    if shape_val in ("line", "arrow"):
                        el["style"]["flipH"] = bool(shape.element.xpath('.//a:xfrm/@flipH') and shape.element.xpath('.//a:xfrm/@flipH')[0] == '1')
                        el["style"]["flipV"] = bool(shape.element.xpath('.//a:xfrm/@flipV') and shape.element.xpath('.//a:xfrm/@flipV')[0] == '1')
                    """ + m.group(3)

new_content = re.sub(pattern_shape, replace_autoshape, content, count=1, flags=re.DOTALL)

with open(main_py_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Patched main.py auto_shapes")
