# Paperfect 安装包说明（面向用户）

## 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | **Windows 10 或 Windows 11**（不支持 Windows 7/8） |
| 架构 | **64 位 (x64)** 仅支持 |
| 内存 | 建议 **8 GB+**（解析大论文时更稳） |
| 磁盘 | 安装约 **400–600 MB**，另需工作空间存放 PDF/PPT |
| 网络 | 需要可访问你配置的大模型 API（解析/翻译/PPT 均走 API） |
| 其它 | **无需**自备 Python / Node.js；安装包已内置运行时 |

不支持：32 位系统、ARM 版 Windows（未测试）、Windows Server 精简环境（未保证）。

## 安装文件

- 主安装包：`Paperfect-Setup-2.0.0.exe`  
  路径：`E:\workspace\paperfect\dist_electron\Paperfect-Setup-2.0.0.exe`  
  也可使用项目根目录副本：`Paperfect_Setup.exe`

## 安装步骤

1. 双击 **Paperfect-Setup-*.exe**
2. 选择安装目录（默认可改）
3. 完成安装后可从桌面快捷方式或开始菜单启动 **Paperfect**
4. 首次启动打开 **账户设置**，填写你的 **API Key**（可添加多个，自动轮询并发）
   API 地址与模型已由官方预先配置好，无需（也无法）自行修改。
   保存后即可上传 PDF 使用

## 安装包内已包含（用户无需再装）

- Electron 桌面壳
- Python 后端（`paperfect.exe`，PyInstaller）
- Node.js 运行时（仅用于 PPT 生成）
- 前端页面与 PPT 编辑器静态资源

## 卸载

通过「设置 → 应用 → 已安装的应用」卸载 Paperfect。  
用户文库数据默认保留在安装目录下的 `resources/dist_portable/data`（卸载是否删除取决于系统/卸载选项）。

## 开发者重新打包

```bat
cd /d E:\workspace\paperfect
python build_installer.py
```

密钥不会打进安装包：使用 `env.release.template` 的空配置。
