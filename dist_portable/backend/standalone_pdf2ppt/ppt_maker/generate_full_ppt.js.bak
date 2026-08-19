import fs from 'fs';
import path from 'path';
import { OpenAI } from 'openai';
import pptxgen from 'pptxgenjs';
import sizeOf from 'image-size';

const args = process.argv.slice(2);
if (args.length < 5) {
    console.error("Usage: node generate_full_ppt.js <mdPath> <imgDir> <outputPath> <mode: simple|creative> <apiKey> [modelName]");
    process.exit(1);
}

const mdPath = path.resolve(args[0]);
const imgDir = path.resolve(args[1]);
const outputPath = path.resolve(args[2]);
const MODE = args[3] || 'simple'; 
const apiKey = args[4];
const modelName = args[5] || 'Qwen/Qwen2.5-72B-Instruct';
const customBaseURL = args[6] || 'https://api.siliconflow.cn/v1';
const pptLang = args[7] || 'zh';
const isEn = pptLang === 'en';

const client = new OpenAI({
  apiKey: apiKey,
  baseURL: customBaseURL
});

const is_deepseek = modelName.toLowerCase().includes("deepseek") || customBaseURL.toLowerCase().includes("deepseek");


async function generateGlobalSlides(mdContent) {
    console.log("\n[Agent] -> Generating global slides (Title, TOC, Summary, Ending)...");
    const prompt = isEn ? `
You are an expert AI academic presenter. Your task is to extract high-level information from the provided academic paper text to generate structural presentation slides.
Provide the content for:
1. A Title Slide (Paper title, authors or general presentation context)
2. A Table of Contents (TOC) Slide
3. A Summary/Conclusion Slide
4. An Ending Slide

Context (Academic Analysis Report):
<<<
${mdContent}
>>>

Return ONLY a valid JSON object matching this format (inside \`\`\`json blocks). Please use ENGLISH for all content:
{
  "cover": {
    "title": "Paper Title",
    "subtitle": "Subtitle/Authors/Venue"
  },
  "toc": {
    "title": "Table of Contents",
    "items": ["1. Introduction", "2. Related Work", "3. Methodology", "4. Experiments", "5. Conclusion"]
  },
  "summary": {
    "title": "Summary & Conclusion",
    "bullet_points": ["Core Contribution 1...", "Core Contribution 2...", "Future Work..."]
  },
  "ending": {
    "text": "Thank you!"
  }
}
` : `
You are an expert AI academic presenter. Your task is to extract high-level information from the provided academic paper text to generate structural presentation slides.
Provide the content for:
1. A Title Slide (Paper title, authors or general presentation context)
2. A Table of Contents (TOC) Slide
3. A Summary/Conclusion Slide
4. An Ending Slide

Context (Academic Analysis Report):
<<<
${mdContent}
>>>

Return ONLY a valid JSON object matching this format (inside \`\`\`json blocks). Please use CHINESE for all content:
{
  "cover": {
    "title": "论文标题",
    "subtitle": "副标题/作者/会议"
  },
  "toc": {
    "title": "目录",
    "items": ["1. 引言", "2. 相关工作", "3. 方法", "4. 实验", "5. 结论"]
  },
  "summary": {
    "title": "全文总结",
    "bullet_points": ["核心贡献1...", "核心贡献2...", "未来展望..."]
  },
  "ending": {
    "text": "谢谢聆听"
  }
}
`;

    try {
        const response = await client.chat.completions.create({
            model: modelName,
            messages: [{ role: "user", content: prompt }],
            temperature: 0.2
        });

        let result = response.choices[0].message.content;
        let parsed = null;
        const jsonMatch = result.match(/```json\s*([\s\S]*?)\s*```/);
        if (jsonMatch) {
            parsed = JSON.parse(jsonMatch[1]);
        } else {
            const rawMatch = result.match(/\{\s*"cover"[\s\S]*\}\s*$/);
            if (rawMatch) parsed = JSON.parse(rawMatch[0]);
            else throw new Error("Unable to parse JSON");
        }
        return parsed;
    } catch (e) {
        console.error("   ! Error generating global slides:", e.message);
        return { // Fallback
            cover: { title: "Paper Presentation", subtitle: "" },
            toc: { title: isEn ? "Table of Contents" : "目录", items: isEn ? ["Introduction", "Main Body", "Conclusion"] : ["引言", "主体", "总结"] },
            summary: { title: isEn ? "Summary & Conclusion" : "总结", bullet_points: isEn ? ["This paper proposes a new method..."] : ["本文提出了一种新方案..."] },
            ending: { text: isEn ? "Thank you" : "谢谢聆听 Q&A" }
        };
    }
}

