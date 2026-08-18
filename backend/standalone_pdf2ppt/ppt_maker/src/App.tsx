import React, { useState, useRef, useEffect } from 'react';
import { 
  MousePointer2, 
  ArrowRight, 
  Type, 
  Trash2, 
  MonitorPlay,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Undo2,
  Redo2,
  Copy,
  Minus,
  Plus,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';

type Tool = 'select' | 'arrow' | 'text';

interface BaseElement { id: string; type: string; isSelected?: boolean; }
interface ArrowElement extends BaseElement {
  type: 'arrow';
  startX: number; startY: number; endX: number; endY: number;
  color: string; width: number;
  /** true for figure-to-card connectors (no triangle arrowhead) */
  noHead?: boolean;
}
interface TextElement extends BaseElement {
  type: 'text';
  x: number; y: number; text: string; color: string; fontSize: number;
  isEditing: boolean; maxWidth?: number; maxHeight?: number;
  textAlign?: string; valign?: string;
  fontWeight?: string | number; fontFamily?: string;
  /** Callout card chrome — matches PowerPoint text-on-shape */
  fill?: string; stroke?: string; strokeWidth?: number; borderRadius?: number;
}
type CanvasElement = ArrowElement | TextElement;

interface SlideImage {
  data: string;
  intrinsicWidth: number;
  intrinsicHeight: number;
  x: number;
  y: number;
  width: number;
  height: number;
}


interface SlideData {
  slideImage: SlideImage | null;
  elements: CanvasElement[];
}

// -------------------------------------------------------------
// -------------------------------------------------------------
// STANDARDIZED CANVAS DIMENSIONS (16:9 Aspect Ratio)
const SLIDE_WIDTH = 1280;
const SLIDE_HEIGHT = 720;
// -------------------------------------------------------------

const App: React.FC = () => {

  const [allSlides, setAllSlides] = useState<SlideData[]>([]);
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0);

  const [slideImage, setSlideImage] = useState<SlideImage | null>(null);
  const [elements, setElements] = useState<CanvasElement[]>([]);

  const [currentTool, setCurrentTool] = useState<Tool>('select');
  const [isDrawing, setIsDrawing] = useState(false);
  const [activeColor, setActiveColor] = useState('#3b82f6');
  const [activeFontSize, setActiveFontSize] = useState(16);
  const [activeStrokeWidth, setActiveStrokeWidth] = useState(2);
  const [history, setHistory] = useState<CanvasElement[][]>([]);
  const [future, setFuture] = useState<CanvasElement[][]>([]);
  
  const [viewScale, setViewScale] = useState(1);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLDivElement>(null);
  
  const [, setStartPoint] = useState({ x: 0, y: 0 });
  const lastPointerRef = useRef<{x: number, y: number} | null>(null);
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 });
  const [draggingElementId, setDraggingElementId] = useState<string | null>(null);
  const [draggingHandle, setDraggingHandle] = useState<{ id: string, type: 'start' | 'end' } | null>(null);

  const colors = ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ffffff', '#000000'];

  // Sync light/dark chrome with Paperfect parent theme (Cyan Light etc.)
  useEffect(() => {
    const applyTheme = () => {
      const theme = localStorage.getItem('theme') || '';
      const isLight = theme.includes('light') || theme === 'cyan-light';
      document.documentElement.classList.toggle('theme-light', isLight);
      document.body.classList.toggle('theme-light', isLight);
      if (theme) document.body.setAttribute('data-theme', theme);
    };
    applyTheme();
    window.addEventListener('storage', applyTheme);
    // Parent may set theme after iframe load
    const t = window.setInterval(applyTheme, 800);
    return () => {
      window.removeEventListener('storage', applyTheme);
      window.clearInterval(t);
    };
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const book = params.get('book');
    if (!book) return;

    const fetchPpt = async () => {
      try {
        // Same-origin when embedded under FastAPI (port 8900). Only Vite dev (8081) needs absolute backend URL.
        const isViteDev = window.location.port === '8081';
        const apiUrl = isViteDev
          ? `http://${window.location.hostname}:8900/api/ppt_export_json/${encodeURIComponent(book)}`
          : `/api/ppt_export_json/${encodeURIComponent(book)}`;
        const res = await fetch(apiUrl);
        if (!res.ok) {
          console.error('PPT export HTTP', res.status, await res.text());
          return;
        }
        const json = await res.json();
        if (json.error) {
          console.error('PPT export error:', json.error);
          alert(json.error);
          return;
        }
        
        if (json.slides && json.slides.length > 0) {
          const parsedSlides: SlideData[] = json.slides.map((s: any) => {
             let sImg: SlideImage | null = null;
             const newEls: CanvasElement[] = [];
             const SCALE = 1280 / 960; // Convert 96 DPI backend points to 128 DPI canvas coords
             
             s.elements.forEach((el: any) => {
                if (el.type === 'image' && !sImg) {
                   sImg = {
                     data: el.content,
                     intrinsicWidth: el.size.width * SCALE,
                     intrinsicHeight: el.size.height * SCALE,
                     x: Math.round(el.position.x * SCALE),
                     y: Math.round(el.position.y * SCALE),
                     width: Math.round(el.size.width * SCALE),
                     height: Math.round(el.size.height * SCALE)
                   };
                } else if (el.type === 'text') {
                   newEls.push({
                     id: el.id || Math.random().toString(36).substr(2, 9),
                     type: 'text',
                     x: Math.round(el.position.x * SCALE),
                     y: Math.round(el.position.y * SCALE),
                     text: el.content || '',
                     color: el.style?.color || '#0F172A',
                     fontSize: Math.round((el.style?.fontSize || 14) * SCALE),
                     isEditing: false,
                     isSelected: false,
                     maxWidth: Math.round(el.size.width * SCALE),
                     maxHeight: Math.round(el.size.height * SCALE),
                     textAlign: el.style?.textAlign || 'left',
                     valign: el.style?.valign || 'top',
                     fontWeight: el.style?.fontWeight || (el.style?.fill ? 'normal' : 'bold'),
                     fontFamily: el.style?.fontFamily || 'Calibri, Segoe UI, sans-serif',
                     fill: el.style?.fill,
                     stroke: el.style?.stroke,
                     strokeWidth: el.style?.strokeWidth,
                     borderRadius: el.style?.borderRadius,
                   } as TextElement);
                } else if (el.type === 'shape' && (el.content === 'arrow' || el.content === 'line')) {
                   const sx = el.position.x * SCALE;
                   const sy = el.position.y * SCALE;
                   const ew = el.size.width * SCALE;
                   const eh = el.size.height * SCALE;
                   
                   const flipH = el.style?.flipH;
                   const flipV = el.style?.flipV;
                   
                   let startX = sx;
                   let endX = sx + ew;
                   let startY = sy;
                   let endY = sy + eh;
                   
                   if (flipH) { startX = sx + ew; endX = sx; }
                   if (flipV) { startY = sy + eh; endY = sy; }

                   const isLine = el.content === 'line' || el.style?.noHead;
                   newEls.push({
                      id: el.id || Math.random().toString(36).substr(2, 9),
                      type: 'arrow',
                      startX,
                      startY,
                      endX,
                      endY,
                      // connectors use muted slate, not default bright blue
                      color: el.style?.stroke || (isLine ? '#64748B' : '#3b82f6'),
                      width: el.style?.strokeWidth || (isLine ? 1.5 : 3),
                      noHead: !!isLine,
                      isSelected: false
                   } as ArrowElement);
                } else if (el.type === 'shape' && (el.content === 'ellipse' || el.content === 'roundRect' || el.content === 'rectangle')) {
                   // On-figure numbered badges are ellipse shapes (fill) + separate text in PPTX.
                   // Without importing the ellipse, only a hard-to-see white digit remains.
                   const isEllipse = el.content === 'ellipse';
                   const fill = el.style?.fill && el.style.fill !== 'transparent' ? el.style.fill : (isEllipse ? '#1E40AF' : undefined);
                   const stroke = el.style?.stroke || (isEllipse ? '#FFFFFF' : undefined);
                   newEls.push({
                     id: el.id || Math.random().toString(36).substr(2, 9),
                     type: 'text',
                     x: Math.round(el.position.x * SCALE),
                     y: Math.round(el.position.y * SCALE),
                     text: '',
                     color: '#FFFFFF',
                     fontSize: Math.max(10, Math.round(Math.min(el.size.width, el.size.height) * SCALE * 0.45)),
                     isEditing: false,
                     isSelected: false,
                     maxWidth: Math.round(el.size.width * SCALE),
                     maxHeight: Math.round(el.size.height * SCALE),
                     textAlign: 'center',
                     valign: 'middle',
                     fontWeight: 'bold',
                     fontFamily: 'Calibri, Segoe UI, sans-serif',
                     fill,
                     stroke,
                     strokeWidth: el.style?.strokeWidth || (isEllipse ? 1.5 : 1),
                     borderRadius: isEllipse ? 999 : (el.content === 'roundRect' ? 12 : 0),
                   } as TextElement);
                }
             });

             // Merge empty badge circles with overlapping short number labels (1–99)
             const merged: CanvasElement[] = [];
             const used = new Set<string>();
             const texts = newEls.filter((e): e is TextElement => e.type === 'text');
             for (const t of texts) {
               if (used.has(t.id)) continue;
               const label = (t.text || '').trim();
               const isNum = /^\d{1,2}$/.test(label);
               if (isNum && !t.fill) {
                 const tw = t.maxWidth || 24;
                 const th = t.maxHeight || 24;
                 const mate = texts.find(o =>
                   o.id !== t.id &&
                   !used.has(o.id) &&
                   !(o.text || '').trim() &&
                   !!o.fill &&
                   (o.borderRadius === 999 || (o.borderRadius != null && o.borderRadius > 50)) &&
                   Math.abs(o.x - t.x) < Math.max(tw, o.maxWidth || 0) * 0.6 &&
                   Math.abs(o.y - t.y) < Math.max(th, o.maxHeight || 0) * 0.6
                 );
                 if (mate) {
                   used.add(mate.id);
                   used.add(t.id);
                   merged.push({
                     ...mate,
                     text: label,
                     color: t.color && t.color.toLowerCase() !== '#000000' ? t.color : '#FFFFFF',
                     fontSize: t.fontSize || mate.fontSize,
                     fontWeight: 'bold',
                     textAlign: 'center',
                     valign: 'middle',
                     maxWidth: mate.maxWidth || tw,
                     maxHeight: mate.maxHeight || th,
                   });
                   continue;
                 }
               }
               if (!used.has(t.id)) {
                 used.add(t.id);
                 merged.push(t);
               }
             }
             for (const e of newEls) {
               if (e.type !== 'text' && !used.has(e.id)) merged.push(e);
             }
             
             return { slideImage: sImg, elements: merged };
          });
          
          setAllSlides(parsedSlides);
          if (parsedSlides.length > 0) {
            setSlideImage(parsedSlides[0].slideImage);
            setElements(parsedSlides[0].elements);
          }
          if (json.page_mapping) {
            window.parent.postMessage({
              type: 'PPT_MAPPING_LOADED',
              page_mapping: json.page_mapping
            }, '*');
          }
        }
      } catch (err) {
        console.error("Failed to load PPT", err);
      }
    };
    fetchPpt();
  }, []);

  // Save current slide state to allSlides when switching
  const saveCurrentSlide = () => {
    setAllSlides(prev => {
       const newSlides = [...prev];
       if (newSlides[currentSlideIndex]) {
          newSlides[currentSlideIndex].slideImage = slideImage;
          newSlides[currentSlideIndex].elements = elements.map(el => ({...el, isSelected: false, isEditing: false}));
       }
       return newSlides;
    });
  };

  const switchSlide = (newIndex: number, preventReverseSync: boolean = false) => {
    if (newIndex < 0 || newIndex >= allSlides.length) return;
    saveCurrentSlide();
    setCurrentSlideIndex(newIndex);
    // Timeout to ensure state commits before loading next to prevent race conditions
    setTimeout(() => {
       setAllSlides(prev => {
          setSlideImage(prev[newIndex].slideImage);
          setElements(prev[newIndex].elements);
          return prev;
       });
    }, 0);

    // Broadcast the slide index change event to the parent
    if (!preventReverseSync) {
      window.parent.postMessage({
        type: 'SLIDE_CHANGED_BY_USER',
        slideIndex: newIndex
      }, '*');
    }
  };

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data && event.data.type === 'SELECT_SLIDE_BY_INDEX') {
        const index = parseInt(event.data.index, 10);
        if (!isNaN(index) && index >= 0 && index < allSlides.length && index !== currentSlideIndex) {
          switchSlide(index, true); // True to prevent reverse sync loop
        }
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [allSlides, currentSlideIndex]);


  useEffect(() => {
    const handlePreventScroll = (e: Event) => {
      if (document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        e.preventDefault();
      }
    }
    const canvas = canvasRef.current;
    if (canvas) canvas.addEventListener('touchmove', handlePreventScroll, { passive: false });
    return () => { if (canvas) canvas.removeEventListener('touchmove', handlePreventScroll); };
  }, []);

  // Fit fixed 1280×720 canvas into workspace (no outer page scroll)
  useEffect(() => {
    const handleResize = () => {
      if (workspaceRef.current) {
        const workspaceRect = workspaceRef.current.getBoundingClientRect();
        const pad = 24;
        const availableW = Math.max(120, workspaceRect.width - pad);
        const availableH = Math.max(120, workspaceRect.height - pad);
        const scale = Math.min(availableW / SLIDE_WIDTH, availableH / SLIDE_HEIGHT);
        setViewScale(Math.max(0.12, Math.min(scale, 1.25)));
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [slideImage, allSlides.length]);

  const pushHistory = (next: CanvasElement[]) => {
    setHistory(h => [...h.slice(-40), elements.map(e => ({ ...e } as CanvasElement))]);
    setFuture([]);
    setElements(next);
  };

  const undo = () => {
    if (!history.length) return;
    const prev = history[history.length - 1];
    setFuture(f => [elements.map(e => ({ ...e } as CanvasElement)), ...f].slice(0, 40));
    setHistory(h => h.slice(0, -1));
    setElements(prev);
  };

  const redo = () => {
    if (!future.length) return;
    const next = future[0];
    setHistory(h => [...h, elements.map(e => ({ ...e } as CanvasElement))]);
    setFuture(f => f.slice(1));
    setElements(next);
  };

  const duplicateSelected = () => {
    const selected = elements.filter(el => el.isSelected);
    if (!selected.length) return;
    const clones = selected.map(el => {
      if (el.type === 'text') {
        const t = el as TextElement;
        return { ...t, id: generateId(), x: t.x + 16, y: t.y + 16, isSelected: true, isEditing: false };
      }
      const a = el as ArrowElement;
      return {
        ...a,
        id: generateId(),
        startX: a.startX + 16,
        startY: a.startY + 16,
        endX: a.endX + 16,
        endY: a.endY + 16,
        isSelected: true,
      };
    });
    pushHistory([
      ...elements.map(el => ({ ...el, isSelected: false } as CanvasElement)),
      ...clones as CanvasElement[],
    ]);
  };

  const bumpFontSize = (delta: number) => {
    setActiveFontSize(s => Math.min(48, Math.max(10, s + delta)));
    const next = elements.map(el => {
      if (el.isSelected && el.type === 'text') {
        const t = el as TextElement;
        return { ...t, fontSize: Math.min(48, Math.max(10, (t.fontSize || 16) + delta)) };
      }
      return el;
    });
    if (next.some((el, i) => el !== elements[i])) pushHistory(next);
  };

  const bumpStroke = (delta: number) => {
    setActiveStrokeWidth(s => Math.min(8, Math.max(1, s + delta)));
    const next = elements.map(el => {
      if (el.isSelected && el.type === 'arrow') {
        const a = el as ArrowElement;
        return { ...a, width: Math.min(8, Math.max(1, (a.width || 2) + delta)) };
      }
      return el;
    });
    if (next.some((el, i) => el !== elements[i])) pushHistory(next);
  };

  const generateId = () => Math.random().toString(36).substr(2, 9);

  const getCanvasCoordinates = (e: React.MouseEvent | React.TouchEvent) => {
    if (!canvasRef.current) return { x: 0, y: 0 };
    const rect = canvasRef.current.getBoundingClientRect();
    
    let clientX, clientY;
    if ('touches' in e) { clientX = e.touches[0].clientX; clientY = e.touches[0].clientY; }
    else { clientX = (e as React.MouseEvent).clientX; clientY = (e as React.MouseEvent).clientY; }
    
    // Divide by viewScale to convert screen pixels into 1280x720 canvas coordinates!
    return {
      x: (clientX - rect.left) / viewScale,
      y: (clientY - rect.top) / viewScale
    };
  };

  const handlePointerDown = (e: React.MouseEvent | React.TouchEvent) => {
    if ((e.target as HTMLElement).tagName === 'INPUT' || (e.target as HTMLElement).tagName === 'TEXTAREA') return;

    const { x, y } = getCanvasCoordinates(e);
    
    if ((e.target as HTMLElement).id === 'slide-background' || (e.target as HTMLElement).id === 'slide-image') {
      setElements(elements.map(el => ({ ...el, isSelected: false })));
    }

    if (currentTool === 'arrow') {
      setIsDrawing(true);
      setStartPoint({ x, y }); lastPointerRef.current = { x, y };
      const newArrow: ArrowElement = {
        id: generateId(), type: 'arrow',
        startX: x, startY: y, endX: x, endY: y,
        color: activeColor, width: activeStrokeWidth,
        isSelected: false
      };
      pushHistory([...elements.map(el => ({ ...el, isSelected: false })), newArrow]);
    } else if (currentTool === 'text') {
      const newText: TextElement = {
        id: generateId(), type: 'text',
        x, y: y - activeFontSize / 2,
        text: '', color: activeColor, fontSize: activeFontSize,
        isEditing: true, isSelected: true
      };
      pushHistory([...elements.map(el => ({ ...el, isSelected: false })), newText]);
      setCurrentTool('select');
    }
  };

  const handlePointerMove = (e: React.MouseEvent | React.TouchEvent) => {
    if (!isDrawing && !draggingElementId && !draggingHandle) return;
    const { x, y } = getCanvasCoordinates(e);

    if (isDrawing && currentTool === 'arrow') {
      setElements(elements.map((el, idx) => {
        if (idx === elements.length - 1 && el.type === 'arrow') return { ...el, endX: x, endY: y };
        return el;
      }));
    } else if (draggingHandle) {
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
    } else if (draggingElementId) {
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
    }
  };

  const handlePointerUp = () => {
    if (isDrawing && currentTool === 'arrow') {
      const lastElement = elements[elements.length - 1] as ArrowElement;
      if (lastElement) {
        const dx = lastElement.endX - lastElement.startX;
        const dy = lastElement.endY - lastElement.startY;
        if (Math.sqrt(dx * dx + dy * dy) < 5) setElements(elements.slice(0, -1));
      }
    }
    setIsDrawing(false);
    setDraggingElementId(null);
    setDraggingHandle(null);
  };

  const handleElementPointerDown = (e: React.MouseEvent | React.TouchEvent, id: string) => {
    e.stopPropagation();
    if (currentTool !== 'select') return;
    
    const { x, y } = getCanvasCoordinates(e);
    setStartPoint({ x, y }); lastPointerRef.current = { x, y };
      const element = elements.find(el => el.id === id);
    if (element) {
      if (element.type === 'text') setDragOffset({ x: x - element.x, y: y - element.y });
      setDraggingElementId(id);
      
      setElements(prev => prev.map(el => ({
        ...el, isSelected: el.id === id,
        ...(el.id === id && el.type === 'text' && ('detail' in e && (e as React.MouseEvent).detail === 2) ? { isEditing: true } : {})
      })));
    }
  };

  const handleTextChange = (id: string, newText: string) => {
    setElements(prev => prev.map(el => el.id === id && el.type === 'text' ? { ...el, text: newText } : el));
  };

  const finishTextEditing = (id: string) => {
    setElements(prev => prev.map(el => {
      if (el.id === id && el.type === 'text') {
        if (el.text.trim() === '') return null as any; 
        return { ...el, isEditing: false };
      }
      return el;
    }).filter(Boolean));
  };

  const deleteSelected = () => {
    if (!elements.some(el => el.isSelected)) return;
    pushHistory(elements.filter(el => !el.isSelected));
  };

  useEffect(() => {
    const handleGlobalKeyDown = (e: globalThis.KeyboardEvent) => {
      if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') {
        return;
      }
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo(); return; }
      if (mod && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) { e.preventDefault(); redo(); return; }
      if (mod && e.key === 'd') { e.preventDefault(); duplicateSelected(); return; }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        deleteSelected();
      } else if (e.key === 'ArrowLeft') {
        switchSlide(currentSlideIndex - 1);
      } else if (e.key === 'ArrowRight') {
        switchSlide(currentSlideIndex + 1);
      } else if (e.key === 'v' || e.key === 'V') {
        setCurrentTool('select');
      } else if (e.key === 'a' || e.key === 'A') {
        setCurrentTool('arrow');
      } else if (e.key === 't' || e.key === 'T') {
        setCurrentTool('text');
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [elements, currentSlideIndex, allSlides.length, history, future]);

  const hasSelection = elements.some(el => el.isSelected);
  const bookLabel = new URLSearchParams(window.location.search).get('book') || 'Paperfect PPT';

  return (
    <div className="ppt-shell flex flex-col h-screen w-full font-sans p-3 gap-3 overflow-hidden">
      {/* Wrapping toolbar: groups flow to next row when narrow — no clip / no H-scroll */}
      <div className="ppt-toolbar z-20 select-none" role="toolbar" aria-label="PPT editor tools">
        <div className="ppt-toolbar-group" title="Slides">
          <button type="button" className="ppt-tb-btn" disabled={currentSlideIndex <= 0} onClick={() => switchSlide(0)} title="First slide">
            <ChevronsLeft size={15} />
          </button>
          <button type="button" className="ppt-tb-btn" disabled={currentSlideIndex <= 0} onClick={() => switchSlide(currentSlideIndex - 1)} title="Previous (←)">
            <ChevronLeft size={15} />
          </button>
          <span className="ppt-tb-label">
            {allSlides.length ? `${currentSlideIndex + 1}/${allSlides.length}` : '—'}
          </span>
          <button type="button" className="ppt-tb-btn" disabled={!allSlides.length || currentSlideIndex >= allSlides.length - 1} onClick={() => switchSlide(currentSlideIndex + 1)} title="Next (→)">
            <ChevronRight size={15} />
          </button>
          <button type="button" className="ppt-tb-btn" disabled={!allSlides.length || currentSlideIndex >= allSlides.length - 1} onClick={() => switchSlide(allSlides.length - 1)} title="Last slide">
            <ChevronsRight size={15} />
          </button>
        </div>

        <div className="ppt-toolbar-group" title="Tools">
          <button type="button" className={`ppt-tb-btn ${currentTool === 'select' ? 'active' : ''}`} onClick={() => setCurrentTool('select')} title="Select / Move (V)">
            <MousePointer2 size={15} />
          </button>
          <button type="button" className={`ppt-tb-btn ${currentTool === 'arrow' ? 'active' : ''}`} onClick={() => setCurrentTool('arrow')} title="Connector / Arrow (A)">
            <ArrowRight size={15} />
          </button>
          <button type="button" className={`ppt-tb-btn ${currentTool === 'text' ? 'active' : ''}`} onClick={() => setCurrentTool('text')} title="Text (T)">
            <Type size={15} />
          </button>
        </div>

        <div className="ppt-toolbar-group" title="History">
          <button type="button" className="ppt-tb-btn" disabled={!history.length} onClick={undo} title="Undo (Ctrl+Z)">
            <Undo2 size={15} />
          </button>
          <button type="button" className="ppt-tb-btn" disabled={!future.length} onClick={redo} title="Redo (Ctrl+Y)">
            <Redo2 size={15} />
          </button>
          <button type="button" className="ppt-tb-btn" disabled={!hasSelection} onClick={duplicateSelected} title="Duplicate (Ctrl+D)">
            <Copy size={15} />
          </button>
          <button type="button" className="ppt-tb-btn danger" disabled={!hasSelection} onClick={deleteSelected} title="Delete">
            <Trash2 size={15} />
          </button>
        </div>

        <div className="ppt-toolbar-group" title="Color">
          {colors.map(color => (
            <button
              type="button"
              key={color}
              className={`ppt-color-dot ${activeColor === color ? 'active' : ''}`}
              style={{ backgroundColor: color, boxShadow: color === '#ffffff' ? 'inset 0 0 0 1px #cbd5e1' : undefined }}
              onClick={() => {
                setActiveColor(color);
                const next = elements.map(el => el.isSelected ? { ...el, color } as CanvasElement : el);
                if (next.some((el, i) => el !== elements[i])) pushHistory(next);
              }}
              title={color}
            />
          ))}
        </div>

        <div className="ppt-toolbar-group" title="Text size">
          <button type="button" className="ppt-tb-btn" onClick={() => bumpFontSize(-2)} title="Smaller text">
            <Minus size={14} />
          </button>
          <span className="ppt-tb-label" style={{ minWidth: 28 }}>{activeFontSize}</span>
          <button type="button" className="ppt-tb-btn" onClick={() => bumpFontSize(2)} title="Larger text">
            <Plus size={14} />
          </button>
        </div>

        <div className="ppt-toolbar-group" title="Line width">
          <button type="button" className="ppt-tb-btn" onClick={() => bumpStroke(-1)} title="Thinner line">
            <Minus size={14} />
          </button>
          <span className="ppt-tb-label" style={{ minWidth: 22 }}>{activeStrokeWidth}</span>
          <button type="button" className="ppt-tb-btn" onClick={() => bumpStroke(1)} title="Thicker line">
            <Plus size={14} />
          </button>
        </div>

        <div className="ppt-toolbar-group" title="Zoom">
          <button type="button" className="ppt-tb-btn" onClick={() => setViewScale(s => Math.max(0.12, +(s - 0.08).toFixed(2)))} title="Zoom out">
            <ZoomOut size={15} />
          </button>
          <span className="ppt-tb-label" style={{ minWidth: 40 }}>{Math.round(viewScale * 100)}%</span>
          <button type="button" className="ppt-tb-btn" onClick={() => setViewScale(s => Math.min(1.25, +(s + 0.08).toFixed(2)))} title="Zoom in">
            <ZoomIn size={15} />
          </button>
        </div>

        <span className="ppt-tb-hint" title={bookLabel}>
          {bookLabel.length > 36 ? bookLabel.slice(0, 36) + '…' : bookLabel}
        </span>
      </div>

      {/* Slide Workspace — fixed, no outer scroll */}
      <div 
        ref={workspaceRef}
        className="ppt-workspace flex-1 min-h-0 relative w-full glass-panel rounded-xl shadow-sm flex items-center justify-center p-3"
      >
        {(slideImage || elements.length > 0 || allSlides.length > 0) ? (
          <div className="relative flex-shrink-0" style={{ width: `${SLIDE_WIDTH * viewScale}px`, height: `${SLIDE_HEIGHT * viewScale}px` }}>
            <div
              id="canvas-container"
              ref={canvasRef}
              className="absolute left-0 top-0 bg-white shadow-xl origin-top-left flex-shrink-0"
              style={{ 
                width: `${SLIDE_WIDTH}px`, 
                height: `${SLIDE_HEIGHT}px`,
                transform: `scale(${viewScale})`,
                cursor: currentTool === 'select' ? 'default' : currentTool === 'text' ? 'text' : 'crosshair',
                overflow: 'hidden'
              }}
            onMouseDown={handlePointerDown} onMouseMove={handlePointerMove} onMouseUp={handlePointerUp} onMouseLeave={handlePointerUp}
            onTouchStart={handlePointerDown} onTouchMove={handlePointerMove} onTouchEnd={handlePointerUp}
          >
            {/* Base White Slide Background */}
            <div id="slide-background" className="absolute inset-0 bg-white" />

            {/* Injected Image */}
            {slideImage && (
              <img 
                id="slide-image" src={slideImage.data} alt="Slide Content" draggable={false}
                className="absolute pointer-events-auto"
                style={{ left: slideImage.x, top: slideImage.y, width: slideImage.width, height: slideImage.height }}
              />
            )}
            
            {/* SVG OVERLAY FOR ARROWS */}
            <svg className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 10 }}>
              <defs>
                {colors.map(color => (
                  <marker key={`arr-${color}`} id={`arr-${color.replace('#', '')}`} markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                    <polygon points="0 0, 10 3.5, 0 7" fill={color} />
                  </marker>
                ))}
              </defs>
              
              {elements.filter((el): el is ArrowElement => el.type === 'arrow').map(arrow => (
                <g key={arrow.id}>
                  <line
                    x1={arrow.startX} y1={arrow.startY} x2={arrow.endX} y2={arrow.endY}
                    stroke="transparent" strokeWidth="15" className="pointer-events-auto cursor-pointer"
                    onMouseDown={(e) => handleElementPointerDown(e, arrow.id)}
                  />
                  <line
                    x1={arrow.startX} y1={arrow.startY} x2={arrow.endX} y2={arrow.endY}
                    stroke={arrow.color}
                    strokeWidth={arrow.width}
                    markerEnd={arrow.noHead ? undefined : `url(#arr-${arrow.color.replace('#', '')})`}
                    className={`pointer-events-none transition-all ${arrow.isSelected ? 'stroke-current drop-shadow-[0_0_8px_rgba(59,130,246,0.8)]' : ''}`}
                  />
                  {arrow.isSelected && currentTool === 'select' && (
                    <>
                      <g 
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
                        </g>
                    </>
                  )}
                </g>
              ))}
            </svg>

            {/* HTML OVERLAY FOR TEXT */}
            <div className="absolute inset-0 w-full h-full pointer-events-none" style={{ zIndex: 20 }}>
              {elements.filter((el): el is TextElement => el.type === 'text').map(textEl => (
                <div
                  key={textEl.id}
                  className={`absolute pointer-events-auto group ${currentTool === 'select' ? 'cursor-move' : ''}`}
                  style={{ left: textEl.x, top: textEl.y }}
                  onMouseDown={(e) => handleElementPointerDown(e, textEl.id)}
                  onDoubleClick={(e) => { e.stopPropagation(); if (currentTool === 'select') setElements(prev => prev.map(el => el.id === textEl.id ? { ...el, isEditing: true } : el)); }}
                >
                  {textEl.isSelected && !textEl.isEditing && ( <div className="absolute -inset-2 border border-dashed border-indigo-400 rounded bg-indigo-500/10 pointer-events-none" /> )}
                  
                  {textEl.isEditing ? (
                    <textarea
                      autoFocus value={textEl.text} onChange={(e) => handleTextChange(textEl.id, e.target.value)}
                      onBlur={() => finishTextEditing(textEl.id)} onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); finishTextEditing(textEl.id); } }}
                      className="bg-white/80 backdrop-blur outline-none border-indigo-500 border rounded px-1 py-0"
                      style={{
                        color: textEl.color,
                        fontSize: `${textEl.fontSize}px`,
                        fontWeight: textEl.fontWeight || 'normal',
                        fontFamily: textEl.fontFamily || 'Calibri, Segoe UI, sans-serif',
                        width: textEl.maxWidth ? `${textEl.maxWidth}px` : `${Math.max(150, textEl.text.length * (textEl.fontSize * 0.6) + 20)}px`,
                        minHeight: textEl.maxHeight ? `${textEl.maxHeight}px` : '40px',
                        resize: 'both',
                        whiteSpace: 'pre-wrap',
                      }}
                    />
                  ) : (
                    <div
                      className={textEl.fill ? '' : 'px-1 py-0'}
                      style={{
                         color: textEl.color,
                         fontSize: `${textEl.fontSize}px`,
                         fontWeight: textEl.fontWeight || (textEl.fill ? 500 : 'bold'),
                         fontFamily: textEl.fontFamily || 'Calibri, Segoe UI, sans-serif',
                         textAlign: (textEl.textAlign as any) || 'left',
                         display: 'flex',
                         flexDirection: 'column',
                         alignItems: (textEl.borderRadius === 999 || textEl.textAlign === 'center') ? 'center' : 'stretch',
                         justifyContent: textEl.valign === 'middle' ? 'center' : (textEl.valign === 'bottom' ? 'flex-end' : 'flex-start'),
                         height: textEl.maxHeight ? `${textEl.maxHeight}px` : 'auto',
                         width: textEl.maxWidth ? `${textEl.maxWidth}px` : undefined,
                         minWidth: textEl.borderRadius === 999 ? (textEl.maxWidth || 20) : undefined,
                         minHeight: textEl.borderRadius === 999 ? (textEl.maxHeight || 20) : undefined,
                         boxSizing: 'border-box',
                         // Callout card chrome (matches PowerPoint text-on-shape)
                         background: textEl.fill || 'transparent',
                         border: textEl.stroke
                           ? `${Math.max(1, textEl.strokeWidth || 1.5)}px solid ${textEl.stroke}`
                           : undefined,
                         borderRadius: textEl.borderRadius != null ? textEl.borderRadius : (textEl.fill ? 10 : 0),
                         // Numbered on-figure badges are ~20px circles — no card padding
                         padding: textEl.borderRadius === 999
                           ? '0'
                           : (textEl.fill ? '8px 10px' : '0 2px'),
                         overflow: 'hidden',
                         boxShadow: textEl.borderRadius === 999
                           ? '0 1px 3px rgba(15,23,42,0.35)'
                           : (textEl.fill ? '0 2px 8px rgba(15,23,42,0.08)' : undefined),
                         textShadow: textEl.fill ? 'none' : '0 1px 2px rgba(255,255,255,0.8)',
                         lineHeight: textEl.borderRadius === 999 ? 1 : 1.25,
                         whiteSpace: 'pre-wrap',
                         wordBreak: 'normal',
                         overflowWrap: 'anywhere',
                      }}
                    >
                      {textEl.text}
                    </div>
                  )}
                </div>
              ))}
            </div>

          </div>
          </div>
        ) : (
          <div className="ppt-empty">
            <MonitorPlay size={40} style={{ opacity: 0.45, margin: '0 auto' }} />
            <h2>Loading presentation…</h2>
            <p>
              Slides are loaded from the paper pipeline. Use the toolbar to annotate:
              select, connectors, text, colors, undo/redo.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default App;
