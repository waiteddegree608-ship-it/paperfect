import React, { useState, useRef, useEffect } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent } from 'react';
import { 
  Image as ImageIcon, 
  MousePointer2, 
  ArrowRight, 
  Type, 
  Trash2, 
  Upload, 
  FileBox,
  MonitorPlay
} from 'lucide-react';
import pptxgen from 'pptxgenjs';

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
const PX_TO_INCH = 128; // pptxgenjs uses 10 x 5.625 inches for 16:9 by default. (1280/10 = 128)
// -------------------------------------------------------------

const App: React.FC = () => {

  const [allSlides, setAllSlides] = useState<SlideData[]>([]);
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0);

  const [slideImage, setSlideImage] = useState<SlideImage | null>(null);
  const [elements, setElements] = useState<CanvasElement[]>([]);

  const [currentTool, setCurrentTool] = useState<Tool>('select');
  const [isDrawing, setIsDrawing] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [activeColor, setActiveColor] = useState('#ef4444');
  const activeFontSize = 24;
  const activeStrokeWidth = 3;
  
  // To handle the fixed size canvas responsively on screen
  const [viewScale, setViewScale] = useState(1);
  const workspaceRef = useRef<HTMLDivElement>(null);
  
  const canvasRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  const [startPoint, setStartPoint] = useState({ x: 0, y: 0 });
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
        const port = window.location.port === '8081' ? '8900' : window.location.port;
        const res = await fetch(`http://${window.location.hostname}:${port}/api/ppt_export_json/${encodeURIComponent(book)}`);
        const json = await res.json();
        
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

  // Update scale to fit the fixed 1280x720 canvas into the working area
  useEffect(() => {
    const handleResize = () => {
      if (workspaceRef.current) {
        const workspaceRect = workspaceRef.current.getBoundingClientRect();
        const availableW = workspaceRect.width - 64; 
        const availableH = workspaceRect.height - 64;
        const scaleW = availableW / SLIDE_WIDTH;
        const minScale = Math.max(0.1, scaleW);
        setViewScale(minScale);
      }
    };
    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, [slideImage]);

  const handleImageUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const dataUrl = event.target?.result as string;
        const img = new Image();
        img.onload = () => {
          // Scale it to fit the upper part of the slide, max bounds: 1000 x 500
          const MAX_W = 1000;
          const MAX_H = 500;
          let w = img.width;
          let h = img.height;
          
          if (w > MAX_W || h > MAX_H) {
             const ratioMax = MAX_W / MAX_H;
             const ratioImg = w / h;
             if (ratioImg > ratioMax) { w = MAX_W; h = MAX_W / ratioImg; }
             else { h = MAX_H; w = MAX_H * ratioImg; }
          }
          
          const x = (SLIDE_WIDTH - w) / 2;
          const y = 30; // 30px top margin
          
          setSlideImage({
            data: dataUrl,
            intrinsicWidth: img.width,
            intrinsicHeight: img.height,
            x: Math.round(x),
            y: Math.round(y),
            width: Math.round(w),
            height: Math.round(h)
          });
        };
        img.src = dataUrl;
      };
      reader.readAsDataURL(file);
    }
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
      setElements([...elements, newArrow]);
    } else if (currentTool === 'text') {
      const newText: TextElement = {
        id: generateId(), type: 'text',
        x, y: y - activeFontSize / 2,
        text: '', color: activeColor, fontSize: activeFontSize,
        isEditing: true, isSelected: true
      };
      setElements([...elements.map(el => ({ ...el, isSelected: false })), newText]);
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
    setElements(prev => prev.filter(el => !el.isSelected));
  };

  
  // =========================================================
  // NATIVE PPTX EXPORT ENGINE
  const exportPPTX = async () => {
    saveCurrentSlide(); // flush current pending edits
    
    setTimeout(async () => {
      const pres = new pptxgen();
      pres.layout = 'LAYOUT_16x9'; 
      
      allSlides.forEach(slideData => {
          const slide = pres.addSlide();
          slide.background = { color: 'FFFFFF' };

          if (slideData.slideImage) {
            slide.addImage({
              data: slideData.slideImage.data,
              x: slideData.slideImage.x / PX_TO_INCH,
              y: slideData.slideImage.y / PX_TO_INCH,
              w: slideData.slideImage.width / PX_TO_INCH,
              h: slideData.slideImage.height / PX_TO_INCH
            });
          }

          slideData.elements.forEach(el => {
            if (el.type === 'text' && (el as TextElement).text.trim()) {
               const t = el as TextElement;
               slide.addText(t.text, {
                  x: t.x / PX_TO_INCH,
                  y: t.y / PX_TO_INCH,
                  w: (t.maxWidth || 250) / PX_TO_INCH,
                  h: 0.5,
                  fontSize: t.fontSize * 0.75,
                  fontFace: 'Arial',
                  color: t.color.replace('#', ''),
                  bold: true,
                  valign: "top"
               });
            }
            else if (el.type === 'arrow') {
               const a = el as ArrowElement;
               let w = (a.endX - a.startX) / PX_TO_INCH;
               let h = (a.endY - a.startY) / PX_TO_INCH;
               let x = a.startX / PX_TO_INCH;
               let y = a.startY / PX_TO_INCH;
               
               let flipH = w < 0;
               let flipV = h < 0;

               slide.addShape(pres.ShapeType.line, {
                  x: flipH ? x + w : x,
                  y: flipV ? y + h : y,
                  w: Math.max(Math.abs(w), 0.01),
                  h: Math.max(Math.abs(h), 0.01),
                  flipH,
                  flipV,
                  line: { color: a.color.replace('#',''), width: a.width, endArrowType: "triangle" }
               });
            }
          });
      });

      try {
        await pres.writeFile({ fileName: `AI-Presentation-${new Date().getTime()}.pptx` });
      } catch (err) {
        console.error("PPTX Export Error:", err);
        alert("Export failed. See console.");
      }
    }, 100);
  };
  // =========================================================


  const loadAIPayload = async () => {
    if (!slideImage) { alert("Please upload an image first."); return; }

    setIsAnalyzing(true);
    try {
      const backendPort = (window.location.port === '8081' || window.location.port === '8000') ? '8900' : window.location.port;
      const response = await fetch(`http://${window.location.hostname}:${backendPort}/api/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: slideImage.data,
          slideWidth: SLIDE_WIDTH,
          slideHeight: SLIDE_HEIGHT,
          imgX: slideImage.x,
          imgY: slideImage.y,
          imgW: slideImage.width,
          imgH: slideImage.height,
          book_name: new URLSearchParams(window.location.search).get('book') || ""
        })
      });
      
      if (response.ok) {
        const data = await response.json();
        setElements(prev => [...prev, ...data.map((d: any) => ({ ...d, isSelected: false, isEditing: false }))]);
      } else {
        alert("Error analyzing image.");
      }
    } catch (err) {
      console.error(err);
      alert("Error connecting to AI server.");
    } finally {
      setIsAnalyzing(false);
    }
  };

  useEffect(() => {
    const handleGlobalKeyDown = (e: globalThis.KeyboardEvent) => {
      if (document.activeElement?.tagName === 'INPUT' || document.activeElement?.tagName === 'TEXTAREA') {
        return;
      }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        deleteSelected();
      } else if (e.key === 'ArrowLeft') {
        switchSlide(currentSlideIndex - 1);
      } else if (e.key === 'ArrowRight') {
        switchSlide(currentSlideIndex + 1);
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [elements, currentSlideIndex, allSlides.length]);

  return (
    <div className="ppt-shell flex flex-col h-screen w-full font-sans p-4 gap-4 overflow-hidden">
      {/* Compact Toolbar */}
      <div className="ppt-toolbar flex flex-row flex-nowrap items-center gap-2 border rounded-xl px-3 py-2 z-10 w-full shrink-0 overflow-x-auto whitespace-nowrap scrollbar-thin select-none">
        
        {/* Navigation */}
        {allSlides.length > 0 && (
          <div className="flex items-center gap-1.5 bg-slate-800 rounded-lg px-2 py-1 shrink-0">
            <button onClick={() => switchSlide(currentSlideIndex - 1)} disabled={currentSlideIndex === 0} className="px-1.5 py-0.5 text-slate-400 hover:text-white disabled:opacity-30 text-xs font-bold">&lt;</button>
            <span className="text-xs font-semibold text-slate-200 min-w-[70px] text-center">Slide {currentSlideIndex + 1} / {allSlides.length}</span>
            <button onClick={() => switchSlide(currentSlideIndex + 1)} disabled={currentSlideIndex === allSlides.length - 1} className="px-1.5 py-0.5 text-slate-400 hover:text-white disabled:opacity-30 text-xs font-bold">&gt;</button>
          </div>
        )}

        <div className="w-px h-5 bg-slate-800 shrink-0 mx-1"></div>

        {/* Tools */}
        <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800 shrink-0">
          <button 
            className={`p-1.5 rounded transition-all ${currentTool === 'select' ? 'bg-[#6E88BD] text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}
            onClick={() => setCurrentTool('select')} title="Select/Move Tool"
          ><MousePointer2 size={16} /></button>
          <button 
            className={`p-1.5 rounded transition-all ${currentTool === 'arrow' ? 'bg-[#6E88BD] text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}
            onClick={() => setCurrentTool('arrow')} title="Draw Arrow Tool"
          ><ArrowRight size={16} /></button>
          <button 
            className={`p-1.5 rounded transition-all ${currentTool === 'text' ? 'bg-[#6E88BD] text-white' : 'text-slate-400 hover:bg-slate-800 hover:text-white'}`}
            onClick={() => setCurrentTool('text')} title="Text Tool"
          ><Type size={16} /></button>
        </div>

        <div className="w-px h-5 bg-slate-800 shrink-0 mx-1"></div>

        {/* Colors & Delete */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
            {colors.map(color => (
              <button
                key={color}
                className={`w-5 h-5 rounded-full transition-transform ${activeColor === color ? 'scale-110 border border-white shadow-md' : 'border border-slate-700 hover:scale-105'}`}
                style={{ backgroundColor: color }}
                onClick={() => {
                  setActiveColor(color);
                  setElements(elements.map(el => el.isSelected ? { ...el, color } : el));
                }}
              />
            ))}
          </div>
          <button
            className="p-1.5 bg-rose-500/10 text-rose-400 rounded-lg hover:bg-rose-500/20 transition-colors border border-rose-500/20 flex items-center justify-center disabled:opacity-40 shrink-0"
            onClick={deleteSelected} disabled={!elements.some(el => el.isSelected)} title="Delete Selected"
          ><Trash2 size={15} /></button>
        </div>

        <div className="w-px h-5 bg-slate-800 shrink-0 mx-1"></div>

        {/* Actions */}
        <div className="flex items-center gap-1.5 shrink-0">
          <label className="flex items-center gap-1.5 px-2.5 py-1 bg-slate-800 hover:bg-slate-750 border border-slate-750 transition-all rounded-lg cursor-pointer text-xs font-semibold text-slate-200">
            <Upload size={14} />
            <span>Load Image</span>
            <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleImageUpload} />
          </label>
          <button 
            className="flex items-center gap-1.5 px-2.5 py-1 bg-[#3A9F83] hover:bg-[#348e75] text-white transition-all rounded-lg text-xs font-semibold disabled:opacity-40"
            onClick={loadAIPayload} disabled={!slideImage || isAnalyzing}
          >
            <span>{isAnalyzing ? "AI Calculating..." : "Auto Layout PPT"}</span>
          </button>
          <button 
            className="flex items-center gap-1.5 px-2.5 py-1 bg-[#C6945D] hover:bg-[#b28452] text-white transition-all rounded-lg text-xs font-semibold disabled:opacity-40"
            onClick={exportPPTX} disabled={!slideImage && elements.length === 0}
          >
            <FileBox size={14} />
            <span>Export Native .PPTX</span>
          </button>
        </div>
      </div>

      {/* Slide Workspace */}
      <div 
        ref={workspaceRef}
        className="ppt-workspace flex-1 min-h-0 relative w-full h-full glass-panel rounded-xl shadow-2xl overflow-y-auto overflow-x-hidden p-4"
      >
        <div className="w-full flex justify-center pb-8" style={{ minHeight: 'max-content' }}>
        {(slideImage || elements.length > 0 || allSlides.length > 0) ? (
          <div className="relative flex-shrink-0" style={{ width: `${SLIDE_WIDTH * viewScale}px`, height: `${SLIDE_HEIGHT * viewScale}px` }}>
            <div
              id="canvas-container"
              ref={canvasRef}
              className="absolute left-0 top-0 bg-white shadow-2xl origin-top-left flex-shrink-0"
              style={{ 
                width: `${SLIDE_WIDTH}px`, 
                height: `${SLIDE_HEIGHT}px`,
                transform: `scale(${viewScale})`,
                cursor: currentTool === 'select' ? 'default' : currentTool === 'text' ? 'text' : 'crosshair',
                overflow: 'visible'
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
                         lineHeight: textEl.borderRadius === 999 ? 1 : undefined,
                         whiteSpace: 'pre-wrap',
                         wordBreak: 'normal',
                         overflowWrap: 'anywhere',
                         lineHeight: 1.25,
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
          <div className="flex flex-col items-center justify-center p-8 text-center border-2 border-dashed border-slate-700/50 rounded-2xl bg-slate-800/20 max-w-lg w-full">
            <MonitorPlay size={48} className="text-indigo-400/50 mb-6" />
            <h2 className="text-2xl font-bold text-white mb-2">Create Standard 16:9 Slide</h2>
            <p className="text-slate-400 mb-8 max-w-md text-sm">
              Upload an architecture diagram. The tool will inject it into a standard 1280x720 PPT slide template.
            </p>
            <label className="flex items-center gap-2 px-6 py-3 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white font-medium rounded-xl shadow-lg cursor-pointer transition-all hover:scale-105">
              <Upload size={20} />
              <span>Select Desktop Image</span>
              <input type="file" accept="image/*" className="hidden" onChange={handleImageUpload} />
            </label>
          </div>
        )}
        </div>
      </div>
    </div>
  );
};

export default App;