async function processImage(imageName, mdContent) {
    console.log(`\n[Agent] -> Processing ${imageName}...`);
    const imgPath = path.join(imgDir, imageName);
    const imgBuffer = fs.readFileSync(imgPath);
    const base64Data = "data:image/png;base64," + imgBuffer.toString('base64');
    
    const dimensions = sizeOf(imgBuffer);
    let imgW = dimensions.width;
    let imgH = dimensions.height;
    console.log(`   * Dimensions: ${imgW}x${imgH}`);
    
    // Layout parameters (16:9 standard slide)
    const SLIDE_WIDTH = 1280;
    const SLIDE_HEIGHT = 720;
    const MAX_W = 1000;
    // Allow max height to be 300 to make room for Title + Overall explanation + Annotations (prevent bottom overflow)
    const MAX_H = 300;
    
    if (imgW > MAX_W || imgH > MAX_H) {
        const ratioMax = MAX_W / MAX_H;
        const ratioImg = imgW / imgH;
        if (ratioImg > ratioMax) { imgH = MAX_W / ratioImg; imgW = MAX_W; }
        else { imgW = MAX_H * ratioImg; imgH = MAX_H; }
    }
    
    const imgX = (SLIDE_WIDTH - imgW) / 2;
    // Anchor top down 80px to leave room for Title
    const imgY = 80;

    const prompt = isEn ? `
You are an expert AI academic presenter. Your task is to explain the provided image from the scientific paper to an audience by identifying and annotating its logical sub-components (such as sub-figures labeled with letters like 'a', 'b', 'c', 'd', 'e', or charts, tables, specific panels).

Important Context (Academic Analysis Report):
<<<
${mdContent}
>>>

Important Image Rules for Annotations:
Imagine a coordinate system over the provided image where X goes from 0.00 (left edge) to 1.00 (right edge), and Y goes from 0.00 (top edge) to 1.00 (bottom edge of the image).

Instructions:
1. Provide a "slide_title" in ENGLISH summarizing the image's role or content.
2. Provide a brief "overall_explanation" of the image's role (1-3 sentences in ENGLISH, strictly under 40 words).
3. Identify 2 to 6 specific sub-figures or logical components (e.g. sub-figures 'a', 'b', 'c', 'd', 'e') visible in this image to highlight. For each identified sub-figure/component:
   - Provide "targetX": the exact horizontal center ratio (0.00 to 1.00) of this sub-figure/component.
   - Provide "targetY": the exact vertical center ratio (0.00 to 1.00) of this sub-figure/component.
   - Provide "description": A highly specific, detail-oriented, region-bound description explaining exactly what is shown inside this sub-figure/component (e.g. what kind of painting, prompt, baseline, score, or structure is displayed), referencing its label (e.g. "sub-figure a", "sub-figure b") if present. IMPORTANT: Keep each description concise and strictly under 45 words to prevent layout overflow!
4. "follow_up_slides": ${MODE === 'creative' 
    ? "BE CREATIVE! If this image introduces a complex mathematical mechanism, generate one or more follow-up text slides to dive deeper. IMPORTANT: Do NOT use LaTeX tags or symbols that render badly (like \\\\hat{}, \\\\frac{}, \\\\sqrt{}, or $$). PPT uses plain text text-boxes. You MUST use plain English/characters for math (e.g., use E_t' instead of \\\\hat{E}_t, use alpha instead of \\\\alpha) and simple inline operators (like A / B, L_total = L_adv) so formulas look flawless in plain text."
    : "Empty array. DO NOT generate ANY follow-up slides."}

Return ONLY a valid JSON object matching this format (inside \`\`\`json blocks):
{
  "slide_title": "InkIdeator Comparison with Baseline Systems",
  "overall_explanation": "This figure displays the visual design results of InkIdeator compared to baseline systems...",
  "annotations": [
    {
      "targetX": 0.15,
      "targetY": 0.25,
      "description": "Sub-figure a (Canary, Haystack): Shows the comparison, where InkIdeator exhibits better details..."
    }
  ],
  "follow_up_slides": ${MODE === 'creative' ? `[
    {
      "slide_title": "Deep Dive: Core Loss Computation",
      "bullet_points": [
        "The overall loss consists of several components",
        "L_total = L_adv + lambda * L_L1",
        "The adversarial loss helps reduce visual artifacts..."
      ]
    }
  ]` : `[]`}
}
` : `
You are an expert AI academic presenter. Your task is to explain the provided image from the scientific paper to an audience by identifying and annotating its logical sub-components (such as sub-figures labeled with letters like 'a', 'b', 'c', 'd', 'e', or charts, tables, specific panels).

Important Context (Academic Analysis Report):
<<<
${mdContent}
>>>

Important Image Rules for Annotations:
Imagine a coordinate system over the provided image where X goes from 0.00 (left edge) to 1.00 (right edge), and Y goes from 0.00 (top edge) to 1.00 (bottom edge of the image).

Instructions:
1. Provide a "slide_title" in CHINESE summarizing the image's role or content.
2. Provide a brief "overall_explanation" of the image's role (1-3 sentences in CHINESE, strictly under 50 Chinese characters).
3. Identify 2 to 6 specific sub-figures or logical components (e.g. sub-figures 'a', 'b', 'c', 'd', 'e') visible in this image to highlight. For each identified sub-figure/component:
   - Provide "targetX": the exact horizontal center ratio (0.00 to 1.00) of this sub-figure/component.
   - Provide "targetY": the exact vertical center ratio (0.00 to 1.00) of this sub-figure/component.
   - Provide "description": A highly specific, detail-oriented, region-bound (图文结合) description explaining exactly what is shown inside this sub-figure/component (e.g. what kind of painting, prompt, baseline, score, or structure is displayed), referencing its label (e.g. "子图a", "子图b") if present. IMPORTANT: Keep each description concise and strictly under 60 Chinese characters (每条 description 必须极其简明，严格控制在 60 个汉字以内) to prevent layout overflow!
4. "follow_up_slides": ${MODE === 'creative' 
    ? "BE CREATIVE! If this image introduces a complex mathematical mechanism, generate one or more follow-up text slides to dive deeper. IMPORTANT: Do NOT use LaTeX tags or symbols that render badly (like \\\\hat{}, \\\\frac{}, \\\\sqrt{}, or $$). PPT uses plain text text-boxes. You MUST use plain English/characters for math (e.g., use E_t' instead of \\\\hat{E}_t, use alpha instead of \\\\alpha) and simple inline operators (like A / B, L_total = L_adv) so formulas look flawless in plain text."
    : "Empty array. DO NOT generate ANY follow-up slides."}

Return ONLY a valid JSON object matching this format (inside \`\`\`json blocks):
{
  "slide_title": "InkIdeator与基线系统生成图像对比及评估",
  "overall_explanation": "本图展示了InkIdeator系统与基线系统根据相同提示词生成的中国风格绘画作品...",
  "annotations": [
    {
      "targetX": 0.15,
      "targetY": 0.25,
      "description": "子图a (Canary, Haystack): 展示了InkIdeator和提示词的对应效果，可见生成作品在细节和意境上..."
    }
  ],
  "follow_up_slides": ${MODE === 'creative' ? `[
    {
      "slide_title": "深入剖析: 模型核心损失函数计算逻辑",
      "bullet_points": [
        "整体损失由以下几个部分组成",
        "L_total = L_adv + λL_L1",
        "对抗损失的作用在于减少生成瑕疵..."
      ]
    }
  ]` : `[]`}
}
`;

    const maxRetries = 2;
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            let messages;
            if (is_deepseek) {
                const userContent = isEn ? `You are an expert AI academic presenter. We have extracted an image named "${imageName}" from the scientific paper.
Since we are using a text-only model, please analyze the paper content and explain the role/meaning of this figure.

Important Context (Academic Analysis Report):
<<<
${mdContent}
>>>

Instructions:
1. Provide a "slide_title" in ENGLISH summarizing the image's role or content.
2. Provide a brief "overall_explanation" of the image's role (1-3 sentences in ENGLISH).
3. Identify 0 to 5 key features/modules in this image to highlight. Provide "targetX" as a rough horizontal float ratio between 0.00 (left) and 1.00 (right) indicating its relative order in the image.
4. "follow_up_slides": BE CREATIVE! If this image introduces a complex mathematical mechanism, generate one or more follow-up text slides to dive deeper. IMPORTANT: Do NOT use LaTeX tags or symbols that render badly. Use plain English/characters for math.

Return ONLY a valid JSON object matching this format (inside \`\`\`json blocks):
{
  "slide_title": "Visual Result Comparison",
  "overall_explanation": "This figure shows the comparison between...",
  "annotations": [
    {
      "targetX": 0.25,
      "description": "Projection Module: ..."
    }
  ],
  "follow_up_slides": []
}` : `You are an expert AI academic presenter. We have extracted an image named "${imageName}" from the scientific paper.
Since we are using a text-only model, please analyze the paper content and explain the role/meaning of this figure.

Important Context (Academic Analysis Report):
<<<
${mdContent}
>>>

Instructions:
1. Provide a "slide_title" in CHINESE summarizing the image's role or content.
2. Provide a brief "overall_explanation" of the image's role (1-3 sentences in CHINESE).
3. Identify 0 to 5 key features/modules in this image to highlight. Provide "targetX" as a rough horizontal float ratio between 0.00 (left) and 1.00 (right) indicating its relative order in the image.
4. "follow_up_slides": BE CREATIVE! If this image introduces a complex mathematical mechanism, generate one or more follow-up text slides to dive deeper. IMPORTANT: Do NOT use LaTeX tags or symbols that render badly. Use plain English/characters for math.

Return ONLY a valid JSON object matching this format (inside \`\`\`json blocks):
{
  "slide_title": "图像编辑效果对比",
  "overall_explanation": "本图展示了本文提出的FashionTex在...",
  "annotations": [
    {
      "targetX": 0.25,
      "description": "投影模块: ..."
    }
  ],
  "follow_up_slides": []
}`;
                messages = [
                    {
                        role: "user",
                        content: userContent
                    }
                ];
            } else {
                messages = [
                    {
                        role: "user",
                        content: [
                            { type: "image_url", image_url: { url: base64Data } },
                            { type: "text", text: prompt }
                        ]
                    }
                ];
            }

            const response = await client.chat.completions.create({
                model: modelName,
                messages: messages,
                temperature: 0.2
            });

            let result = response.choices[0].message.content;
            
            let parsed = null;
            const jsonMatch = result.match(/```json\s*([\s\S]*?)\s*```/);
            if (jsonMatch) {
                parsed = JSON.parse(jsonMatch[1]);
            } else {
                const rawMatch = result.match(/\{\s*"slide_title"[\s\S]*?\}/);
                if (rawMatch) {
                    parsed = JSON.parse(rawMatch[0]);
                } else {
                    throw new Error("Unable to parse JSON");
                }
            }
            console.log(`   * Success! Found ${parsed.annotations ? parsed.annotations.length : 0} annotations, ${parsed.follow_up_slides ? parsed.follow_up_slides.length : 0} follow-up slides.`);
            
            return {
                imageName, base64Data, imgW, imgH, imgX, imgY, ...parsed
            };
        } catch (e) {
            const errStr = String(e.message || e);
            const isRateLimit = errStr.includes("429") || errStr.includes("limit") || errStr.includes("quota");
            const sleepTime = isRateLimit ? 35000 : 8000;
            console.error(`   ! Error processing ${imageName} (Attempt ${attempt}/${maxRetries}):`, errStr);
            console.error(`   ! Sleeping for ${sleepTime / 1000}s before retry...`);
            if (attempt === maxRetries) {
                console.error(`   ! Max retries reached for ${imageName}. Exiting.`);
                process.exit(1);
            }
            await new Promise(resolve => setTimeout(resolve, sleepTime));
        }
    }
}

