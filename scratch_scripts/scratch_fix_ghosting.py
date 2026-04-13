import re

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Fix the early return to include draggingHandle
pattern1 = r'if \(!isDrawing && !draggingElementId\) return;'
replacement1 = 'if (!isDrawing && !draggingElementId && !draggingHandle) return;'
content = content.replace(pattern1, replacement1)

# 2. Fix the state accumulation jumping bug by using functional updates AND a pointer ref
# We must introduce a ref for tracking last pointer coordinates to avoid stale closures with dx/dy.
if 'const lastPointerRef = useRef<{x: number, y: number} | null>(null);' not in content:
    ref_anchor = "const [startPoint, setStartPoint] = useState({ x: 0, y: 0 });"
    ref_inject = "const [startPoint, setStartPoint] = useState({ x: 0, y: 0 });\n  const lastPointerRef = useRef<{x: number, y: number} | null>(null);"
    content = content.replace(ref_anchor, ref_inject)

# In handlePointerDown / handleElementPointerDown, initialize the ref
down1 = "setStartPoint({ x, y });"
down1_inject = "setStartPoint({ x, y });\n      lastPointerRef.current = { x, y };"
# We'll just replace all occurrences of `setStartPoint({ x, y });` if they aren't already followed by the ref assignment
content = re.sub(r'setStartPoint\(\{ x, y \}\);\s*(?!lastPointerRef)', r'setStartPoint({ x, y }); lastPointerRef.current = { x, y };\n      ', content)

# In handlePointerMove, rebuild the draggingElementId block to use prev and lastPointerRef
move_anchor = r'\} else if \(draggingElementId\) \{.*?\setStartPoint\(\{ x, y \}\); \s*\}'
# We have to be careful not to rely on regex matching the whole block easily
# Let's rebuild the handlePointerMove draggingElementId logic
old_block = """    } else if (draggingElementId) {
      setElements(elements.map(el => {
        if (el.id === draggingElementId) {
          if (el.type === 'text') return { ...el, x: x - dragOffset.x, y: y - dragOffset.y };
          if (el.type === 'arrow') {
            const dx = x - startPoint.x; const dy = y - startPoint.y;
            return {
              ...el, startX: el.startX + dx, startY: el.startY + dy,
              endX: el.endX + dx, endY: el.endY + dy
            };
          }
        }
        return el;
      }));
      setStartPoint({ x, y }); 
    }"""

new_block = """    } else if (draggingElementId) {
      if (lastPointerRef.current) {
         const dx = x - lastPointerRef.current.x;
         const dy = y - lastPointerRef.current.y;
         setElements(prev => prev.map(el => {
           if (el.id === draggingElementId) {
             if (el.type === 'text') return { ...el, x: x - dragOffset.x, y: y - dragOffset.y };
             if (el.type === 'arrow') {
               return {
                 ...el, startX: el.startX + dx, startY: el.startY + dy,
                 endX: el.endX + dx, endY: el.endY + dy
               };
             }
           }
           return el;
         }));
         lastPointerRef.current = { x, y };
      }
    }"""

content = content.replace(old_block, new_block)

# Also fix the draggingHandle to use functional `prev =>` state update to be completely immune to ghosting
old_handle_block = """    } else if (draggingHandle) {
      setElements(elements.map(el => {
        if (el.id === draggingHandle.id && el.type === 'arrow') {
          if (draggingHandle.type === 'start') {
             return { ...el, startX: x, startY: y };
          } else {
             return { ...el, endX: x, endY: y };
          }
        }
        return el;
      }));
    }"""

new_handle_block = """    } else if (draggingHandle) {
      setElements(prev => prev.map(el => {
        if (el.id === draggingHandle.id && el.type === 'arrow') {
          if (draggingHandle.type === 'start') {
             return { ...el, startX: x, startY: y };
          } else {
             return { ...el, endX: x, endY: y };
          }
        }
        return el;
      }));
    }"""
content = content.replace(old_handle_block, new_handle_block)


# Write back
with open(app_tsx_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched pointer jumping and handle return")
