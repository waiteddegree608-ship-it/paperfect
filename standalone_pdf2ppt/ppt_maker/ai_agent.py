import base64
import json
import os
import re
from openai import OpenAI
from PIL import Image

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# Load API Key from config.json
api_key = ""
config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'config.json')
if os.path.exists(config_path):
    with open(config_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
        keys = cfg.get("parse_api_key", [])
        if keys:
            api_key = keys[0] if isinstance(keys, list) else keys

client = OpenAI(
    api_key=api_key,
    base_url="https://api.siliconflow.cn/v1"
)

target_image = r"E:\workspace\aigal\参考\c2a4075843dba86800a235fd4e690be7.png"
reference_image = r"E:\workspace\aigal\参考\3c3bc45774ead99dd46d7ca5d73e1df9.png"

# Read image sizes to help the model with coordinates
with Image.open(target_image) as img:
    width, height = img.size

base64_target = encode_image(target_image)
base64_reference = encode_image(reference_image)

prompt = f"""
You are an expert AI architecture analyzer. Your task is to use a visual annotation tool to explain the provided architecture diagram. 
We have a target architecture diagram (Image 2) with size W:{width}px, H:{height}px.
I want to create an annotation exactly like the example reference diagram (Image 1). 
Please break down the architecture in Image 2 and explain each module.

To use the annotation tool, you need to output a JSON array of elements inside a markdown code block ````json ... ````.
The tool supports two types of elements: arrows and texts. 
Use Absolute Pixel Coordinates (0 to {width} for X, 0 to {height} for Y).
Colors should be in HEX (like #ef4444 for red, #3b82f6 for blue, #000000 for black).
FontSize for text is usually 18-24.

Format:
[
  {{
    "id": "arrow_1",
    "type": "arrow",
    "startX": 100,
    "startY": 200,
    "endX": 150,
    "endY": 250,
    "color": "#ef4444",
    "width": 3
  }},
  {{
    "id": "text_1",
    "type": "text",
    "x": 160,
    "y": 260,
    "text": "This is the Encoder module",
    "color": "#ffffff",
    "fontSize": 20
  }}
]

Provide only the valid JSON array in your output, containing all the arrows and text notes necessary to explain the diagram (at least 6 components: global features, losses, pipeline steps, etc., like the reference).
"""

messages = [
    {
        "role": "user",
        "content": [
            {
                "type": "text",
                "text": "Image 1: Reference"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_reference}"
                }
            },
            {
                "type": "text",
                "text": "Image 2: Target Diagram"
            },
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{base64_target}"
                }
            },
            {
                "type": "text",
                "text": prompt
            }
        ]
    }
]

print("Calling SiliconFlow API...")
try:
    response = client.chat.completions.create(
        model="Qwen/Qwen3-VL-235B-A22B-Thinking",
        messages=messages,
        temperature=0.2
    )

    result = response.choices[0].message.content
    print("API Result received.")
    
    # Extract JSON
    json_str = result
    pattern = r'```json\s*(.*?)\s*```'
    match = re.search(pattern, result, re.DOTALL)
    if match:
        json_str = match.group(1)
    elif r'```' in result:
        json_str = result.split('```')[1]
        
    try:
        data = json.loads(json_str)
        with open('public/ai_payload.json', 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("Successfully saved annotations to public/ai_payload.json")
    except json.JSONDecodeError as e:
        print("Failed to parse JSON")
        print(json_str)
except Exception as e:
    print("Error calling API:", e)
