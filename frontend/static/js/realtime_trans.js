/**
 * RealtimeTranslationManager
 * 
 * 负责实时翻译功能的双模架构：
 * 1. 子容器模式 (Embedded)：默认在界面的 pane-realtime-trans 中展示。
 * 2. 画中画模式 (Document PiP)：真正的系统级全局置顶小窗，可拖出浏览器。
 * 3. 降级悬浮模式 (Fallback)：如果浏览器不支持 PiP，回退到普通悬浮窗并提供 resize。
 */

class RealtimeTranslationManager {
    constructor() {
        const match = window.location.pathname.match(/\/chat\/([^\/]+)/);
        this.bookName = match ? decodeURIComponent(match[1]) : '';
        
        this.pane = document.getElementById('pane-realtime-trans');
        if (!this.pane) return;

        this.header = document.getElementById('realtime-header');
        this.contentWrapper = document.getElementById('realtime-content-wrapper');
        this.btnDetach = document.getElementById('realtime-btn-detach');
        this.btnMax = document.getElementById('realtime-btn-max');
        this.btnClose = document.getElementById('realtime-btn-close');
        
        this.sourceText = document.getElementById('realtime-source-text');
        this.resultText = document.getElementById('realtime-result-text');
        this.statusText = document.getElementById('realtime-status');
        this.btnTranslate = document.getElementById('realtime-btn-translate');

        this.isDetached = false;
        this.pipWindow = null;
        
        // 拖拽相关 (仅 Fallback 模式用)
        this.isDragging = false;
        this.dragOffset = { x: 0, y: 0 };
        this.originalStyles = {
            position: '', zIndex: '', left: '', top: '', width: '', height: '', flex: '', resize: '', overflow: ''
        };

        this.lastSelectedText = '';
        this.translateTimeout = null;

        this.initUIEvents();
        this.initSelectionListeners();
    }

    initUIEvents() {
        // 关闭按钮
        this.btnClose.addEventListener('click', () => {
            const btn = document.getElementById('btn-layout-realtime');
            if (btn && btn.classList.contains('active')) {
                btn.click(); // 复用 togglePane 逻辑
            }
        });

        // 脱离/嵌入按钮
        this.btnDetach.addEventListener('click', () => {
            this.toggleDetach();
        });

        // 手动修改原文重新翻译
        this.sourceText.addEventListener('input', () => {
            if (this.translateTimeout) clearTimeout(this.translateTimeout);
            this.translateTimeout = setTimeout(() => {
                const text = this.sourceText.value.trim();
                if (text) this.triggerTranslation(text);
            }, 1000);
        });

        this.btnTranslate.addEventListener('click', () => {
            const text = this.sourceText.value.trim();
            if (text) this.triggerTranslation(text);
        });

        // Fallback 模式拖拽逻辑
        this.header.addEventListener('mousedown', (e) => {
            // 如果没脱离，或者是真PiP模式，不走网页拖拽
            if (!this.isDetached || this.pipWindow) return;
            if (e.target.tagName.toLowerCase() === 'button') return;

            this.isDragging = true;
            this.header.style.cursor = 'grabbing';
            const rect = this.pane.getBoundingClientRect();
            this.dragOffset.x = e.clientX - rect.left;
            this.dragOffset.y = e.clientY - rect.top;

            document.addEventListener('mousemove', this.onMouseMove);
            document.addEventListener('mouseup', this.onMouseUp);
            document.querySelectorAll('iframe').forEach(ifr => ifr.style.pointerEvents = 'none');
        });

        this.onMouseMove = (e) => {
            if (!this.isDragging) return;
            // 直接修改 left/top，由于去除了 transition，会非常跟手
            this.pane.style.left = (e.clientX - this.dragOffset.x) + 'px';
            this.pane.style.top = (e.clientY - this.dragOffset.y) + 'px';
        };

        this.onMouseUp = (e) => {
            this.isDragging = false;
            this.header.style.cursor = 'move';
            document.removeEventListener('mousemove', this.onMouseMove);
            document.removeEventListener('mouseup', this.onMouseUp);
            document.querySelectorAll('iframe').forEach(ifr => ifr.style.pointerEvents = 'auto');
        };
    }

    async toggleDetach() {
        if (this.isDetached) {
            // 从脱离状态还原
            if (this.pipWindow) {
                this.pipWindow.close(); // 会触发 pagehide 事件处理还原
            } else {
                this.restoreFallbackPane();
            }
        } else {
            // 尝试开启 Document PiP
            if ('documentPictureInPicture' in window) {
                try {
                    await this.openPiPWindow();
                    return; // 成功则结束
                } catch (err) {
                    console.warn("PiP 唤起失败，回退到网页悬浮窗", err);
                    // 失败则降级
                }
            }
            // 降级方案
            this.openFallbackPane();
        }
    }

