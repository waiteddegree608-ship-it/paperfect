import re

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, "r", encoding="utf-8") as f:
    content = f.read()

# Fix the JSON parsing block for text
pattern_text_push = r"(newEls\.push\(\{[^\{\}]*?type: 'text',[^\{\}]*?maxWidth: Math\.round\(el\.size\.width \* SCALE\)\s*\}\);)"

def replace_text_push(m):
    orig = m.group(1)
    return orig.replace("maxWidth: Math.round(el.size.width * SCALE)\n                   });", """maxWidth: Math.round(el.size.width * SCALE),
                     maxHeight: Math.round(el.size.height * SCALE),
                     textAlign: el.style?.textAlign || 'left',
                     valign: el.style?.valign || 'top'
                   });""")

content = re.sub(pattern_text_push, replace_text_push, content, flags=re.DOTALL)


# Fix the DOM rendering
text_align_fix = """style={{ 
                         color: textEl.color, 
                         fontSize: `${textEl.fontSize}px`, 
                         fontWeight: 'bold', 
                         textAlign: (textEl as any).textAlign || 'left',
                         display: 'flex',
                         flexDirection: 'column',
                         justifyContent: (textEl as any).valign === 'middle' ? 'center' : ((textEl as any).valign === 'bottom' ? 'flex-end' : 'flex-start'),
                         height: (textEl as any).maxHeight ? `${(textEl as any).maxHeight}px` : 'auto',
                         textShadow: '0 1px 2px rgba(255,255,255,0.8)', 
                         width: textEl.maxWidth ? `${textEl.maxWidth}px` : undefined, 
                         whiteSpace: textEl.maxWidth ? 'pre-wrap' : 'nowrap', 
                         wordBreak: textEl.maxWidth ? 'break-all' : 'normal' 
                      }}"""

old_style = r"style=\{\{ color: textEl\.color, fontSize: `\$\{textEl\.fontSize\}px`, fontWeight: 'bold', textShadow: '0 1px 2px rgba\(255,255,255,0\.8\)', width: textEl\.maxWidth \? `\$\{textEl\.maxWidth\}px` : undefined, whiteSpace: textEl\.maxWidth \? 'pre-wrap' : 'nowrap', wordBreak: textEl\.maxWidth \? 'break-word' : 'normal' \}\}"

content = re.sub(old_style, text_align_fix, content)

outer_style_old = r"style=\{\{ left: textEl\.x, top: textEl\.y \}\}"
outer_style_new = "style={{ left: textEl.x, top: textEl.y, width: textEl.maxWidth ? `${textEl.maxWidth}px` : undefined, height: (textEl as any).maxHeight ? `${(textEl as any).maxHeight}px` : undefined }}"

content = content.replace(outer_style_old, outer_style_new)


with open(app_tsx_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched App.tsx text alignment and rendering!")
