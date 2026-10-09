# 参与 Paperfect

先按 README 启动源码版，并使用独立测试文献。请勿把自己的 `.env`、论文库、数据库、API 响应、导出文件或浏览器配置提交进仓库。

## 提交改进

Issue 请说明系统版本、运行方式、复现步骤、预期和实际结果。日志应移除 API Key、个人路径及论文隐私内容。提交图译问题时，注明 PDF 物理页码、图号、错误标签和预期术语；仅提供你有权共享的材料。

代码修改尽量围绕一个问题，PR 描述实际行为变化、验证方式和已知限制。不要把 mock 模型的测试通过描述为真实论文质量验证。

## 验证

```powershell
python -m unittest discover -s tests -v
node --check backend/standalone_pdf2ppt/ppt_maker/generate_full_ppt.js
node --check frontend/static/js/research_workspace.js
```

配置、来源页码、缓存命中/失效、部分失败、图片标签可编辑性是关键行为。变更布局后应打开实际 PPTX，检查文本溢出、图像裁剪、字体替换和备注。保留合成样本，不把受版权保护的整篇论文用作公开测试夹具。

## 扩展生成能力

运行时 Skill 位于 `backend/skills`，外部 Agent 调用指南位于 `paperfect_agent/skills`。新增能力需同时考虑桌面入口、MCP 工具、产物契约与缓存，不仅添加提示词文件。具体接口见 [扩展文档](docs/extensions.md)。

提交贡献意味着你有权以本项目自有代码采用的 MIT 许可提供这些贡献。第三方代码需保留其原始许可与来源，不要将其重新标成 MIT。
