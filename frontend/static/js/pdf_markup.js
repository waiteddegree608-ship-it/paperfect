/**
 * Enable text selection + highlight/underline/note on PDF.js viewer.
 * Posts {type:'paperfect-markup', ...} to the parent window.
 */
(function () {
    function pageFromNode(node) {
        let el = node && node.nodeType === 1 ? node : node && node.parentElement;
        while (el) {
            if (el.classList && el.classList.contains('page') && el.dataset.pageNumber) {
                return el;
            }
            el = el.parentElement;
        }
        return null;
    }

    function detectSource() {
        try {
            const id = window.frameElement && window.frameElement.id;
            if (id === 'iframe-translated') return 'translated';
            if (id === 'iframe-annotated') return 'annotated';
        } catch (e) {}
        return 'raw';
    }

    function pdfRectsFromRange(range) {
        const pageEl = pageFromNode(range.startContainer);
        if (!pageEl) return null;
        const pageNumber = parseInt(pageEl.dataset.pageNumber, 10);
        const app = window.PDFViewerApplication;
        const pv = app && app.pdfViewer && app.pdfViewer.getPageView(pageNumber - 1);
        if (!pv) return null;
        // Map CSS (top-left) onto PyMuPDF page space (also top-left). Do not use
        // convertToPdfPoint — that is PDF user space with origin at the bottom.
        const wrap = pageEl.querySelector('.canvasWrapper') || pageEl.querySelector('canvas') || pageEl;
        const box = wrap.getBoundingClientRect();
        if (box.width < 1 || box.height < 1) return null;
        const view = (pv.pdfPage && pv.pdfPage.view) || [0, 0, box.width, box.height];
        const pdfW = Math.abs(view[2] - view[0]) || box.width;
        const pdfH = Math.abs(view[3] - view[1]) || box.height;
        const rects = [];
        for (const r of range.getClientRects()) {
            if (r.width < 1 || r.height < 1) continue;
            const x0 = (r.left - box.left) / box.width * pdfW;
            const y0 = (r.top - box.top) / box.height * pdfH;
            const x1 = (r.right - box.left) / box.width * pdfW;
            const y1 = (r.bottom - box.top) / box.height * pdfH;
            rects.push({
                x0: Math.min(x0, x1),
                y0: Math.min(y0, y1),
                x1: Math.max(x0, x1),
                y1: Math.max(y0, y1),
            });
        }
        return { pageNumber, rects, text: range.toString(), source: detectSource() };
    }

    let bar = null;
    function ensureBar() {
        if (bar) return bar;
        bar = document.createElement('div');
        bar.id = 'paperfect-sel-bar';
        bar.style.cssText = 'position:fixed;z-index:100000;display:none;gap:6px;padding:6px 8px;background:#1e293b;border:1px solid #64748b;border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.35);font:12px/1.2 system-ui,sans-serif;';
        const mk = (label, kind) => {
            const b = document.createElement('button');
            b.textContent = label;
            b.dataset.kind = kind;
            b.style.cssText = 'background:#334155;color:#fff;border:0;border-radius:6px;padding:5px 8px;cursor:pointer;';
            bar.appendChild(b);
            return b;
        };
        mk('高亮', 'highlight');
        mk('下划线', 'underline');
        mk('波浪线', 'squiggly');
        mk('删除线', 'strike');
        mk('翻译', 'translate');
        const noteBtn = mk('批注', 'note');
        bar.addEventListener('mousedown', (e) => e.preventDefault());
        bar.addEventListener('click', (e) => {
            const btn = e.target.closest('button');
            if (!btn || !bar._payload) return;
            const text = (bar._payload.text || '').replace(/\s+/g, ' ').trim();
            if (btn.dataset.kind === 'translate') {
                window.parent.postMessage({ type: 'paperfect-open-realtime', text }, '*');
                bar.style.display = 'none';
                return;
            }
            let note = '';
            if (btn.dataset.kind === 'note') {
                note = window.prompt('批注内容 / Note') || '';
                if (!note) return;
            }
            window.parent.postMessage({
                type: 'paperfect-markup',
                kind: btn.dataset.kind === 'note' ? 'highlight' : btn.dataset.kind,
                note,
                page: bar._payload.pageNumber,
                text: bar._payload.text,
                rects: bar._payload.rects,
                source: bar._payload.source || detectSource(),
            }, '*');
            bar.style.display = 'none';
            const sel = window.getSelection();
            if (sel) sel.removeAllRanges();
        });
        document.body.appendChild(bar);
        return bar;
    }

    document.addEventListener('mouseup', () => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.rangeCount) {
            if (bar) bar.style.display = 'none';
            return;
        }
        const range = sel.getRangeAt(0);
        const payload = pdfRectsFromRange(range);
        if (!payload || !payload.rects.length || !(payload.text || '').trim()) {
            if (bar) bar.style.display = 'none';
            return;
        }
        try {
            window.parent.postMessage({
                type: 'paperfect-selection',
                text: String(payload.text || '').replace(/\s+/g, ' ').trim(),
            }, '*');
        } catch (e) {}
        const b = ensureBar();
        b._payload = payload;
        const r = range.getBoundingClientRect();
        b.style.display = 'flex';
        b.style.left = Math.max(8, r.left) + 'px';
        b.style.top = Math.max(8, r.top - 40) + 'px';
    });

    // Make sure text layer can be selected even if a theme sets user-select:none
    const style = document.createElement('style');
    style.textContent = `
      html { -moz-user-select: text !important; }
      .textLayer, .textLayer span { user-select: text !important; -webkit-user-select: text !important; pointer-events: auto !important; cursor: text !important; }
      /* Invisible PDF link rects sit above the text layer and block selection */
      .annotationLayer .linkAnnotation { pointer-events: none !important; }
    `;
    document.head.appendChild(style);
})();
