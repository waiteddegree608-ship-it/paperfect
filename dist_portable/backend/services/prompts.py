import os
import json
from typing import Dict, List
from backend.core.config import get_base_dir

def get_character_config(char_id: str) -> dict:
    char_dir = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "characters", char_id)
    config_path = os.path.join(char_dir, "config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_stage1_prompt(prompt_name: str = "计算机+人工智能") -> str:
    prompt_dir = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "prompts")
    prompt_file = os.path.join(prompt_dir, f"{prompt_name}.md")
    p1 = "未找到指定提示词"
    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            p1 = f.read()
    else:
        # Fallback to default if custom not found
        default_file = os.path.join(prompt_dir, "计算机+人工智能.md")
        if os.path.exists(default_file):
            with open(default_file, "r", encoding="utf-8") as f:
                p1 = f.read()
    return f"""请仔细阅读提供的PDF所有页面内容，并直接按照以下需求汇总要求，为这篇论文生成一份深度的学术解析报告（使用Markdown格式）。

【需求汇总（来自 {prompt_name}.md）】：
{p1}

请直接输出高质量的 Markdown 格式学术报告，尽可能详细严谨，分析深入，内容充实。"""


def get_stage2_pure_script_prompt(md_report: str) -> str:
    seq_file = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "论文汇报顺序.md")
    p_seq = "按照正常学术演讲顺序"
    if os.path.exists(seq_file):
        with open(seq_file, "r", encoding="utf-8") as f:
            p_seq = f.read()

    # 读取提示词汇总（如果不包含在md_report的分析中，也可在这里强调）
    prompt_file = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "提示词汇总.md")
    p_summary = ""
    if os.path.exists(prompt_file):
        with open(prompt_file, "r", encoding="utf-8") as f:
            p_summary = f.read()

    prompt_base = f"""这里有一份整理极好的学术报告全文：
=== 学术报告开始 ===
{md_report}
=== 学术报告结束 ===

任务：请结合上述报告和原PDF图片，生成一份【极其严谨的、完全剥离任何角色人设和口癖的纯学术汇报剧本】。
请完全遵守以下汇报顺序：
【论文汇报顺序】：
{p_seq}

【要求（来自提示词汇总）】：
{p_summary}

必须返回合法的 JSON 格式，结构如下：
{{
  "title": "（起个这篇文献的相关标题）",
  "script": [
    {{
      "speaker": "主讲人",
      "text": "（纯粹的学术讲解台词，语言必须专业、客观、严密，不能有任何口癖和轻浮感）",
      "emotion": "normal",
      "display_figure": 2 // 注意：如果不涉及具体图表（如引言或结论），必须填 null，绝对不能填数字0！只有在明确讲述某张图时填该图数字序号，且在连续讲解同一张图时必须持续保持该序号。
    }}
  ]
}}
}}
注意：这是一个生死攸关的要求！这段剧本需要尽可能极其详细！绝对不能把整个章节塞进一句台词里！！
必须细致地将报告内容切分成多条对话，每一条 `text` 不超过 100 字。把图表的细节、创新的意义层层递进地解释透彻。
最终生成的 `script` 数组长度请务必保持在超越 20 条以上！如果写不长请多写细节分析！
"""
    return prompt_base

