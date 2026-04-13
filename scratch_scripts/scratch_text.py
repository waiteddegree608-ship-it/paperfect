import re
import os

main_py_path = r"E:\workspace\ddl\web_ui\main.py"

with open(main_py_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Replace textAlign and add valign
# Find the font parsing block
pattern_text = r'(if shape\.has_text_frame:.*?)(font_size = 18.*?)(el\["style"\]\.update\(\{.*?"textAlign": )"left"(.*?\})'

def replace_text_style(m):
    return m.group(1) + m.group(2) + """
                    text_align = "left"
                    try:
                        if shape.text_frame.paragraphs:
                            align = shape.text_frame.paragraphs[0].alignment
                            if align == 2:
                                text_align = "center"
                            elif align == 3:
                                text_align = "right"
                    except:
                        pass
                    
                    valign = "top"
                    try:
                        anchor = getattr(shape.text_frame, 'vertical_anchor', None)
                        if anchor == 4:
                            valign = "middle"
                        elif anchor == 3:
                            valign = "bottom"
                    except:
                        pass
                    
                    """ + m.group(3) + """text_align,
                        "valign": valign""" + m.group(4)

new_content = re.sub(pattern_text, replace_text_style, content, flags=re.DOTALL)
if new_content != content:
    content = new_content
    print("Patched main.py for text_align and valign")
else:
    print("Failed to patch main.py text_align!")

with open(main_py_path, 'w', encoding='utf-8') as f:
    f.write(content)
