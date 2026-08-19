/**
 * PdfScrollSyncManager
 * 
 * 用于管理多个 PDF.js iframe 之间的滚动同步。
 * 功能包括：
 * 1. 监听多个 iframe 的滚动事件。
 * 2. 记录最后一次交互的 iframe。
 * 3. 开启同步时，自动按比例对齐其他 iframe 的滚动条。
 * 4. 保持各窗口自身的缩放级别，只同步滚动位置（按比例）。
 */

class PdfScrollSyncManager {
    constructor() {
        this.iframes = {};
        this.isSyncEnabled = true;
        this.lastActiveIframeId = null;
        this.isSyncing = false; // 防抖标志，避免循环触发
        this.initInterval = null;
    }

    /**
     * 注册参与同步的 iframe
     * @param {string} id 标识符 (如 'original', 'annotated', 'translated')
     * @param {HTMLIFrameElement} iframeElement iframe DOM 元素
     */
    registerIframe(id, iframeElement) {
        if (!iframeElement) return;
        this.iframes[id] = iframeElement;
    }

    /**
     * 开启/关闭同步功能
     * @param {boolean} enabled 
     */
    setSyncState(enabled) {
        this.isSyncEnabled = enabled;
        // 如果开启同步，并且知道上次操作的是哪个窗口，则立即以该窗口为准同步其他窗口
        if (enabled && this.lastActiveIframeId) {
            this.syncScroll(this.lastActiveIframeId);
        }
    }

    /**
     * 初始化监听器，等待 iframe 和其内部的 PDF.js 加载完毕
     */
    initListeners() {
        // 定时检查 iframe 内的 viewerContainer 是否就绪
        this.initInterval = setInterval(() => {
            let allReady = true;

            for (const [id, iframe] of Object.entries(this.iframes)) {
                if (iframe.dataset.listenerAttached) continue;

                try {
                    const innerWin = iframe.contentWindow;
                    if (innerWin && innerWin.document) {
                        const viewerContainer = innerWin.document.getElementById('viewerContainer');
                        if (viewerContainer) {
                            // 绑定滚动事件
                            viewerContainer.addEventListener('scroll', () => {
                                if (this.isSyncing) return;
                                
                                this.lastActiveIframeId = id;
                                if (this.isSyncEnabled) {
                                    this.syncScroll(id);
                                }

                                // Sync PPT slide to this PDF page
                                // page_mapping: { slideIndex: pdfPage }
                                // Multiple slides may share one PDF page (multi-figure page + 补充说明).
                                try {
                                    const pageNum = innerWin.PDFViewerApplication.page;
                                    if (pageNum && window.pptPageMapping) {
                                        const matches = Object.keys(window.pptPageMapping)
                                            .filter(key => Number(window.pptPageMapping[key]) === Number(pageNum))
                                            .map(key => parseInt(key, 10))
                                            .filter(n => !Number.isNaN(n))
                                            .sort((a, b) => a - b);
                                        if (matches.length) {
                                            const cur = (typeof window.pptCurrentSlideIndex === 'number')
                                                ? window.pptCurrentSlideIndex : -1;
                                            // Stay on current slide if it already belongs to this PDF page
                                            // (e.g. 2nd figure on same page, or 补充说明 of current figure)
                                            const slideIndex = matches.includes(cur) ? cur : matches[0];
                                            if (slideIndex !== cur) {
                                                const pptIframe = document.querySelector('#pane-ppt iframe');
                                                if (pptIframe && pptIframe.contentWindow) {
                                                    pptIframe.contentWindow.postMessage({
                                                        type: 'SELECT_SLIDE_BY_INDEX',
                                                        index: slideIndex
                                                    }, '*');
                                                }
                                                window.pptCurrentSlideIndex = slideIndex;
                                            }
                                        }
                                    }
                                } catch (err) {}
                            });

                            // 标记为已挂载
                            iframe.dataset.listenerAttached = 'true';
                            console.log(`[PdfScrollSync] Listener attached to ${id}`);
                        } else {
                            allReady = false;
                        }
                    } else {
                        allReady = false;
                    }
                } catch (e) {
                    // 跨域或未加载完成的异常
                    allReady = false;
                }
            }

            // 如果全部挂载完毕，可以清除定时器 (但因为有些页面可能是隐藏的或者按需加载，我们可以保留较长时间再清理，或一直保留以应对重载)
            // if (allReady) {
            //     clearInterval(this.initInterval);
            // }

        }, 1000);
    }

    /**
     * 执行同步逻辑，将其他 iframe 的滚动比例与源 iframe 保持一致
     * @param {string} sourceId 发起同步的源 iframe ID
     */
    syncScroll(sourceId) {
        const sourceIframe = this.iframes[sourceId];
        if (!sourceIframe) return;

        let sourceContainer;
        try {
            sourceContainer = sourceIframe.contentWindow.document.getElementById('viewerContainer');
        } catch (e) { return; }

        if (!sourceContainer) return;

        // 计算源的滚动比例 (0 到 1 之间)
        const maxScrollTop = sourceContainer.scrollHeight - sourceContainer.clientHeight;
        const scrollRatio = maxScrollTop > 0 ? sourceContainer.scrollTop / maxScrollTop : 0;
        const scrollLeftRatio = (sourceContainer.scrollWidth - sourceContainer.clientWidth) > 0 
            ? sourceContainer.scrollLeft / (sourceContainer.scrollWidth - sourceContainer.clientWidth) : 0;

        this.isSyncing = true; // 加锁，防止循环触发事件

        for (const [id, iframe] of Object.entries(this.iframes)) {
            if (id === sourceId) continue;

            // 检查 iframe 对应的 pane 是否隐藏，如果隐藏则跳过
            // 如果其父元素(.pane)存在且 style.display 为 'none'，则跳过
            if (iframe.offsetParent === null) continue;

            try {
                const targetContainer = iframe.contentWindow.document.getElementById('viewerContainer');
                if (targetContainer) {
                    const targetMaxScrollTop = targetContainer.scrollHeight - targetContainer.clientHeight;
                    const targetMaxScrollLeft = targetContainer.scrollWidth - targetContainer.clientWidth;

                    // 设置目标滚动条高度（按比例）
                    targetContainer.scrollTop = targetMaxScrollTop * scrollRatio;
                    targetContainer.scrollLeft = targetMaxScrollLeft * scrollLeftRatio;
                }
            } catch (e) {
                // 忽略异常，可能该 iframe 还未准备好
            }
        }

        // 短暂延迟后解锁
        requestAnimationFrame(() => {
            this.isSyncing = false;
        });
    }
}

// 暴露到全局，供其他脚本使用
window.PdfScrollSyncManager = PdfScrollSyncManager;
