# 启动空白 / 卡死 — 2026-07-27 关键修复

## 截图现象
顶栏有 Neon / 中英 / 设置，**中间整片黑空**，导航文字也是空的。

## 真正根因（已用 Electron 控制台复现）
```
Uncaught SyntaxError: Identifier 't' has already been declared
```
- `i18n.js` 定义了全局 `function t`
- `library/main.js` 顶层又写了 `const t = ...`
- 浏览器经典 script **共享词法作用域** → 整份 main.js 解析失败
- **Vue 永不挂载** → 只剩静态 HTML 壳（`v-text` 空按钮 + 空 router-view）

“有时能启动”：可能是旧缓存 / 未加载到带 bug 的 main.js。

## 本次修复
1. 顶层改为 `function translate(...)`，setup 里 `t: translate`
2. 缓存 bust：`main.js?v=2026072703`
3. 启动 2.5s 后若仍空白，底部红条提示
4. SQLite `WAL` + `busy_timeout=30s`，减轻进退页面时写锁卡死
5. 已同步到 `dist_portable` 与 `dist_electron/win-unpacked/...`

## 请你现在这样重启
1. 任务管理器结束所有 `Paperfect.exe` / 相关 `python.exe` / 占 8900 的进程
2. 开发：`cd E:\workspace\paperfect` → `npm start`
   或便携：`dist_electron\win-unpacked\Paperfect.exe`
3. 应看到：导航「资料管理」+ 文件夹 + 最近上传，而不是黑屏

若仍异常：F12 Console 把红字发我。
