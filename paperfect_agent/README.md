# Paperfect Agent Pack（MCP + Skills）

给**其他项目里的其他 AI**用的封装：同一套论文流水线，不依赖 Paperfect 桌面窗口。

- **MCP**：可调用的工具（ingest / 解析 / 翻译 / 批注 / PPT / 问答 / PDF 工具箱）
- **Skills**：教 Agent 何时调用这些工具、产物路径、续跑规则

MCP 进程必须能 import Paperfect 的 `backend/`（设 `PAPERFECT_ROOT`）。Skills 可以单独拷贝。

## 目录

```
paperfect_agent/
├── server.py              # MCP stdio 入口
├── runtime.py / workspace.py / stages.py
├── requirements.txt       # pip install mcp
├── mcp.json.example
├── MANIFEST.json
└── skills/
    ├── paperfect-pipeline/
    ├── paperfect-reading/
    ├── paperfect-library/
    ├── paperfect-prompts/
    └── paperfect-authoring/
```

## 1. 安装 MCP 依赖

在**已经能运行 Paperfect** 的同一个 Python 环境里：

```bash
python -m pip install mcp
```

PPT 还需要 Node，并在 `backend/standalone_pdf2ppt/ppt_maker` 执行过一次 `npm install`。API Key 仍写在 Paperfect 根目录的 `.env`（`CHAT_API_KEY` / `PARSE_API_KEY` 等），不要写进 MCP 配置。

## 2. 在其他项目注册 MCP

把 `mcp.json.example` 里的路径改成你的绝对路径，合并进客户端配置：

- Cursor：`~/.cursor/mcp.json` 或项目 `.cursor/mcp.json`
- Claude Desktop：`claude_desktop_config.json` 的 `mcpServers`

必填环境变量：

| 变量 | 含义 |
|---|---|
| `PAPERFECT_ROOT` | Paperfect 仓库根目录（含 `backend/`、`.env`） |
| `PAPERFECT_WORK_DIR` | 可选。本项目论文产物目录。不设则写入 `{PAPERFECT_ROOT}/data/papers` |

其他项目**强烈建议**设置 `PAPERFECT_WORK_DIR`，避免论文堆进桌面版文献库。

Windows 示例：

```json
{
  "mcpServers": {
    "paperfect": {
      "command": "C:/path/to/paperfect/venv/Scripts/python.exe",
      "args": ["C:/path/to/paperfect/paperfect_agent/server.py"],
      "env": {
        "PAPERFECT_ROOT": "C:/path/to/paperfect",
        "PAPERFECT_WORK_DIR": "D:/my-research/paperfect_out"
      }
    }
  }
}
```

`command` 必须指向装过 `PyMuPDF`、`openai`、`mcp` 的解释器（Paperfect 的 `venv` 即可）。

## 3. 安装 Skills

把 `skills/` 下五个文件夹原样复制到：

- Cursor 用户级：`~/.cursor/skills/`
- 仅某个仓库：`{repo}/.cursor/skills/`

详见 [skills/README.md](skills/README.md)。

## 4. Agent 应如何用

1. `health`
2. `ingest_pdf(pdf_path=...)` → 记下 `book_name`
3. 全做：`run_pipeline`；只要问答：`parse_paper` 然后 `ask_paper`
4. 重跑前先 `get_artifacts`，已有产物会自动 skip（`force=true` 才覆盖）

解析 / 翻译 / PPT 可能数分钟，客户端超时后用 `get_artifacts` 看是否已经写完。

## 5. 工具一览

`health`, `ingest_pdf`, `list_papers`, `get_artifacts`, `read_artifact`, `detect_body_range`, `analyze_metadata`, `extract_figures`, `parse_paper`, `translate_pdf`, `annotate_pdf`, `generate_ppt`, `run_pipeline`, `ask_paper`, `search_library`, `list_prompts`, `pdf_tool`

细节见 `skills/paperfect-pipeline/tools.md`。


## 精读、图译与讲解型 PPT

共享生成规范位于 `backend/skills`，由实际模型调用加载；外部 Agent 可用 `list_skills` / `read_skill` 读取。

- `translate_reading(book_name, pages=[1,2], localize=true)`：生成 HTML 阅读版、可编辑表格、原始 SVG 与中文标签 SVG。省略 pages 翻译全部物理页；视觉模型用于页面与图内文字理解。
- `generate_notes(book_name)`：按全部可提取页文本生成详细解读，返回页码、引文匹配和待核查项。
- `read_artifact(kind="reading_manifest" | "notes" | "notes_json")`：读取新产物。
- `generate_ppt`：生成正文讲解页、配图标注与演讲备注；优先复用已经生成且唯一匹配的中文图标签。

详细契约见 [扩展文档](../docs/extensions.md)。`complete` 只表示生成阶段完成；图像覆盖、术语与科学结论仍需核查。当前 HTTP 与 MCP 共用缓存，但同一工作区不应从两个进程同时启动同类任务。
