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
interface ArrowElement extends BaseElement { type: 'arrow'; startX: number; startY: number; endX: number; endY: number; color: string; width: number; }
interface TextElement extends BaseElement { type: 'text'; x: number; y: number; text: string; color: string; fontSize: number; isEditing: boolean; maxWidth?: number; }
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
                     color: el.style?.color || '#000000',
                     fontSize: Math.round((el.style?.fontSize || 18) * SCALE),
                     isEditing: false,
                     isSelected: false,
                     maxWidth: Math.round(el.size.width * SCALE),
                     maxHeight: Math.round(el.size.height * SCALE),
                     textAlign: el.style?.textAlign || 'left',
                     valign: el.style?.valign || 'top'
                   });
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

                   newEls.push({
                      id: el.id || Math.random().toString(36).substr(2, 9),
                      type: 'arrow',
                      startX,
                      startY,
                      endX,
                      endY,
                      color: el.style?.stroke || '#3b82f6',
                      width: el.style?.strokeWidth || 3,
                      isSelected: false
                   });
                }
             });
             
             return { slideImage: sImg, elements: newEls };
          });
          
          setAllSlides(parsedSlides);
          if (parsedSlides.length > 0) {
            setSlideImage(parsedSlides[0].slideImage);
            setElements(parsedSlides[0].elements);
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

  const switchSlide = (newIndex: number) => {
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
  };


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
      const response = await fetch('http://localhost:3005/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          image: slideImage.data,
          slideWidth: SLIDE_WIDTH,
          slideHeight: SLIDE_HEIGHT,
          imgX: slideImage.x,
          imgY: slideImage.y,
          imgW: slideImage.width,
          imgH: slideImage.height
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
      if ((e.key === 'Delete' || e.key === 'Backspace') && 
          document.activeElement?.tagName !== 'INPUT' && document.activeElement?.tagName !== 'TEXTAREA') {
        deleteSelected();
      }
    };
    window.addEventListener('keydown', handleGlobalKeyDown);
    return () => window.removeEventListener('keydown', handleGlobalKeyDown);
  }, [elements]);

  return (
    <div className="flex flex-col h-screen w-full bg-slate-950 text-slate-100 font-sans p-4 gap-4 overflow-hidden">
      {/* Header Container */}
      <div className="glass-panel rounded-xl shadow-xl p-4 flex flex-col md:flex-row items-center justify-between gap-4 z-10 w-full shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-500/20 text-indigo-400 flex items-center justify-center">
            <MonitorPlay size={24} />
          </div>
          <div>
            <h1 className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-indigo-400 to-purple-400">
              AI Presentation Canvas
            </h1>
            <p className="text-xs text-slate-400">16:9 Standard Slides (1280x720)</p>
          </div>
        </div>

        {/* Tools */}
        <div className="flex flex-wrap items-center justify-center gap-2 bg-slate-900/50 p-2 rounded-lg border border-slate-800">
          <button 
            className={`p-2 rounded-md transition-all ${currentTool === 'select' ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30' : 'text-slate-400 hover:bg-slate-700 hover:text-white'}`}
            onClick={() => setCurrentTool('select')} title="Select/Move Tool"
          ><MousePointer2 size={20} /></button>
          <div className="w-px h-6 bg-slate-700 mx-1"></div>
          <button 
            className={`p-2 rounded-md transition-all ${currentTool === 'arrow' ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30' : 'text-slate-400 hover:bg-slate-700 hover:text-white'}`}
            onClick={() => setCurrentTool('arrow')} title="Draw Arrow Tool"
          ><ArrowRight size={20} /></button>
          <button 
            className={`p-2 rounded-md transition-all ${currentTool === 'text' ? 'bg-indigo-500 text-white shadow-lg shadow-indigo-500/30' : 'text-slate-400 hover:bg-slate-700 hover:text-white'}`}
            onClick={() => setCurrentTool('text')} title="Text Tool"
          ><Type size={20} /></button>
        </div>

        {/* Props */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex gap-1 bg-slate-900/50 p-1.5 rounded-lg border border-slate-800">
            {colors.map(color => (
              <button
                key={color}
                className={`w-6 h-6 rounded-full transition-transform ${activeColor === color ? 'scale-125 border-2 border-white shadow-md' : 'border border-slate-600 hover:scale-110'}`}
                style={{ backgroundColor: color }}
                onClick={() => {
                  setActiveColor(color);
                  setElements(elements.map(el => el.isSelected ? { ...el, color } : el));
                }}
              />
            ))}
          </div>
          <button
            className="p-2 bg-rose-500/10 text-rose-400 rounded-lg hover:bg-rose-500/20 transition-colors border border-rose-500/20 flex items-center justify-center disabled:opacity-50"
            onClick={deleteSelected} disabled={!elements.some(el => el.isSelected)} title="Delete Selected"
          ><Trash2 size={18} /></button>
        </div>

        
        {/* Actions */}
        <div className="flex items-center gap-2">
          {allSlides.length > 0 && (
              <div className="flex items-center gap-2 mr-4 bg-slate-800 rounded-lg px-2 py-1">
                 <button onClick={() => switchSlide(currentSlideIndex - 1)} disabled={currentSlideIndex === 0} className="px-2 py-1 text-slate-400 hover:text-white disabled:opacity-30">&lt;</button>
                 <span className="text-sm font-medium">Slide {currentSlideIndex + 1} / {allSlides.length}</span>
                 <button onClick={() => switchSlide(currentSlideIndex + 1)} disabled={currentSlideIndex === allSlides.length - 1} className="px-2 py-1 text-slate-400 hover:text-white disabled:opacity-30">&gt;</button>
              </div>
          )}

          <label className="flex items-center gap-2 px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-all rounded-lg cursor-pointer text-sm font-medium">
            <Upload size={18} />
            <span>Load Image</span>
            <input type="file" accept="image/*" className="hidden" ref={fileInputRef} onChange={handleImageUpload} />
          </label>
          <button 
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 shadow-lg shadow-emerald-500/20 text-white transition-all rounded-lg text-sm font-medium disabled:opacity-50"
            onClick={loadAIPayload} disabled={!slideImage || isAnalyzing}
          >
            <span>{isAnalyzing ? "AI Calculating..." : "Auto Layout PPT"}</span>
          </button>
          <button 
            className="flex items-center gap-2 px-4 py-2 bg-gradient-to-r from-orange-600 to-rose-600 hover:from-orange-500 hover:to-rose-500 shadow-lg shadow-orange-500/20 text-white transition-all rounded-lg text-sm font-medium disabled:opacity-50"
            onClick={exportPPTX} disabled={!slideImage && elements.length === 0}
          >
            <FileBox size={18} />
            <span>Export Native .PPTX</span>
          </button>
        </div>
      </div>

      {/* Slide Workspace */}
      <div 
        ref={workspaceRef}
        className="flex-1 min-h-0 relative w-full h-full glass-panel rounded-xl shadow-2xl overflow-y-auto overflow-x-hidden p-4 bg-slate-900/50"
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
                    stroke={arrow.color} strokeWidth={arrow.width} markerEnd={`url(#arr-${arrow.color.replace('#', '')})`}
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
                      style={{ color: textEl.color, fontSize: `${textEl.fontSize}px`, fontWeight: 'bold', width: textEl.maxWidth ? `${textEl.maxWidth}px` : `${Math.max(150, textEl.text.length * (textEl.fontSize * 0.6) + 20)}px`, minHeight: '40px', resize: 'both' }}
                    />
                  ) : (
                    <div 
                      className="px-1 py-0 drop-shadow-md"
                      style={{ 
                         color: textEl.color, 
                         fontSize: `${textEl.fontSize}px`, 
                         fontWeight: 'bold', 
                         textAlign: (textEl as any).textAlign || 'left',
                         display: 'flex',
                         flexDirection: 'column',
                         justifyContent: (textEl as any).valign === 'middle' ? 'center' : ((textEl as any).valign === 'bottom' ? 'flex-end' : 'flex-start'),
                         height: (textEl as any).maxHeight ? `${(textEl as any).maxHeight}px` : 'auto',
                         textShadow: '0 1px 2px rgba(255,255,255,0.8)', 
                         width: textEl.maxWidth ? `${textEl.maxWidth + 4}px` : undefined, 
                         whiteSpace: textEl.maxWidth ? 'pre-wrap' : 'nowrap', 
                         wordBreak: textEl.maxWidth ? 'break-all' : 'normal' 
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
