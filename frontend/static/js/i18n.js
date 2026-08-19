/**
 * Paperfect i18n — Lightweight internationalization system
 * Usage: t('key') returns the translated string for the current language.
 * Language is persisted in localStorage('paperfect_lang').
 */

const TRANSLATIONS = {
  zh: {
    // ── Header / Nav ──
    "nav.library": "资料管理",
    "nav.prompts": "提示词管理",
    "nav.my_files": "我的资料",
    "nav.auto_classify": "自动分类",
    "nav.settings": "系统配置",
    "nav.back_home": "返回主页",
    "nav.toggle_theme": "切换昼夜模式",
    "nav.github": "前往 GitHub 项目主页",

    // ── Toolbox (batch PDF tools, no need to open a paper) ──
    "toolbox.title": "工具箱",
    "toolbox.pick_docs": "选择文献（合并需选 2 篇及以上）",
    "toolbox.search_placeholder": "搜索标题 / 文件名...",
    "toolbox.pick_tool": "选择工具",
    "toolbox.tool_merge": "合并 PDF（多选）",
    "toolbox.run": "执行",
    "toolbox.running": "执行中...",
    "toolbox.no_docs": "无匹配文献",
    "toolbox.angle": "旋转角度",
    "toolbox.range": "页面范围（如 1-5）",
    "toolbox.wm_text": "水印文字",
    "toolbox.password": "设置密码",
    "toolbox.password_current": "当前密码（无则留空）",
    "toolbox.merge_hint": "请在上方勾选 2 篇及以上文献，将按勾选顺序合并为一个 PDF。",
    "toolbox.pick_at_least_one": "请至少选择一篇文献",
    "toolbox.merge_need_two": "合并至少需要选择两篇文献",
    "toolbox.download": "下载合并结果",

    // ── Reader Workspace (browser-like tabs) ──
    "reader.smart_group": "智能分组",
    "reader.close_all": "关闭全部",
    "reader.hibernated_hint": "该标签已休眠以节省内存",
    "reader.wake": "点击唤醒",
    "reader.uncategorized": "未分类",

    // ── Dashboard ──
    "dash.upload_title": "拖入 PDF 或点击此处选择文件",
    "dash.upload_sub": "支持论文与教材的深度解析",
    "dash.folders_title": "我的文件夹",
    "dash.new_folder": "新建文件夹",
    "dash.recent_title": "最近上传",
    "dash.no_uploads": "暂无上传记录",
    "dash.drop_hint": "拖入 PDF 文件开始使用",
    "dash.files_unit": "个文件",
    "dash.all_folders": "全部文件夹",
    "dash.folder_empty_title": "此文件夹为空",
    "dash.folder_empty_sub": "上传文件时可选择存入此文件夹",

    // ── Folder actions ──
    "folder.create": "新建文件夹",
    "folder.rename": "重命名文件夹",
    "folder.name_label": "文件夹名称",
    "folder.name_placeholder": "输入文件夹名称...",
    "folder.new_name_label": "新名称",
    "folder.new_name_placeholder": "输入新名称...",
    "folder.confirm_create": "创建文件夹",
    "folder.confirm_rename": "确认重命名",
    "folder.ctx_rename": "重命名",
    "folder.ctx_delete": "删除文件夹",
    "folder.confirm_delete": "确定要删除文件夹「{name}」吗？文件夹内的文件不会被删除，但会移出该文件夹。",

    // ── Upload modal ──
    "upload.title": "上传文献",
    "upload.type_label": "将其作为何种类型解析？",
    "upload.type_book": "教材/书籍 (仅解析结构)",
    "upload.type_paper": "论文 (深度解析与打标)",
    "upload.folder_label": "存入文件夹",
    "upload.folder_default": "默认文件夹",
    "upload.folder_new_placeholder": "或新建文件夹...",
    "upload.prompt_label": "选择提示词方案",
    "upload.ppt_mode_label": "PPT生成模式",
    "upload.language_label": "生成语言",
    "upload.lang_zh": "中文 / Chinese",
    "upload.lang_en": "英文 / English",
    "upload.ppt_simple": "简单",
    "upload.ppt_creative": "详细 (Creative)",
    "upload.prompt_cs_ai": "计算机+人工智能",
    "upload.prompt_default": "默认提示词",
    "upload.confirm": "确认并开始上传",
    "upload.uploading": "上传引擎启动中...",
    "upload.error": "上传出错",
    "upload.current_file": "当前文件: ",
    "upload.batch_count": "已选择文件数: ",
    "upload.stages_label": "处理阶段（默认全开）",
    "upload.do_translate": "翻译 PDF",
    "upload.do_annotate": "AI 批注",
    "upload.do_ppt": "制作 PPT",

    // ── Auto classify ──
    "auto.title": "智能文献分类",
    "auto.sub": "基于AI标签自动对文献进行分类展示",

    // ── Confirm dialogs ──
    "confirm.delete_doc": "确定要永久删除该文献吗？该操作不可逆转！",

    // ── Chat page ──
    "chat.original": "原文",
    "chat.annotated": "AI标注",
    "chat.translated": "翻译",
    "chat.ppt": "PPT",
    "chat.ai": "AI",
    "chat.realtime": "实时翻译",
    "chat.back": "返回主页",
    "chat.pane_original": "PDF 原文版",
    "chat.pane_annotated": "AI 批注版 PDF",
    "chat.pane_translated": "PDF 翻译版",
    "chat.pane_ppt": "PPT 独立流式编辑器",
    "chat.pane_realtime": "实时翻译",
    "chat.history": "历史对话",
    "chat.new_session": "开启新对话",
    "chat.placeholder": "请输入您关于这档文档的任何疑问，或者指定页码进行问答...",
    "chat.send": "发送 (Enter)",
    "chat.source_label": "原文 (支持划选捕获与手动修改)",
    "chat.source_placeholder": "在主页面的文献中划选文字，将自动显示在此处...",
    "chat.translate_btn": "翻译",
    "chat.result_label": "翻译结果",
    "chat.status_waiting": "等待中...",
    "chat.embed_back": "嵌入网页",
    "chat.detach": "脱离容器并置顶",
    "chat.maximize": "最大化",
    "chat.close": "关闭",
    "chat.no_annotation": "尚未生成AI批注",
    "chat.tools": "工具",
    "chat.tool_pages": "导出页面为图片",
    "chat.tool_figures": "导出论文配图",
    "chat.tool_docx": "转为 Word",
    "chat.tool_md": "导出 Markdown",
    "chat.tool_tex": "导出 LaTeX",
    "chat.tool_ocr": "OCR 可检索 PDF",
    "chat.tool_rotate": "旋转 PDF",
    "chat.tool_split": "提取页面范围",
    "chat.tool_compress": "压缩 PDF",
    "chat.tool_watermark": "添加水印",
    "chat.tool_protect": "加密 PDF",
    "chat.tool_unlock": "解密 PDF",

    // ── Universal search ──
    "search.placeholder": "搜索文献...",
    "search.btn": "万能搜索",

    // ── Prompt Management ──
    "prompt.saved_list": "已保存的提示词",
    "prompt.new_btn": "新建提示词",
    "prompt.new_dialog": "请输入新提示词方案的名称:",
    "prompt.editing": "当前编辑:",
    "prompt.delete": "删除",
    "prompt.save": "保存",
    "prompt.save_ok": "保存成功",
    "prompt.save_fail": "保存失败",
    "prompt.confirm_delete": "确认删除 \"{name}\" 吗？",
    "prompt.add_segment": "+ 添加新段落",
    "prompt.segment_delete": "删除",
    "prompt.empty_hint": "请在左侧选择或新建一个提示词方案",
    "prompt.no_prompts": "暂无提示词方案",

    // ── Settings ──
    "settings.title": "大模型引擎配置",
    "settings.url_label": "API URL (Base)",
    "settings.keys_label": "API Keys (支持多秘钥并发轮询)",
    "settings.keys_add": "+ 增加 API Key",
    "settings.model_label": "解析 / PPT 看图模型",
    "settings.text_model_label": "文本/翻译/批注模型（可留空与解析模型相同）",
    "settings.save_btn": "保存配置并全局生效",
    "settings.saving": "保存中...",
    "settings.saved": "配置已保存！",
    "settings.failed": "保存失败",

    // ── Auto tab names ──
    "auto.tab_classify": "分类",
    "auto.tab_relations": "论文脉络",
    "auto.tab_search": "万能搜索",
    "auto.search_graph_nodes": "在图谱中搜索节点...",
    "auto.lineage_pick": "从左侧选择一篇论文",
    "auto.lineage_hint": "",
    "auto.lineage_related": "库内相关",
    "auto.lineage_refs": "参考文献精选",
    "auto.lineage_in_lib": "已在库中",
    "auto.lineage_author": "同作者工作",
    "auto.lineage_empty": "暂无库内关联",
    "auto.lineage_dossier": "论文速览",
    "auto.lineage_hero_fig": "最具辨识度的配图",
    "auto.lineage_arch_fig": "模型架构 / 材料结构图",
    "auto.lineage_arch_same": "架构图与主配图为同一张（该文最醒目的图即框架图）。",
    "auto.lineage_ai_abs": "AI 摘要",
    "auto.lineage_qa": "提示词问题与解读",
    "auto.lineage_no_abs": "暂无摘要。请等解析完成或点击重新打标。",
    "auto.lineage_no_qa": "知识库尚未生成，解析完成后将显示提示词问答。",
    "auto.reason_keywords": "关键词相近",
    "auto.reason_field": "同一领域",
    "auto.reason_author": "同作者",
    "auto.retag": "重标",
    "auto.retag_ok": "已重新打标",
    "auto.retag_fail": "打标失败",

    // ── Right Sidebar Filters ──
    "filter.search_title": "文献检索",
    "filter.search_placeholder": "标题/摘要关键词...",
    "filter.type_title": "文献类型",
    "filter.review": "综述",
    "filter.research": "研究",
    "filter.core_title": "核心期刊",
    "filter.cssci": "南大核心",
    "filter.pku": "北大核心",
    "filter.chinese": "中文核心",
    "filter.jcr_partition": "Jcr分区-2026",
    "filter.cas_partition": "中科院分区-2026",
    "filter.ccf_partition": "CCF分区-2026",
    "filter.q1": "一区",
    "filter.q2": "二区",
    "filter.q3": "三区",
    "filter.q4": "四区",

    // ── Chat dynamic ──
    "chat.sync_scroll_on": "滚动同步: 开",
    "chat.sync_scroll_off": "滚动同步: 关",
  },

  en: {
    // ── Header / Nav ──
    "nav.library": "Library",
    "nav.prompts": "Prompts",
    "nav.my_files": "My Files",
    "nav.auto_classify": "Auto Classify",
    "nav.settings": "Settings",
    "nav.back_home": "Back to Home",
    "nav.toggle_theme": "Toggle Light/Dark",
    "nav.github": "Go to GitHub Repository",

    // ── Toolbox ──
    "toolbox.title": "Toolbox",
    "toolbox.pick_docs": "Pick document(s) (merge needs 2+)",
    "toolbox.search_placeholder": "Search title / filename...",
    "toolbox.pick_tool": "Choose a tool",
    "toolbox.tool_merge": "Merge PDFs (multi-select)",
    "toolbox.run": "Run",
    "toolbox.running": "Running...",
    "toolbox.no_docs": "No matching documents",
    "toolbox.angle": "Rotation angle",
    "toolbox.range": "Page range (e.g. 1-5)",
    "toolbox.wm_text": "Watermark text",
    "toolbox.password": "Set password",
    "toolbox.password_current": "Current password (leave empty if none)",
    "toolbox.merge_hint": "Check 2+ documents above; they will be merged in the checked order.",
    "toolbox.pick_at_least_one": "Please select at least one document",
    "toolbox.merge_need_two": "Merging needs at least two documents",
    "toolbox.download": "Download merged PDF",

    // ── Reader Workspace ──
    "reader.smart_group": "Smart group",
    "reader.close_all": "Close all",
    "reader.hibernated_hint": "This tab was hibernated to save memory",
    "reader.wake": "Click to wake",
    "reader.uncategorized": "Uncategorized",

    // ── Dashboard ──
    "dash.upload_title": "Drop PDF here or click to select",
    "dash.upload_sub": "Deep analysis for papers and textbooks",
    "dash.folders_title": "My Folders",
    "dash.new_folder": "New Folder",
    "dash.recent_title": "Recent Uploads",
    "dash.no_uploads": "No uploads yet",
    "dash.drop_hint": "Drop a PDF to get started",
    "dash.files_unit": "files",
    "dash.all_folders": "All Folders",
    "dash.folder_empty_title": "This folder is empty",
    "dash.folder_empty_sub": "You can choose this folder when uploading",

    // ── Folder actions ──
    "folder.create": "Create Folder",
    "folder.rename": "Rename Folder",
    "folder.name_label": "Folder Name",
    "folder.name_placeholder": "Enter folder name...",
    "folder.new_name_label": "New Name",
    "folder.new_name_placeholder": "Enter new name...",
    "folder.confirm_create": "Create Folder",
    "folder.confirm_rename": "Confirm Rename",
    "folder.ctx_rename": "Rename",
    "folder.ctx_delete": "Delete Folder",
    "folder.confirm_delete": "Delete folder \"{name}\"? Files inside will not be deleted but will be moved out.",

    // ── Upload modal ──
    "upload.title": "Upload Document",
    "upload.type_label": "Parse as:",
    "upload.type_book": "Textbook (structure only)",
    "upload.type_paper": "Paper (deep analysis & tagging)",
    "upload.folder_label": "Save to Folder",
    "upload.folder_default": "Default Folder",
    "upload.folder_new_placeholder": "Or create new folder...",
    "upload.prompt_label": "Prompt Scheme",
    "upload.ppt_mode_label": "PPT Mode",
    "upload.language_label": "Output Language",
    "upload.lang_zh": "Chinese",
    "upload.lang_en": "English",
    "upload.ppt_simple": "Simple",
    "upload.ppt_creative": "Detailed (Creative)",
    "upload.prompt_cs_ai": "CS + AI",
    "upload.prompt_default": "Default Prompt",
    "upload.confirm": "Confirm & Upload",
    "upload.uploading": "Upload engine starting...",
    "upload.error": "Upload failed",
    "upload.current_file": "Selected: ",
    "upload.batch_count": "Files selected: ",
    "upload.stages_label": "Pipeline stages (all on by default)",
    "upload.do_translate": "Translate PDF",
    "upload.do_annotate": "AI annotations",
    "upload.do_ppt": "Generate PPT",

    // ── Auto classify ──
    "auto.title": "Smart Classification",
    "auto.sub": "AI-powered automatic document classification",

    // ── Confirm dialogs ──
    "confirm.delete_doc": "Permanently delete this document? This action cannot be undone!",

    // ── Chat page ──
    "chat.original": "Original",
    "chat.annotated": "AI Annotated",
    "chat.translated": "Translated",
    "chat.ppt": "PPT",
    "chat.ai": "AI",
    "chat.realtime": "Live Translate",
    "chat.back": "Back",
    "chat.pane_original": "Original PDF",
    "chat.pane_annotated": "AI Annotated PDF",
    "chat.pane_translated": "Translated PDF",
    "chat.pane_ppt": "PPT Editor",
    "chat.pane_realtime": "Live Translate",
    "chat.history": "Chat History",
    "chat.new_session": "New Chat",
    "chat.placeholder": "Ask anything about this document, or specify a page to discuss...",
    "chat.send": "Send (Enter)",
    "chat.source_label": "Source (select text from PDF to auto-capture)",
    "chat.source_placeholder": "Select text in the PDF viewer, it will appear here...",
    "chat.translate_btn": "Translate",
    "chat.result_label": "Translation",
    "chat.status_waiting": "Waiting...",
    "chat.embed_back": "Embed in Page",
    "chat.detach": "Detach & Float",
    "chat.maximize": "Maximize",
    "chat.close": "Close",
    "chat.no_annotation": "AI annotations not generated yet",
    "chat.tools": "Tools",
    "chat.tool_pages": "Export pages as images",
    "chat.tool_figures": "Export paper figures",
    "chat.tool_docx": "Convert to Word",
    "chat.tool_md": "Export Markdown",
    "chat.tool_tex": "Export LaTeX",
    "chat.tool_ocr": "OCR searchable PDF",
    "chat.tool_rotate": "Rotate PDF",
    "chat.tool_split": "Extract page range",
    "chat.tool_compress": "Compress PDF",
    "chat.tool_watermark": "Add watermark",
    "chat.tool_protect": "Encrypt PDF",
    "chat.tool_unlock": "Decrypt PDF",

    // ── Universal search ──
    "search.placeholder": "Search documents...",
    "search.btn": "Smart Search",

    // ── Prompt Management ──
    "prompt.saved_list": "Saved Prompts",
    "prompt.new_btn": "New Prompt",
    "prompt.new_dialog": "Enter a name for the new prompt scheme:",
    "prompt.editing": "Editing:",
    "prompt.delete": "Delete",
    "prompt.save": "Save",
    "prompt.save_ok": "Saved successfully",
    "prompt.save_fail": "Save failed",
    "prompt.confirm_delete": "Delete \"{name}\"?",
    "prompt.add_segment": "+ Add Section",
    "prompt.segment_delete": "Delete",
    "prompt.empty_hint": "Select or create a prompt scheme from the sidebar",
    "prompt.no_prompts": "No prompt schemes yet",

    // ── Settings ──
    "settings.title": "LLM Engines Settings",
    "settings.url_label": "API URL (Base)",
    "settings.keys_label": "API Keys (Supports multiple keys rotation)",
    "settings.keys_add": "+ Add API Key",
    "settings.model_label": "Parse / PPT vision model",
    "settings.text_model_label": "Text / translate / annotate model (leave blank to match parse model)",
    "settings.save_btn": "Save & Apply",
    "settings.saving": "Saving...",
    "settings.saved": "Saved!",
    "settings.failed": "Failed",

    // ── Auto tab names ──
    "auto.tab_classify": "Categories",
    "auto.tab_relations": "Paper lineage",
    "auto.tab_search": "Smart Search",
    "auto.search_graph_nodes": "Search nodes in graph...",
    "auto.lineage_pick": "Pick a paper on the left",
    "auto.lineage_hint": "Related papers, worthwhile references, and an AI dossier of figures plus Q&A.",
    "auto.lineage_related": "Related in library",
    "auto.lineage_refs": "References worth reading",
    "auto.lineage_in_lib": "Already in library",
    "auto.lineage_author": "Same-author work",
    "auto.lineage_empty": "No library relations yet",
    "auto.lineage_dossier": "Paper dossier",
    "auto.lineage_hero_fig": "Most distinctive figure",
    "auto.lineage_arch_fig": "Model architecture / structure figure",
    "auto.lineage_arch_same": "The architecture figure is the same as the hero figure.",
    "auto.lineage_ai_abs": "AI abstract",
    "auto.lineage_qa": "Prompt questions and answers",
    "auto.lineage_no_abs": "No abstract yet. Wait for parsing or re-tag.",
    "auto.lineage_no_qa": "Knowledge base not ready; prompt Q&A will appear after parse.",
    "auto.reason_keywords": "shared keywords",
    "auto.reason_field": "same field",
    "auto.reason_author": "same author",
    "auto.retag": "Retag",
    "auto.retag_ok": "Retagged",
    "auto.retag_fail": "Retag failed",

    // ── Right Sidebar Filters ──
    "filter.search_title": "Literature Search",
    "filter.search_placeholder": "Title/Abstract/Keywords...",
    "filter.type_title": "Literature Type",
    "filter.review": "Review",
    "filter.research": "Research",
    "filter.core_title": "Core Journals",
    "filter.cssci": "CSSCI",
    "filter.pku": "PKU Core",
    "filter.chinese": "Chinese Core",
    "filter.jcr_partition": "JCR Partition - 2026",
    "filter.cas_partition": "CAS Partition - 2026",
    "filter.ccf_partition": "CCF Partition - 2026",
    "filter.q1": "Q1",
    "filter.q2": "Q2",
    "filter.q3": "Q3",
    "filter.q4": "Q4",

    // ── Chat dynamic ──
    "chat.sync_scroll_on": "Scroll Sync: On",
    "chat.sync_scroll_off": "Scroll Sync: Off",
  }
};

// ── Core API ──

function getLang() {
  return localStorage.getItem('paperfect_lang') || 'zh';
}

function setLang(lang) {
  localStorage.setItem('paperfect_lang', lang);
  // Dispatch event so Vue apps and other listeners can react
  window.dispatchEvent(new CustomEvent('lang-changed', { detail: { lang } }));
}

function t(key, params) {
  const lang = getLang();
  let str = (TRANSLATIONS[lang] && TRANSLATIONS[lang][key]) || TRANSLATIONS['zh'][key] || key;
  // Simple template replacement: t('key', {name: 'foo'}) replaces {name}
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      str = str.replace(`{${k}}`, v);
    }
  }
  return str;
}

// Expose globally
window.TRANSLATIONS = TRANSLATIONS;
window.getLang = getLang;
window.setLang = setLang;
window.t = t;
