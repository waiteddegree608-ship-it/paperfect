import fs from 'fs';
import { OpenAI } from 'openai';
import pptxgen from 'pptxgenjs';
import sizeOf from 'image-size';

const apiKey = "sk-cdzjqfotorgcynqgzzygcbwrylepjbijikgydpgauwxnpycp";
const client = new OpenAI({
  apiKey: apiKey,
  baseURL: "https://api.siliconflow.cn/v1"
});

const mdPath = "E:\\workspace\\aigal\\参考\\输出结果_FashionTex.md";
const imgPath = "E:\\workspace\\aigal\\参考\\c2a4075843dba86800a235fd4e690be7.png";
const outputPath = "E:\\workspace\\aigal\\参考\\FashionTex_Annotation.pptx";

async function run() {
    console.log("1. Reading Markdown & Image files...");
    const mdContent = fs.readFileSync(mdPath, 'utf-8');
    const imgBuffer = fs.readFileSync(imgPath);
    const base64Data = "data:image/png;base64," + imgBuffer.toString('base64');
    
    // Get image dimensions 
    const dimensions = sizeOf(imgBuffer);
    let imgW = dimensions.width;
    let imgH = dimensions.height;
    console.log(`Original Image Dimensions: ${imgW}x${imgH}`);
    
    // Layout parameters (16:9 standard slide)
    const SLIDE_WIDTH = 1280;
    const SLIDE_HEIGHT = 720;
    const MAX_W = 1000;
    const MAX_H = 500;
    
    // Scale image
    if (imgW > MAX_W || imgH > MAX_H) {
        const ratioMax = MAX_W / MAX_H;
        const ratioImg = imgW / imgH;
        if (ratioImg > ratioMax) { imgH = MAX_W / ratioImg; imgW = MAX_W; }
        else { imgW = MAX_H * ratioImg; imgH = MAX_H; }
    }
    
    const imgX = (SLIDE_WIDTH - imgW) / 2;
    const imgY = 30;

    const prompt = `
You are an expert AI architecture analyzer. Your task is to extract the key modules from the architecture diagram provided.

Important Context: Here is an academic analysis report of this very architecture:
<<<
${mdContent}
>>>

Important Image Rules:
Imagine a coordinate system over the provided image where X goes from 0 (left edge) to 1000 (right edge), and Y goes from 0 (top edge) to 1000 (bottom edge of the image).

Please identify 4 to 6 key modules in the diagram part of the image.
For each module, provide:
1. "targetX": the normalized X coordinate (0-1000) of the center of this module relative to the image width.
2. "targetY": the normalized Y coordinate (0-1000) of the center of this module relative to the image height.
3. "description": A concise but rich and professional explanation of the module's function IN CHINESE (中文). Refer to the Context provided above.

Return ONLY a valid JSON array of objects matching this format (inside \`\`\`json blocks):
[
  {
    "targetX": 250,
    "targetY": 350,
    "description": "投影模块: ..."
  }
]
`;
    console.log("2. Analyzing image via Qwen-VL (SiliconFlow API)...");
    
    const response = await client.chat.completions.create({
      model: "Qwen/Qwen3-VL-235B-A22B-Thinking",
      messages: [
        {
          role: "user",
          content: [
            { type: "image_url", image_url: { url: base64Data } },
            { type: "text", text: prompt }
          ]
        }
      ],
      temperature: 0.2
    });

    let result = response.choices[0].message.content;
    console.log("3. AI result received. Parsing...");
    
    let modules = [];
    const jsonMatch = result.match(/```json\s*([\s\S]*?)\s*```/);
    if (jsonMatch) {
      modules = JSON.parse(jsonMatch[1]);
    } else {
      const rawArrayMatch = result.match(/\[\s*\{[\s\S]*?\}\s*\]/);
      if (rawArrayMatch) {
        modules = JSON.parse(rawArrayMatch[0]);
      } else {
        throw new Error("Unable to parse JSON from AI response.\nRaw: " + result);
      }
    }

    modules.sort((a, b) => a.targetX - b.targetX);
    
    console.log(`-> Found ${modules.length} annotation modules.`);
    console.log("4. Building standard 16:9 .pptx vector file...");

    const pres = new pptxgen();
    pres.layout = 'LAYOUT_16x9'; // 10 x 5.625 inches
    const slide = pres.addSlide();
    slide.background = { color: 'FFFFFF' };
    
    const PX_TO_INCH = 128;
    
    // Add Main Graphic Image
    slide.addImage({
        data: base64Data,
        x: imgX / PX_TO_INCH,
        y: imgY / PX_TO_INCH,
        w: imgW / PX_TO_INCH,
        h: imgH / PX_TO_INCH
    });
    
    const N = modules.length;
    const marginSide = 60;
    const availableWidth = SLIDE_WIDTH - marginSide * 2;
    const columnWidth = availableWidth / N;
    
    modules.forEach((mod, i) => {
        // Recover original points coordinates relative to slide layout
        const absTargetX = imgX + (mod.targetX / 1000) * imgW;
        const absTargetY = imgY + (mod.targetY / 1000) * imgH;

        const boxWidth = Math.max(160, columnWidth - 20);
        const textX = Math.round(marginSide + i * columnWidth + 10);
        // Start text dynamically 40px below the bottom edge of the image
        const textY = imgY + imgH + 40; 
        
        // Add description box
        slide.addText(mod.description, {
            x: textX / PX_TO_INCH,
            y: textY / PX_TO_INCH,
            w: Math.min(250, boxWidth) / PX_TO_INCH,
            h: 0.5,
            fontSize: 14,
            fontFace: 'Arial',
            color: '000000',
            bold: true,
            valign: "top"
        });
        
        // Add connective line with pointer endpoint
        const aStartX = textX + Math.min(250, boxWidth) / 2;
        const aStartY = textY - 10;
        
        let w = (absTargetX - aStartX) / PX_TO_INCH;
        let h = (absTargetY - aStartY) / PX_TO_INCH;
        let x = aStartX / PX_TO_INCH;
        let y = aStartY / PX_TO_INCH;
        
        let flipH = w < 0;
        let flipV = h < 0;
        
        slide.addShape(pres.ShapeType.line, {
            x: flipH ? x + w : x,
            y: flipV ? y + h : y,
            w: Math.max(Math.abs(w), 0.01),
            h: Math.max(Math.abs(h), 0.01),
            flipH: flipH,
            flipV: flipV,
            line: { color: '3b82f6', width: 3, endArrowType: "triangle" }
        });
    });
    
    await pres.writeFile({ fileName: outputPath });
    console.log(`========================================`);
    console.log(` SUCCESS! PPT exported to:`);
    console.log(` ${outputPath}`);
    console.log(`========================================`);
}

run().catch(console.error);