    async openPiPWindow() {
        this.pipWindow = await window.documentPictureInPicture.requestWindow({
            width: 400,
            height: 600
        });

        // 复制主页面的基础样式，主要是字体和颜色变量
        [...document.styleSheets].forEach((styleSheet) => {
            try {
                const cssRules = [...styleSheet.cssRules].map((rule) => rule.cssText).join('');
                const style = document.createElement('style');
                style.textContent = cssRules;
                this.pipWindow.document.head.appendChild(style);
            } catch (e) {
                const link = document.createElement('link');
                link.rel = 'stylesheet';
                link.type = styleSheet.type;
                link.media = styleSheet.media;
                link.href = styleSheet.href;
                this.pipWindow.document.head.appendChild(link);
            }
        });
        
        // 基础样式覆盖
        const baseStyle = document.createElement('style');
        baseStyle.textContent = `
            body { margin: 0; padding: 0; background: #16161D; height: 100vh; overflow: hidden; }
            #realtime-content-wrapper { height: 100%; box-sizing: border-box; }
        `;
        this.pipWindow.document.head.appendChild(baseStyle);

        // 将 content-wrapper 移动到 PiP 中
        this.pipWindow.document.body.appendChild(this.contentWrapper);

        // 状态更新
        this.isDetached = true;
        this.pane.style.display = 'none'; // 隐藏主网页的壳子

        // 监听 PiP 关闭
        this.pipWindow.addEventListener("pagehide", (event) => {
            this.pane.appendChild(this.contentWrapper); // 把内容拿回来
            
            const btn = document.getElementById('btn-layout-realtime');
            if (btn && btn.classList.contains('active')) {
                this.pane.style.display = 'flex';
            }
            this.isDetached = false;
            this.pipWindow = null;
        });
    }

    openFallbackPane() {
        this.isDetached = true;
        this.btnDetach.textContent = '↙';
        this.btnDetach.title = "嵌入容器";
        this.header.style.cursor = 'move';
        
        // 移除 flex 限制，变为 absolute
        this.pane.style.position = 'fixed';
        this.pane.style.zIndex = '9999';
        this.pane.style.width = '350px';
        this.pane.style.height = '500px';
        this.pane.style.left = Math.max(0, window.innerWidth - 370) + 'px';
        this.pane.style.top = '100px';
        this.pane.style.boxShadow = '0 10px 30px rgba(0,0,0,0.5)';
        
        // 为了支持原生缩放
        this.pane.style.resize = 'both';
        
        // 保存并移除 flex
        this.originalStyles.flex = this.pane.style.flex;
        this.pane.style.flex = 'none';
        
        if (window.updateResizers) window.updateResizers();
    }

    restoreFallbackPane() {
        this.isDetached = false;
        this.btnDetach.textContent = '↗';
        this.btnDetach.title = "脱离容器并置顶";
        this.header.style.cursor = 'default';
        
        this.pane.style.position = '';
        this.pane.style.zIndex = '';
        this.pane.style.width = '';
        this.pane.style.height = '';
        this.pane.style.left = '';
        this.pane.style.top = '';
        this.pane.style.boxShadow = '';
        this.pane.style.resize = '';
        this.pane.style.flex = this.originalStyles.flex || '1 1 0%';
        
        if (window.updateResizers) window.updateResizers();
    }

    initSelectionListeners() {
        setInterval(() => {
            document.querySelectorAll('iframe').forEach(iframe => {
                if (!iframe.id.startsWith('iframe-')) return;
                if (iframe.dataset.transListenerAttached) return;

                try {
                    const doc = iframe.contentWindow.document;
                    if (doc) {
                        doc.addEventListener('mouseup', () => {
                            this.handleSelection(iframe.contentWindow);
                        });
                        doc.addEventListener('keyup', (e) => {
                            if (e.shiftKey && (e.key.startsWith('Arrow') || e.key === 'Home' || e.key === 'End')) {
                                this.handleSelection(iframe.contentWindow);
                            }
                        });
                        iframe.dataset.transListenerAttached = 'true';
                    }
                } catch (e) {}
            });
        }, 1000);
    }

    handleSelection(win) {
        // 如果面板既没有展示在主窗口，也没打开PiP，说明被完全关掉了，此时不处理
        if (this.pane.style.display === 'none' && !this.pipWindow) return;

        const selection = win.getSelection();
        let text = selection.toString().trim();
        
        // 将多个换行符和空格压缩为一个空格，解决断句问题
        text = text.replace(/\s+/g, ' ').trim();
        
        if (!text || text === this.lastSelectedText) return;
        this.lastSelectedText = text;
        
        this.sourceText.value = text;
        this.triggerTranslation(text);
    }

    async triggerTranslation(text) {
        if (this.translateTimeout) clearTimeout(this.translateTimeout);
        
        this.statusText.textContent = "请求中...";
        this.statusText.style.color = "var(--secondary-accent)";
        this.resultText.innerHTML = "<span style='color: var(--text-muted);'>正在召唤翻译大模型...</span>";

        try {
            const res = await fetch("/api/realtime_translate", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({
                    book_name: this.bookName,
                    selected_text: text
                })
            });
            
            if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
            
            const data = await res.json();
            this.statusText.textContent = "✓ 完成";
            this.statusText.style.color = "#10b981";
            this.resultText.textContent = data.translation;
            
        } catch (e) {
            this.statusText.textContent = "× 错误";
            this.statusText.style.color = "var(--danger-color)";
            this.resultText.innerHTML = `<span style='color: var(--danger-color);'>翻译失败: ${e.message}</span>`;
        }
    }
}

window.addEventListener("DOMContentLoaded", () => {
    setTimeout(() => {
        window.RealtimeTranslationManagerInstance = new RealtimeTranslationManager();
    }, 500);
});
