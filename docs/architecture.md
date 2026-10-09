# 架构与扩展

Paperfect 由桌面工作台、共享处理服务、Agent 扩展包组成。桌面与 MCP 使用同一套 Python 服务和磁盘产物；PPT 使用独立 Node.js 生成器。

```text
Electron / 浏览器                 MCP 客户端
        │                            │
frontend → backend/api      paperfect_agent/server.py
        └──────────┬─────────────────┘
             backend/services
          配置 / Skills / 缓存 / PDF
                   │
        standalone_pdf2ppt/ppt_maker
                   │
          data/papers/<book>/
```

## 模块边界

| 目录 | 职责 |
| --- | --- |
| `backend/core` | 配置、数据库初始化等基础设施 |
| `backend/api` | 桌面 HTTP API；`research_router` 提供精读任务与文件读取 |
| `backend/services` | 解析、翻译、批注、检索、精读产物 |
| `backend/skills` | 真正传给模型的版本化生成指令 |
| `backend/standalone_pdf2ppt` | 配图提取、PPT 规划、排版与导出 |
| `frontend` | Vue 文献库、PDF.js 阅读器、PPT 编辑器 |
| `paperfect_agent` | stdio MCP、外部 Agent 调用指南与扩展包清单 |
| `tests` | 不依赖真实 Key 的回归及本地模拟 API 集成验证 |
| `docs` | 用户资料、架构、扩展与历史设计 |
| `scripts` | 仓库维护与发布工具 |

## 产物契约

```text
data/papers/<book>/
├── raw/<book>.pdf
├── parsed/<book>_KnowledgeBase.md
├── translated/<book>_translated.pdf
├── marked/annotations.json
├── images/Figure_N.png                 # 也支持 SVG 输入
├── pptx/
│   ├── <book>_Full_Presentation.pptx
│   ├── slide_sync_map.json
│   ├── ppt_status.json
│   └── narrative_zh.json               # 正文规划缓存
└── research/
    ├── reading/
    │   ├── index.html                  # 重排中文阅读版
    │   ├── manifest.json               # 范围、源哈希、失败、图素材
    │   ├── assets/                     # 原图、原始 SVG、中文 SVG
    │   └── cache/                      # 响应、模型、指纹、usage
    └── notes/
        ├── index.html
        ├── notes.md
        ├── notes.json                  # 页码、证据、待核查项
        └── cache/
```

原始 SVG 来自 PDF 区域导出，PDF 内已有位图仍保持位图。中文 SVG 用原图底图和可编辑文字覆盖层组成。PPT 通过图号及已知页码匹配唯一素材，并把中文标签写为原生文本框；重名或匹配不确定时保留原配图。

## 任务与缓存

精读 HTTP 任务最多同时执行 2 个，连同排队任务最多 4 个；磁盘记录状态，进程重启后旧运行任务显示为 interrupted。再次点击可续用成功缓存。MCP 工具为同步长任务，客户端需允许足够的工具超时。

阅读版缓存指纹包含服务地址、模型、Skill 与输入页图/文字；PPT 还包含实际图片及标签。`complete` 只代表生成阶段成功，`draft` 表示解读初稿，`partial` 表示存在失败；均不等于人工审稿通过。

详细解读按完整物理页分块，不用前几千字代替全文。扫描论文需先 OCR。PPT 规划使用带页码的文本摘录，截断会标记 `excerpt_truncated`；复杂图表仍需要人工核查。

## 已有架构债务

现有数据库、文献库 UI、传统 PDF 翻译和 PPT 子系统仍具有历史耦合。本轮新增能力集中在共享服务和独立路由，不移动运行时依赖路径。长期可逐步拆分 Vue 页面与任务队列，并把用户数据目录迁到独立可配置位置；这些尚未完成。
