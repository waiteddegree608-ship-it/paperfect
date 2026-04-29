import express from 'express';
import cors from 'cors';
import { OpenAI } from 'openai';
import fs from 'fs';

const app = express();
app.use(cors());
app.use(express.json({ limit: '50mb' }));

import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

let apiKey = "";
try {
  const configObj = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'config.json'), 'utf-8'));
  apiKey = configObj.parse_api_key && configObj.parse_api_key.length > 0 ? configObj.parse_api_key[0] : "";
} catch (e) {
  console.warn("Could not read config.json", e);
}

const client = new OpenAI({
  apiKey: apiKey,
  baseURL: "https://api.siliconflow.cn/v1"
});

app.post('/api/analyze', async (req, res) => {
  try {
    const { 
      image,
      slideWidth, slideHeight,
      imgX, imgY, imgW, imgH 
    } = req.body;
    
    const base64Data = image;

    const mdPath = "E:\\workspace\\aigal\\参考\\输出结果_FashionTex.md";
    let mdContent = "";
    try {
      mdContent = fs.readFileSync(mdPath, 'utf-8');
    } catch (e) {
      console.warn("Could not read MD file", e);
    }

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

    console.log("Analyzing image mapped onto a slide...");

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
    let modules = [];
    
    const jsonMatch = result.match(/```json\s*([\s\S]*?)\s*```/);
    if (jsonMatch) {
      modules = JSON.parse(jsonMatch[1]);
    } else {
      const rawArrayMatch = result.match(/\[\s*\{[\s\S]*?\}\s*\]/);
      if (rawArrayMatch) {
        modules = JSON.parse(rawArrayMatch[0]);
      } else {
        throw new Error("Unable to parse JSON from AI response.");
      }
    }

    modules.sort((a, b) => a.targetX - b.targetX);

    const N = modules.length;
    if (N === 0) throw new Error("No modules extracted.");
    
    // Distribute annotations on the slide below the image
    const marginSide = 60;
    const availableWidth = slideWidth - marginSide * 2;
    const columnWidth = availableWidth / N;
    
    let finalElements = [];
    
    modules.forEach((mod, i) => {
      // Calculate absolute target on the image using projection
      const absTargetX = imgX + (mod.targetX / 1000) * imgW;
      const absTargetY = imgY + (mod.targetY / 1000) * imgH;

      const boxWidth = Math.max(160, columnWidth - 20);
      const textX = Math.round(marginSide + i * columnWidth + 10);
      
      // Start text dynamically 40px below the bottom edge of the image
      const textY = imgY + imgH + 40; 
      
      const tId = "text_" + i;
      const aId = "arrow_" + i;
      
      finalElements.push({
        id: tId,
        type: "text",
        x: textX,
        y: textY,
        text: mod.description,
        color: "#000000",
        fontSize: 18,
        maxWidth: Math.floor(boxWidth),
        isEditing: false,
        isSelected: false
      });
      
      finalElements.push({
        id: aId,
        type: "arrow",
        startX: Math.round(textX + boxWidth / 2),
        startY: textY - 10,
        endX: Math.round(absTargetX),
        endY: Math.round(absTargetY),
        color: "#3b82f6",
        width: 3,
        isSelected: false
      });
    });

    res.json(finalElements);

  } catch (error) {
    console.error("Error during analysis:", error);
    res.status(500).json({ error: error.message });
  }
});

const PORT = 3005;
app.listen(PORT, () => {
  console.log("Backend server running on http://localhost:" + PORT);
});