def get_stage3_roleplay_prompt(char_id: str, raw_json: str) -> str:
    char_config = get_character_config(char_id)
    char_name = char_config.get("name", "未知角色")
    char_prompt = char_config.get("prompt", "")
    emotions = ", ".join(char_config.get("emotions", ["normal"]))

    # Also load the global character roles settings as requested by user
    roles_file = os.path.join(get_base_dir(), "backend", "standalone_pdf2ppt", "角色设定汇总.md")
    roles_context = ""
    if os.path.exists(roles_file):
        with open(roles_file, "r", encoding="utf-8") as f:
            roles_context = f.read()

    prompt_base = f"""你现在是在给超长篇Galgame生成剧本。这有一个浓缩的纯学术风格的JSON底稿：
=== 学术剧本底稿开始 ===
{raw_json}
=== 学术剧本底稿结束 ===

请你以角色“{char_name}”的口吻，对这份底稿进行【超级扩写与彻底洗稿重塑】！
具体核心要求如下：
1. **极限扩写与台词强行拆分（生死攸关的要求）**：这是长篇Galgame！不要大段大段地背书！请强制将底稿中的每一个 `text` 长句拆碎成 3 到 5 句充满呼吸感和互动感的短台词。每句话不超过50个字！
最终返回的 `script` JSON 数组对象数量必须远超 40 条！！绝对不能偷懒缩略！
2. **强制增加日常互动前奏与结尾**：
   - 必须在正式开讲第一阶段学术内容之前，先写 3~5 只具有极强世界观代入感的“日常寒暄剧本”（比如来到房间、抱怨、调戏老板等），引出接下来的演讲。
   - 必须在最后一句讲述结束后，附上 2~3 只温柔或有趣的“打烊告别剧本”。
3. **图表持续显示法则（核心修复）**：当你在拆分讲述某一张核心图表（带有 `display_figure` 数字）时，**拆解出来的这十几句碎台词，每一句的 `display_figure` 都必须原样填写那个图表的序号！**
但反之，在**开场寒暄、结语告别，以及任何没有涉及论文具体配图的段落中，请务必将 `display_figure` 设为 `null`（字面量的null，不要带引号，绝对禁止填数字0！）**，以保持画面清爽！
4. **口吻全面同化**：不要只在句尾加个“哦~”，而是要把枯燥的学术逻辑彻底化作“她的脑回路”语言风格。

你的性格与设定约束：
{char_prompt}

【参考世界观与角色群像（角色设定汇总，请用来构建打招呼的寒暄语境）】：
{roles_context}

！！！极度危险警告及格式约束！！！：
1. `text` 必须是 **100%纯净的人物讲话语言**，绝对禁止出现任何动作或神态描写（如“*抚摸龙角*”、“（笑）”）。
2. 请把 speaker 的名字全部统一写为 `{char_name}`。
3. `emotion` 请根据语境，绝对只能从这几个可选表情中挑选：[{emotions}]。
4. JSON 结构必须合法，输出格式为 `{{"title": "xxx", "script": [{{"speaker":"x","text":"x","emotion":"x","display_figure":null}}]}}`。

返回一段完全合法的经过洗稿的全新JSON，不要给额外的解释。
"""
    return prompt_base

def get_chat_prompt(char_id: str, md_report: str) -> str:
    char_config = get_character_config(char_id)
    char_name = char_config.get("name", "未知角色")
    char_prompt = char_config.get("prompt", "")
    emotions = ", ".join(char_config.get("emotions", ["normal"]))

    roles_file = os.path.join(os.path.dirname(__file__), "角色设定汇总.md")
    roles_context = ""
    if os.path.exists(roles_file):
        with open(roles_file, "r", encoding="utf-8") as f:
            roles_context = f.read()

    sys_prompt = f"""你现在是Visual Novel游戏中的角色“{char_name}”。

在此前，你已经基于下面这份学术报告向我进行了汇报：
=== 学术报告 ===
{md_report[:2500]} ... (由于长度限制截断)
=== 学术报告结束 ===

你的性格和人设约束：
{char_prompt}

【参考世界观与角色群像（角色设定汇总）】：
{roles_context}

【任务约束】：
1. 玩家正在针对这篇论文（或自由聊天）向你提问，你需要以角色的口吻回复玩家。可以自由审视上传的论文全图内容。
2. 你必须返回合法的 JSON 格式，结构如下：
{{
  "text": "（你的回答内容，绝对纯净无动作描写的口语，不要带有*动作*）",
  "emotion": "（从 {emotions} 中任选一个符合当前语境的表情）",
  "display_figure": 2 // 如果你在回话中明确讲解到这篇论文中具体的某张图，请填纯数字。只要话题还是这张图，随后的聊天也要持续带有这个数字，否则幻灯片会掉线！不涉及就设为null。
}}
3. 严禁你的 text 中出现类似“*笑着说*”、“（摸摸头）”这样的动作或神态描写，全部交由 emotion 字段传达！
"""
    return sys_prompt

