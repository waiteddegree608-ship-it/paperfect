# 如何测试 Paperfect 便携版 EXE（安装包之前）

## 产物位置

| 文件 | 说明 |
|------|------|
| `dist_electron\win-unpacked\Paperfect.exe` | **推荐先测这个**（解包目录，日志好查） |
| `dist_electron\Paperfect-2.0.0-portable.exe` | 单文件便携版（约 167MB） |

不需要：`run.bat`、本机 Python、本机 Node、手动起服务器。

## 测试步骤

1. 关掉所有正在跑的 Paperfect / `run.bat` / 占用 8900 的 Python。
2. 双击 **`dist_electron\win-unpacked\Paperfect.exe`**。
3. 首次启动可能稍慢（后端 onefile 解压），最多约 1–2 分钟；之后应打开主窗口。
4. 检查：
   - 文库界面是否正常
   - 浅色主题是否正常
   - 打开一篇论文 → PPT 编辑器工具栏是否可换行、浅色、无 Auto Layout 旧按钮
   - 设置页 API 是否能读到 `.env`（打包时已拷贝你当前项目的 `.env`）
5. 若失败：看
   - `dist_electron\win-unpacked\resources\dist_portable\app_debug.log`
   - 项目根目录附近的 `app_debug.log` / `backend_stdout.log`（Electron 写在 resources 上级时）

## 重新打包

```bat
cd /d E:\workspace\paperfect
python build_portable_exe.py
```

或：

```bat
npm run build:portable
```

## 你确认 EXE 没问题后

再做 **NSIS 安装包**（桌面快捷方式、选安装目录等）：

```bat
npm run dist:installer
```
