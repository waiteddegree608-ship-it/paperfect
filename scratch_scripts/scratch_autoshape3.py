import os

main_py_path = r"E:\workspace\ddl\web_ui\main.py"

with open(main_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Let's cleanly replace the AUTO_SHAPE block in export_json_for_pptx_main
# Find export_json_for_pptx_main
start_main = content.find('async def export_json_for_pptx_main')
end_main = content.find('async def export_json_for_ppt_master')

main_func = content[start_main:end_main]

# Fix the AUTO_SHAPE block inside main_func ONLY
target = """                elif shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
                    el["type"] = "shape"
                    shape_val = "rectangle"
                    try:
                        ast = getattr(shape, 'auto_shape_type', None)
                        if ast in (33, 34, 35, 36): # Arrow types
                            shape_val = "arrow"
                    except:
                        pass
                        
                    el["content"] = shape_val"""

replacement = """                elif shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE:
                    el["type"] = "shape"
                    shape_val = "rectangle"
                    try:
                        ast = getattr(shape, 'auto_shape_type', None)
                        if ast in (33, 34, 35, 36) or ast == 9: # Arrow types
                            shape_val = "arrow"
                    except:
                        if hasattr(shape, 'element') and 'prst="line"' in shape.element.xml:
                            shape_val = "line"
                        elif hasattr(shape, 'element') and 'prst="triangle"' in shape.element.xml:
                            shape_val = "triangle"
                        
                    el["content"] = shape_val
                    if shape_val in ("line", "arrow"):
                        try:
                            el["style"]["flipH"] = bool(shape.element.xpath('.//a:xfrm/@flipH') and shape.element.xpath('.//a:xfrm/@flipH')[0] == '1')
                            el["style"]["flipV"] = bool(shape.element.xpath('.//a:xfrm/@flipV') and shape.element.xpath('.//a:xfrm/@flipV')[0] == '1')
                        except:
                            pass"""

main_func = main_func.replace(target, replacement)

# Re-assemble
content = content[:start_main] + main_func + content[end_main:]

with open(main_py_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Patched main.py via strict block replacement")
