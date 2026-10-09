# Paperfect PPT generator

`generate_full_ppt.js` 是桌面与 MCP 共用的生成入口。`research_deck.js` 负责正文页规划、可编辑中文标签和带页码的讲解备注，`prepare_ppt_context.py` 提取带物理页码的论文文本。

```powershell
npm ci
```

通常通过桌面或 MCP 的 `generate_ppt` 调用。运行时使用 `PPT_API_URL`、`PPT_MODEL` 和 `PPT_API_KEY`；上层通过 `PAPERFECT_PPT_API_KEY` 环境变量传给子进程，避免凭据出现在命令行日志里。

输入为知识库 Markdown、images 目录以及同一论文目录内 raw 下的原始 PDF。图片支持 PNG、JPEG 与 SVG。若已有 research/reading/manifest.json，会匹配中文标签素材。生成指令来自 ../../skills/paper-presentation/SKILL.md。

输出包括 PPTX、slide_sync_map.json、ppt_status.json，以及带输入指纹的规划/配图缓存。部分失败返回退出码 4，保留已有 PPT 供检查和续跑。没有有效正文页或图片时不会声称生成成功。

`server.js` 与 React/Vite 页面属于独立图表编辑开发入口；主应用使用 FastAPI 的 PPT 路由。请使用可公开的演示素材，页面不包含私人论文示例。

实际渲染仍需在 PowerPoint 或兼容查看器中检查。文件结构校验不能证明图表解释准确或版式没有溢出。