async function run() {
    console.log("1. Reading Markdown and enumerating images...");
    const mdContent = fs.readFileSync(mdPath, 'utf-8');
    
    let files = [];
    try {
        files = fs.readdirSync(imgDir).filter(f => f.endsWith('.png') || f.endsWith('.jpg')).sort();
    } catch (e) {
        console.log(`Warning: Image dir ${imgDir} not found or empty. Generating text-only slides.`);
    }
    
    console.log(`Found ${files.length} images: ${files.join(', ')}`);
    
    // Load ppt_cache.json if exists
    const cachePath = path.join(path.dirname(outputPath), "ppt_cache.json");
    let cache = {};
    if (fs.existsSync(cachePath)) {
        try {
            cache = JSON.parse(fs.readFileSync(cachePath, 'utf-8'));
            console.log(`[Cache] Loaded ${Object.keys(cache).length} cached image analysis results.`);
        } catch (e) {
            console.warn("Failed to load cache:", e.message);
        }
    }

    // Page-to-PPT sync mode: We do not generate global semantic slides.
    let globalSlides = null;
    const results = [];
    for (const file of files) {
        let res;
        if (cache[file]) {
            console.log(`[Cache] -> Using cached analysis for ${file}`);
            res = cache[file];
        } else {
            res = await processImage(file, mdContent);
            if (res) {
                cache[file] = res;
                try {
                    fs.writeFileSync(cachePath, JSON.stringify(cache, null, 2), 'utf-8');
                } catch (e) {
                    console.warn("Failed to save cache:", e.message);
                }
            }
        }
        if (res) results.push(res);
        // Sleep for 6 seconds between images to prevent hitting 429 rate limit (strictly 10 RPM)
        await new Promise(resolve => setTimeout(resolve, 6000));
    }
    
    console.log("\n2. Building full presentation...");
    const pres = new pptxgen();
    pres.layout = 'LAYOUT_16x9'; 
    const PX_TO_INCH = 128;
    const SLIDE_WIDTH = 1280;
    const SLIDE_HEIGHT = 720;

    const cleanText = (str) => {
        if (!str) return str;
        return str.replace(/Ê/g, "E'").replace(/\\hat\{(.+?)\}/g, "$1'").replace(/\$/g, "").replace(/\\cos/g, "cos");
    };

    // --- 3. DYNAMIC CONTENT SLIDES ---
    results.forEach((slideData, idx) => {
        // A. The Main Image Slide
        const slide = pres.addSlide();
        slide.background = { color: 'FFFFFF' };
        
        slide.addText(slideData.slide_title || ("Slide " + (idx + 1)), {
            x: 50 / PX_TO_INCH,
            y: 20 / PX_TO_INCH,
            w: (SLIDE_WIDTH - 100) / PX_TO_INCH,
            h: 0.5,
            fontSize: 28,
            bold: true,
            color: '1E3A8A',
            align: 'center'
        });

        slide.addImage({
            data: slideData.base64Data,
            x: slideData.imgX / PX_TO_INCH,
            y: slideData.imgY / PX_TO_INCH,
            w: slideData.imgW / PX_TO_INCH,
            h: slideData.imgH / PX_TO_INCH
        });
        
        const explanationY = slideData.imgY + slideData.imgH + 20;
        slide.addText(slideData.overall_explanation || "", {
            x: 100 / PX_TO_INCH,
            y: explanationY / PX_TO_INCH,
            w: (SLIDE_WIDTH - 200) / PX_TO_INCH,
            h: 0.5,
            fontSize: 16,
            bold: true,
            color: '475569',
            align: 'center',
            valign: 'middle'
        });
        
        // 1. DYNAMIC SPATIAL MAP (OVERRIDE)
        // Resolves asymmetric diagram mapping that AI logic/uniform grids fail on natively.
        const spatialOverrides = {
            // "Figure_2_arch.png": [{ tX: 0.125, tY: 0.45 }, ... ]
        };

        const imgFileName = slideData.imgFile ? path.basename(slideData.imgFile) : "";
        const overrideMap = spatialOverrides[imgFileName];

        const annotations = slideData.annotations || [];
        if (annotations.length > 0) {
            annotations.forEach((mod, idx) => {
                let roughX = 0.5;
                if (mod.target_bbox) {
                    const str = Array.isArray(mod.target_bbox) ? mod.target_bbox.join(',') : String(mod.target_bbox);
                    const numbers = str.match(/[0-9.]+/g);
                    if (numbers && numbers.length >= 4) {
                        let x1 = parseFloat(numbers[1]);
                        let x2 = parseFloat(numbers[3]);
                        if (x1 > 1 || x2 > 1) {  x1 /= 1000.0; x2 /= 1000.0; }
                        roughX = (x1 + x2) / 2.0;
                    }
                } else if (mod.targetX !== undefined) {
                    roughX = parseFloat(mod.targetX);
                }
                mod.computedTx = roughX;
            });
            // Sort to ensure left-to-right alignment sequence
            annotations.sort((a, b) => a.computedTx - b.computedTx);

            const N = annotations.length;
            const marginSide = 60;
            const availableWidth = SLIDE_WIDTH - marginSide * 2;
            const columnWidth = availableWidth / N;
            
            const textY = explanationY + 60; 
            
            annotations.forEach((mod, i) => {
                // Use AI's returned targetX and targetY with grid fallback
                let tX = mod.targetX !== undefined ? parseFloat(mod.targetX) : (i + 0.5) / N;
                let tY = mod.targetY !== undefined ? parseFloat(mod.targetY) : 0.5;

                if (overrideMap && i < overrideMap.length) {
                    tX = overrideMap[i].tX;
                    tY = overrideMap[i].tY;
                }

                const absTargetX = slideData.imgX + tX * slideData.imgW;
                const absTargetY = slideData.imgY + tY * slideData.imgH;

                const boxWidth = Math.max(160, columnWidth - 20);
                const textX = Math.round(marginSide + i * columnWidth + 10);
                
                slide.addText(cleanText(mod.description), {
                    x: textX / PX_TO_INCH,
                    y: textY / PX_TO_INCH,
                    w: Math.min(250, boxWidth) / PX_TO_INCH,
                    h: 0.5,
                    fontSize: 10.5,
                    fontFace: 'Arial',
                    color: '000000',
                    bold: true,
                    valign: "top"
                });
                
                const aStartX = textX + Math.min(250, boxWidth) / 2;
                const aStartY = textY - 5;
                
                let w = (absTargetX - aStartX) / PX_TO_INCH;
                let h = (absTargetY - aStartY) / PX_TO_INCH;
                let x = aStartX / PX_TO_INCH;
                let y = aStartY / PX_TO_INCH;

                // 1. Draw the clean connecting line (NO native arrows to avoid rendering bugs)
                slide.addShape(pres.ShapeType.line, {
                    x: w < 0 ? x + w : x,
                    y: h < 0 ? y + h : y,
                    w: Math.max(Math.abs(w), 0.01),
                    h: Math.max(Math.abs(h), 0.01),
                    flipH: w < 0,
                    flipV: h < 0,
                    line: { color: '3b82f6', width: 2 } 
                });

                // 2. Draw a precise custom vector arrowhead using trigonometry
                const angleRad = Math.atan2(absTargetY - aStartY, absTargetX - aStartX);
                const angleDeg = angleRad * (180 / Math.PI);
                // PPT triangle points UP by default (0 deg). atan2(up) is -90 deg. 
                const pptRotation = angleDeg + 90;

                const arrowSize = 0.12; 
                slide.addShape(pres.ShapeType.triangle, {
                    x: (absTargetX / PX_TO_INCH) - (arrowSize / 2),
                    y: (absTargetY / PX_TO_INCH) - (arrowSize / 2),
                    w: arrowSize,
                    h: arrowSize,
                    fill: { color: '3b82f6' },
                    line: { color: '3b82f6', width: 1 },
                    rotate: pptRotation
                });
            });
        }
    });

    await pres.writeFile({ fileName: outputPath });
    console.log("========================================");
    console.log(" SUCCESS! 🎓 FULL PPT exported to:");
    console.log(" " + outputPath);
    console.log("========================================");
}

run().catch((e) => {
    console.error("Global Error:", e);
    process.exit(1);
});
