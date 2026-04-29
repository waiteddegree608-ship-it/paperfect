import re

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, "r", encoding="utf-8") as f:
    content = f.read()

# Add the useState for draggingHandle
if 'const [draggingHandle, setDraggingHandle]' not in content:
    state_anchor = "const [draggingElementId, setDraggingElementId] = useState<string | null>(null);"
    state_inject = "const [draggingElementId, setDraggingElementId] = useState<string | null>(null);\n  const [draggingHandle, setDraggingHandle] = useState<{ id: string, type: 'start' | 'end' } | null>(null);"
    content = content.replace(state_anchor, state_inject)

# Update handlePointerMove
pointer_move_anchor = "} else if (draggingElementId) {"
pointer_move_inject = """} else if (draggingHandle) {
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
    } else if (draggingElementId) {"""
content = content.replace(pointer_move_anchor, pointer_move_inject)

# Update handlePointerUp
pointer_up_anchor = "setDraggingElementId(null);"
pointer_up_inject = "setDraggingElementId(null);\n    setDraggingHandle(null);"
content = content.replace(pointer_up_anchor, pointer_up_inject)

# Update SVG handles
svg_handles_old = r'<circle cx=\{arrow\.startX\} cy=\{arrow\.startY\} r="5" fill="#fff" stroke="#3b82f6" strokeWidth="2" className="pointer-events-none" />\s*<circle cx=\{arrow\.endX\} cy=\{arrow\.endY\} r="5" fill="#fff" stroke="#3b82f6" strokeWidth="2" className="pointer-events-none" />'

svg_handles_new = """<circle cx={arrow.startX} cy={arrow.startY} r="8" fill="#fff" stroke="#3b82f6" strokeWidth="2" className="pointer-events-auto cursor-crosshair hover:scale-125 transition-transform" onMouseDown={(e) => { e.stopPropagation(); if (currentTool === 'select') setDraggingHandle({ id: arrow.id, type: 'start' }); }} onTouchStart={(e) => { e.stopPropagation(); if (currentTool === 'select') setDraggingHandle({ id: arrow.id, type: 'start' }); }} />
                      <circle cx={arrow.endX} cy={arrow.endY} r="8" fill="#fff" stroke="#3b82f6" strokeWidth="2" className="pointer-events-auto cursor-crosshair hover:scale-125 transition-transform" onMouseDown={(e) => { e.stopPropagation(); if (currentTool === 'select') setDraggingHandle({ id: arrow.id, type: 'end' }); }} onTouchStart={(e) => { e.stopPropagation(); if (currentTool === 'select') setDraggingHandle({ id: arrow.id, type: 'end' }); }} />"""

content = re.sub(svg_handles_old, svg_handles_new, content)

with open(app_tsx_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Patched handle handlers!")
