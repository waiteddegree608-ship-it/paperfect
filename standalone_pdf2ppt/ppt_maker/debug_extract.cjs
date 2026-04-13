const fs = require('fs');
const path = require('path');
const OpenAI = require('openai');

const config = {
    apiKey: "sk-cdzjqfotorgcynqgzzygcbwrylepjbijikgydpgauwxnpycp",
    baseURL: "https://api.siliconflow.cn/v1",
    model: "Qwen/Qwen3-VL-235B-A22B-Thinking",
    // model: "OpenGVLab/InternVL2.5-78B",
};

const openai = new OpenAI({
    apiKey: config.apiKey,
    baseURL: config.baseURL
});

function encodeImageToBase64(filePath) {
    const bitmap = fs.readFileSync(filePath);
    return Buffer.from(bitmap).toString('base64');
}

async function analyzeImagePlaintext(imgPath) {
    const base64Img = encodeImageToBase64(imgPath);
    const prompt = `You are a professional PowerPoint creator and computer vision expert.
Analyze this academic paper diagram (Architecture Pipeline).

Step 1:
Identify 4 key textual labels or module titles printed in the diagram (e.g., "Projection", "ID Recovery", "Fashion Editing").
For EACH label, output its precise location using your visual grounding spatial tokens: <box>(ymin,xmin),(ymax,xmax)</box> followed by the label text.
Do NOT guess. ONLY output the boxes for the exact English text printed on the diagram.

Example format:
<box>(100,200),(150,350)</box> Projection
<box>(300,500),(350,700)</box> ID Recovery
`;

    const response = await openai.chat.completions.create({
        model: config.model,
        temperature: 0.1,
        messages: [
            {
                role: 'user',
                content: [
                    { type: 'text', text: prompt },
                    { type: 'image_url', image_url: { url: `data:image/png;base64,${base64Img}` } }
                ]
            }
        ]
    });

    return response.choices[0].message.content;
}

(async () => {
    const imgPath = path.join(__dirname, '..', '参考', 'images', 'Figure_6.png');
    console.log("Analyzing Figure 6 in Plaintext Grounding Mode...");
    const result = await analyzeImagePlaintext(imgPath);
    console.log("=== RAW MODEL OUPUT ===");
    console.log(result);
    fs.writeFileSync('debug_output.json', result);
})();
