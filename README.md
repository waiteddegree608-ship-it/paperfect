# Paperfect

Paperfect 是一个本地化的 Web 应用，用于将学术教材和论文进行格式化提取、翻译解析以及交互式阅读辅助。它主要结合了视觉大语言模型（VLM）与本地处理逻辑，实现学术文档的知识库化。

## 主要功能

1. **教材解析 (PDF 转 Markdown)**
   采用 VLM 调用（默认使用 SiliconFlow 提供的 Qwen 系列视觉模型）对上传的教材 PDF 进行页面截图并转化为结构化的 Markdown 文本，并保持原有公式、图表和逻辑结构的完整性。支持断点续传与多线程处理。
2. **论文翻译 (中英对照)**
   内部集成官方 `pdf2zh` 包模块，对原始学术论文进行版面解析与双语对照翻译，生成不破坏原版式的新 PDF 文件供下载和阅读。
3. **对话式 RAG 伴读**
   将解析完毕的 Markdown 文本或论文挂载为知识库，提供与文档相关的对话服务，用于辅助阅读理解或归纳总结。
4. **演示文稿自动生成 (PDF2PPT)**
   独立的 PPT Maker 子系统，可将提取完毕的讲义或书籍章节，基于特定的 Prompt 生成大纲并自动排版为配套的 `.pptx` 幻灯片。

## 项目结构

```text
├── imports/                   # 存储导入的教材原始 PDF 及断点缓存目录
├── papers/                    # 存储导入的学术论文及翻译后的结果
├── web_ui/                    # Web 前后端主程序目录
│   ├── main.py                # FastAPI 启动主文件与后端路由
│   ├── static/                # 静态资源文件（如 Logo）
│   └── templates/             # Jinja2 前端页面 (首页及 Chat 页面)
├── standalone_pdf2ppt/        # 基于内容的自动 PPT 生成独立子模块
│   └── ppt_maker/             # 处理逻辑与排版指令
├── config.json                # API Key 等核心配置参数 (本地化存储)
├── universal_kb_builder.py    # VLM 图像识别与知识库构建调度模块
├── paper_translator.py        # 调用 pdf2zh 实现双语双轨替换的核心逻辑
└── pdf_annotator.py           # 用于 PDF 追加批注的模块
```

## 安装与配置

### 环境要求
- 操作系统：Windows / Linux / macOS (在基于 COM 的 PPT 的重塑阶段推荐使用 Windows)
- Python 3.10 及以上系统环境

### 依赖安装

进入项目根目录并安装必要依赖模块：

```bash
pip install fastapi uvicorn PyMuPDF openai python-pptx pywin32 pdf2zh
```

*(注：PPT 导出功能依赖 `win32com`，如果使用 Windows 并调用该特定模块，需要在系统中安装好 Microsoft PowerPoint 本体软件。)*

### 配置文件
如果项目根目录下未自动生成 `config.json`，可自行创建，配置如下核心结构（请根据实际持有的 API Key 替换字符串）：

```json
{
    "parse_api_url": "https://api.siliconflow.cn/v1",
    "parse_api_key": [
        "sk-xxx"
    ],
    "parse_model": "Qwen/Qwen3-VL-235B-A22B-Thinking",
    "chat_api_url": "https://api.siliconflow.cn/v1",
    "chat_api_key": "sk-yyy",
    "chat_model": "Qwen/Qwen3-VL-235B-A22B-Thinking",
    "translate_api_key": "sk-zzz"
}
```

## 运行与使用

在项目根目录下运行以下命令启动后台服务：

```bash
python web_ui/main.py
```

终端将输出本地监听地址。通常情况下，通过浏览器访问 `http://127.0.0.1:8899` (或者终端里打印的其他映射端口) 即可进入。
在首页可以通过拖拽上传目标 PDF 触发解析。系统默认集成基础色调适配系统（内置 Antigravity Neon, Dark+, Cyan Light 方案）。

## 注意事项

- 在处理几百页的无字化或纯图 PDF 时，程序会在 `imports/` 或 `papers/` 目录下生成切片文件以供多线程分发处理。如果在分析过程中断，重新上传相同文件即可继续进行。
- 为保证安全，项目核心配置文件 `config.json` 已内建置入屏蔽名单 `.gitignore` 进行阻截，以防止密钥或接口 URL 在 Github 部署时造成大面积意外泄露。
