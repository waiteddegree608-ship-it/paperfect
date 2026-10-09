# Skills 与 MCP 接入

Paperfect Agent Pack 是可在其他项目接入的本地扩展包，入口为 `paperfect_agent/server.py`，通过 stdio 暴露 MCP 工具。它需要已安装 Paperfect 依赖的 Python 环境。当前不依赖插件商店发布。

## 配置

```powershell
python -m pip install -r requirements.txt
python -m pip install -r paperfect_agent/requirements.txt
```

在支持 `mcpServers` 的客户端中使用以下配置，替换为实际绝对路径：

```json
{
  "mcpServers": {
    "paperfect": {
      "command": "C:/path/to/paperfect/venv/Scripts/python.exe",
      "args": ["C:/path/to/paperfect/paperfect_agent/server.py"],
      "env": {
        "PAPERFECT_ROOT": "C:/path/to/paperfect",
        "PAPERFECT_WORK_DIR": "C:/path/to/research-output"
      }
    }
  }
}
```

不同客户端的配置入口可能不同；上例展示服务器启动参数。Key 写入本机 `.env` 或进程环境，不放到共享项目配置。指定 `PAPERFECT_WORK_DIR` 可与桌面文献库分开保存。

## 推荐调用

1. `health`，确认依赖与配置。
2. `ingest_pdf(pdf_path=...)`，记下返回的 `book_name`。
3. `list_skills` / `read_skill` 读取适用的生成规范。
4. `translate_reading(book_name, pages=[1,2,3], localize=true)` 创建中文阅读版和图译素材。
5. `generate_notes(book_name)` 创建全文详细解读，检查 `read_artifact(kind="notes_json")`。
6. `parse_paper` 后调用 `generate_ppt`，输出正文讲解页、配图标注和备注。

可单独执行需要的步骤。`get_artifacts` 返回文件路径；`read_artifact(kind="reading_manifest")` 可查看翻译范围和图素材记录。处理失败后先查看产物，`force=true` 会产生新的模型调用。

## 两类 Skills

| 位置 | 使用者 | 作用 |
| --- | --- | --- |
| `backend/skills` | Paperfect 运行时 | 向实际模型请求注入翻译、解读、PPT 规范 |
| `paperfect_agent/skills` | 外部 Agent | 指导工具选择、产物读取、续跑和核查 |

运行时 Skill 是带 YAML 元数据的 Markdown，正文通过 `skill_registry` 读取。新增 Skill 后接入调用点，并增加能验证实际行为的样本；仅添加文档不会自动改变生成行为。现有三个 Skill 由项目维护，可在开源仓库内直接修改，不要求用户安装本机私有 Skills。

## HTTP 扩展接口

- `GET /api/research/skills`：生成 Skills 与哈希。
- `POST /api/research/{book}/jobs`：`{"kind":"reading","pages":[1,2],"localize":true,"force":false}`；或 `kind="notes"`。
- `GET /api/research/{book}/jobs/{kind}`：任务状态与页进度。
- `GET /api/research/{book}/files/{relative-path}`：读取生成文件。

这些 API 面向本机桌面应用，当前没有多用户身份认证。不要直接把整个服务作为公共网络服务部署。
