import re

app_tsx_path = r"E:\workspace\ddl\standalone_pdf2ppt\ppt_maker\src\App.tsx"

with open(app_tsx_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add interface SlideData and multi-slide states
code_to_insert_top = """
interface SlideData {
  slideImage: SlideImage | null;
  elements: CanvasElement[];
}

// -------------------------------------------------------------
"""

content = content.replace("// -------------------------------------------------------------", code_to_insert_top + "// -------------------------------------------------------------", 1)

state_replacements = """
  const [allSlides, setAllSlides] = useState<SlideData[]>([]);
  const [currentSlideIndex, setCurrentSlideIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  const [slideImage, setSlideImage] = useState<SlideImage | null>(null);
  const [elements, setElements] = useState<CanvasElement[]>([]);
"""

content = re.sub(
  r"  const \[slideImage, setSlideImage\] = useState<SlideImage \| null>\(null\);\s*const \[elements, setElements\] = useState<CanvasElement\[\]>\(\[\]\);",
  state_replacements,
  content
)

# 2. Add useEffect to load PPT from backend
fetch_logic = """
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const book = params.get('book');
    if (!book) return;

    const fetchPpt = async () => {
      setIsLoading(true);
      try {
        const port = window.location.port === '8081' ? '8899' : window.location.port;
        const res = await fetch(`http://${window.location.hostname}:${port}/api/ppt_export_json/${encodeURIComponent(book)}`);
        const json = await res.json();
        
        if (json.slides && json.slides.length > 0) {
          const parsedSlides: SlideData[] = json.slides.map((s: any) => {
             let sImg: SlideImage | null = null;
             const newEls: CanvasElement[] = [];
             
             s.elements.forEach((el: any) => {
                if (el.type === 'image' && !sImg) {
                   sImg = {
                     data: el.content,
                     intrinsicWidth: el.size.width,
                     intrinsicHeight: el.size.height,
                     x: el.position.x,
                     y: el.position.y,
                     width: el.size.width,
                     height: el.size.height
                   };
                } else if (el.type === 'text') {
                   newEls.push({
                     id: el.id || Math.random().toString(36).substr(2, 9),
                     type: 'text',
                     x: el.position.x,
                     y: el.position.y,
                     text: el.content || '',
                     color: el.style?.color || '#000000',
                     fontSize: el.style?.fontSize || 24,
                     isEditing: false,
                     isSelected: false,
                     maxWidth: el.size.width
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
      } finally {
        setIsLoading(false);
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
"""

content = content.replace("  const colors = ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ffffff', '#000000'];", "  const colors = ['#ef4444', '#3b82f6', '#10b981', '#f59e0b', '#8b5cf6', '#ffffff', '#000000'];\n" + fetch_logic)

# 3. Modify exportPPTX to export ALL slides
export_pptx_new = """
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
"""

content = re.sub(
  r"// =========================================================\s*// NATIVE PPTX EXPORT ENGINE.*?// =========================================================",
  export_pptx_new.replace("\\", "\\\\"),
  content,
  flags=re.DOTALL
)

# 4. Add UI Pagination Controls
ui_pagination = """
        {/* Actions */}
        <div className="flex items-center gap-2">
          {allSlides.length > 0 && (
              <div className="flex items-center gap-2 mr-4 bg-slate-800 rounded-lg px-2 py-1">
                 <button onClick={() => switchSlide(currentSlideIndex - 1)} disabled={currentSlideIndex === 0} className="px-2 py-1 text-slate-400 hover:text-white disabled:opacity-30">&lt;</button>
                 <span className="text-sm font-medium">Slide {currentSlideIndex + 1} / {allSlides.length}</span>
                 <button onClick={() => switchSlide(currentSlideIndex + 1)} disabled={currentSlideIndex === allSlides.length - 1} className="px-2 py-1 text-slate-400 hover:text-white disabled:opacity-30">&gt;</button>
              </div>
          )}
"""

content = content.replace("{/* Actions */}\n        <div className=\"flex items-center gap-2\">", ui_pagination)


with open(app_tsx_path, "w", encoding="utf-8") as f:
    f.write(content)
print("Done rewriting App.tsx")
