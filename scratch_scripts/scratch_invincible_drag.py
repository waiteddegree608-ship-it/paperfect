import re

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, "r", encoding="utf-8") as f:
    content = f.read()

# Replace the native mouse/touch event listeners on the SVG handles with robust Pointer events + setPointerCapture
# and a large transparent hit target for Fitts's law.

old_circles = r'(<circle cx=\{arrow\.startX\} cy=\{arrow\.startY\} r="8" fill="#fff".*?/>\s*<circle cx=\{arrow\.endX\} cy=\{arrow\.endY\} r="8" fill="#fff".*?/>)'

new_circles = """<g 
                          className="pointer-events-auto cursor-crosshair"
                          onPointerDown={(e) => { 
                            e.stopPropagation(); 
                            if (currentTool === 'select') { 
                              (e.target as Element).setPointerCapture(e.pointerId);
                              setDraggingHandle({ id: arrow.id, type: 'start' }); 
                            } 
                          }}
                          onPointerMove={(e) => {
                            if (draggingHandle?.id === arrow.id && draggingHandle.type === 'start') {
                               const rect = canvasRef.current?.getBoundingClientRect();
                               if (!rect) return;
                               const x = (e.clientX - rect.left) / viewScale;
                               const y = (e.clientY - rect.top) / viewScale;
                               setElements(prev => prev.map(el => (el.id === arrow.id && el.type === 'arrow') ? { ...el, startX: x, startY: y } : el));
                            }
                          }}
                          onPointerUp={(e) => {
                             (e.target as Element).releasePointerCapture(e.pointerId);
                             setDraggingHandle(null);
                          }}
                        >
                          <circle cx={arrow.startX} cy={arrow.startY} r="25" fill="transparent" />
                          <circle cx={arrow.startX} cy={arrow.startY} r="8" fill="#fff" stroke="#3b82f6" strokeWidth="2" className="pointer-events-none hover:scale-125 transition-transform" />
                        </g>

                        <g 
                          className="pointer-events-auto cursor-crosshair"
                          onPointerDown={(e) => { 
                            e.stopPropagation(); 
                            if (currentTool === 'select') { 
                              (e.target as Element).setPointerCapture(e.pointerId);
                              setDraggingHandle({ id: arrow.id, type: 'end' }); 
                            } 
                          }}
                          onPointerMove={(e) => {
                            if (draggingHandle?.id === arrow.id && draggingHandle.type === 'end') {
                               const rect = canvasRef.current?.getBoundingClientRect();
                               if (!rect) return;
                               const x = (e.clientX - rect.left) / viewScale;
                               const y = (e.clientY - rect.top) / viewScale;
                               setElements(prev => prev.map(el => (el.id === arrow.id && el.type === 'arrow') ? { ...el, endX: x, endY: y } : el));
                            }
                          }}
                          onPointerUp={(e) => {
                             (e.target as Element).releasePointerCapture(e.pointerId);
                             setDraggingHandle(null);
                          }}
                        >
                          <circle cx={arrow.endX} cy={arrow.endY} r="25" fill="transparent" />
                          <circle cx={arrow.endX} cy={arrow.endY} r="8" fill="#fff" stroke="#3b82f6" strokeWidth="2" className="pointer-events-none hover:scale-125 transition-transform" />
                        </g>"""

content = re.sub(old_circles, new_circles, content, flags=re.DOTALL)

with open(app_tsx_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Applied invincible pointer capture drag targets")
