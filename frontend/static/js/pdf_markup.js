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
        const labels = (localStorage.getItem('paperfect_lang') || 'zh') === 'en'
            ? [['Highlight', 'highlight'], ['Underline', 'underline'], ['Squiggly', 'squiggly'], ['Strike', 'strike'], ['Translate', 'translate'], ['Note', 'note']]
            : [['高亮', 'highlight'], ['下划线', 'underline'], ['波浪线', 'squiggly'], ['删除线', 'strike'], ['翻译', 'translate'], ['批注', 'note']];
        labels.forEach(([label, kind]) => mk(label, kind));
        const relabelBar = () => {
            const en = (localStorage.getItem('paperfect_lang') || 'zh') === 'en';
            const map = en
                ? { highlight: 'Highlight', underline: 'Underline', squiggly: 'Squiggly', strike: 'Strike', translate: 'Translate', note: 'Note' }
                : { highlight: '高亮', underline: '下划线', squiggly: '波浪线', strike: '删除线', translate: '翻译', note: '批注' };
            bar.querySelectorAll('button[data-kind]').forEach((b) => {
                if (map[b.dataset.kind]) b.textContent = map[b.dataset.kind];
            });
        };
        window.addEventListener('storage', (e) => { if (e.key === 'paperfect_lang') relabelBar(); });
        window.addEventListener('message', (e) => { if (e.data && e.data.type === 'paperfect-lang') relabelBar(); });
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
      html.paperfect-focus #toolbarContainer,
      html.paperfect-focus .toolbar { display: none !important; }
      html.paperfect-focus #viewerContainer { inset: 0 !important; }
      .annotationLayer .popupAnnotation,
      .annotationLayer .popup {
        visibility: hidden !important;
        pointer-events: none !important;
      }
      .annotationLayer :is(.highlightAnnotation, .underlineAnnotation, .squigglyAnnotation, .strikeoutAnnotation, .textAnnotation) {
        cursor: help;
      }
      #paperfect-note-hover {
        position: fixed;
        z-index: 100001;
        display: none;
        box-sizing: border-box;
        max-width: min(380px, calc(100vw - 24px));
        min-width: 240px;
        padding: 8px 10px 9px;
        border-radius: 7px;
        background: #fff6b8;
        color: #1f2937;
        border: 1px solid #e3c84a;
        box-shadow: 0 8px 22px rgba(0,0,0,.28);
        font: 13px/1.55 "Microsoft YaHei", "PingFang SC", system-ui, sans-serif;
        white-space: normal;
        word-break: normal;
        overflow-wrap: break-word;
        pointer-events: auto;
      }
      #paperfect-note-hover .paperfect-note-title {
        font-size: 11px;
        font-weight: 700;
        color: #7a5d00;
        margin-bottom: 3px;
      }
    `;
    document.head.appendChild(style);

    function applyPdfFocusMode(on) {
        const next = typeof on === 'boolean'
            ? on
            : (localStorage.getItem('paperfect_reader_focus') === '1');
        document.documentElement.classList.toggle('paperfect-focus', next);
    }
    applyPdfFocusMode();
    window.addEventListener('storage', (e) => {
        if (e.key === 'paperfect_reader_focus') applyPdfFocusMode(e.newValue === '1');
    });
    window.addEventListener('message', (e) => {
        const d = e.data || {};
        if (d.type === 'paperfect-focus-mode' && typeof d.on === 'boolean') {
            applyPdfFocusMode(d.on);
        }
    });

    const ANCHOR_SEL = [
        '.highlightAnnotation',
        '.underlineAnnotation',
        '.squigglyAnnotation',
        '.strikeoutAnnotation',
        '.textAnnotation',
        '.caretAnnotation',
    ].join(',');

    const annotCache = new Map();
    const annotInflight = new Map();
    let tipEl = null;
    let tipAnchor = null;
    let tipHideTimer = null;
    let hoverGen = 0;

    function noteTextFromPopup(popup) {
        if (!popup) return { title: '', body: '' };
        const title = ((popup.querySelector('h1') || {}).textContent || '').trim();
        const content = popup.querySelector('.popupContent, .richText');
        let body = '';
        if (content) {
            body = (content.textContent || '').replace(/\s+/g, ' ').trim();
        } else {
            const clone = popup.cloneNode(true);
            clone.querySelectorAll('.header, h1, .popupDate').forEach((n) => n.remove());
            body = (clone.textContent || '').replace(/\s+/g, ' ').trim();
        }
        if (title && body.indexOf(title) === 0) body = body.slice(title.length).trim();
        return { title, body };
    }

    function mapAnnot(a) {
        return {
            id: String(a.id || ''),
            contents: String((a.contentsObj && a.contentsObj.str) || a.contents || '').trim(),
            title: String((a.titleObj && a.titleObj.str) || a.title || '').trim(),
            parentId: a.parentId != null ? String(a.parentId)
                : (a.inReplyTo != null ? String(a.inReplyTo) : ''),
            subtype: String(a.subtype || ''),
        };
    }

    function ensureAnnotCache(pageNumber) {
        if (annotCache.has(pageNumber)) return Promise.resolve(annotCache.get(pageNumber));
        if (annotInflight.has(pageNumber)) return annotInflight.get(pageNumber);
        const app = window.PDFViewerApplication;
        const pv = app && app.pdfViewer && app.pdfViewer.getPageView(pageNumber - 1);
        if (!pv || !pv.pdfPage || !pv.pdfPage.getAnnotations) {
            return Promise.resolve([]);
        }
        const pending = pv.pdfPage.getAnnotations({ intent: 'display' }).then((list) => {
            const mapped = (list || []).map(mapAnnot);
            annotCache.set(pageNumber, mapped);
            annotInflight.delete(pageNumber);
            return mapped;
        }).catch(() => {
            annotInflight.delete(pageNumber);
            return [];
        });
        annotInflight.set(pageNumber, pending);
        return pending;
    }

    function resolveNote(anchor) {
        const ownPopup = anchor.querySelector(':scope > .popup, :scope .popup');
        if (ownPopup) {
            const fromDom = noteTextFromPopup(ownPopup);
            if (fromDom.body || fromDom.title) return Promise.resolve(fromDom);
        }
        const page = pageFromNode(anchor);
        const id = String(anchor.dataset.annotationId || '');
        if (!page || !id) return Promise.resolve(null);
        const pageNumber = parseInt(page.dataset.pageNumber, 10);
        return ensureAnnotCache(pageNumber).then((list) => {
            const self = list.find((x) => x.id === id && x.subtype !== 'Popup');
            if (self && self.contents) return { title: self.title, body: self.contents };
            const popup = list.find((x) => x.subtype === 'Popup' && x.parentId === id && x.contents);
            if (popup) return { title: popup.title || (self && self.title) || '', body: popup.contents };
            if (self && self.title) return { title: self.title, body: '' };
            return null;
        });
    }

    function stripCategoryPrefix(text, label) {
        let s = String(text || '').trim();
        s = s.replace(/^(【[^】]+】\s*)+/g, '');
        s = s.replace(/^(\[[^\]]+\]\s*)+/g, '');
        const names = [
            label, '核心创新点', '重要方法', '缺陷与挑战', '深度总结', '中文注解',
            '核心创新点、重大贡献', '重要方法、网络模块、数据集与指标',
            '现有缺陷、挑战、问题', '全局总结或深度剖析',
            'Core contribution', 'Key method', 'Limitation', 'Summary',
        ].filter(Boolean);
        names.forEach((name) => {
            const esc = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
            s = s.replace(new RegExp('^' + esc + '\\s*[:：\\-—–]?\\s*', 'i'), '');
        });
        return s.trim();
    }

    function themeForAnchor(anchor) {
        const en = (localStorage.getItem('paperfect_lang') || 'zh') === 'en';
        if (anchor.classList.contains('underlineAnnotation')) {
            return { bg: '#dbeafe', border: '#3b82f6', title: '#1e3a8a', label: en ? 'Key method' : '重要方法' };
        }
        if (anchor.classList.contains('squigglyAnnotation')) {
            return { bg: '#fee2e2', border: '#ef4444', title: '#991b1b', label: en ? 'Limitation' : '缺陷与挑战' };
        }
        if (anchor.classList.contains('textAnnotation')) {
            return { bg: '#dcfce7', border: '#16a34a', title: '#166534', label: en ? 'Summary' : '深度总结' };
        }
        return { bg: '#fff6b8', border: '#e3c84a', title: '#7a5d00', label: en ? 'Core contribution' : '核心创新点' };
    }

    function ensureTip() {
        if (tipEl) return tipEl;
        tipEl = document.createElement('div');
        tipEl.id = 'paperfect-note-hover';
        tipEl.innerHTML = '<div class="paperfect-note-title"></div><div class="paperfect-note-body"></div>';
        tipEl.addEventListener('mouseenter', () => clearTimeout(tipHideTimer));
        tipEl.addEventListener('mouseleave', hideTipSoon);
        document.body.appendChild(tipEl);
        return tipEl;
    }

    function hideTip() {
        clearTimeout(tipHideTimer);
        if (tipEl) tipEl.style.display = 'none';
        tipAnchor = null;
        document.documentElement.classList.remove('paperfect-note-open');
    }

    function hideTipSoon() {
        clearTimeout(tipHideTimer);
        tipHideTimer = setTimeout(hideTip, 180);
    }

    function placeTip(anchor) {
        const tip = ensureTip();
        const r = anchor.getBoundingClientRect();
        const w = Math.min(Math.max(r.width, 260), Math.min(380, window.innerWidth - 24));
        let left = r.left;
        if (left + w > window.innerWidth - 12) left = window.innerWidth - w - 12;
        if (left < 8) left = 8;
        tip.style.display = 'block';
        tip.style.width = w + 'px';
        tip.style.left = left + 'px';
        tip.style.top = (r.bottom + 8) + 'px';
        const th = tip.offsetHeight || 48;
        if (r.bottom + 8 + th > window.innerHeight - 8 && r.top - th - 8 > 8) {
            tip.style.top = (r.top - th - 8) + 'px';
        }
        document.documentElement.classList.add('paperfect-note-open');
    }

    function showTip(anchor, title, body) {
        clearTimeout(tipHideTimer);
        const tip = ensureTip();
        const theme = themeForAnchor(anchor);
        tip.style.background = theme.bg;
        tip.style.borderColor = theme.border;
        const titleEl = tip.querySelector('.paperfect-note-title');
        const bodyEl = tip.querySelector('.paperfect-note-body');
        titleEl.textContent = theme.label;
        titleEl.style.display = 'block';
        titleEl.style.color = theme.title;
        const generic = /^(AI\s*助教|AI Assistant|Summary|深度总结)$/i;
        let text = stripCategoryPrefix(body, theme.label);
        if (generic.test(text)) text = '';
        bodyEl.textContent = text;
        tipAnchor = anchor;
        placeTip(anchor);
    }

    function bindHover() {
        document.addEventListener('mouseover', (e) => {
            const anchor = e.target && e.target.closest && e.target.closest(ANCHOR_SEL);
            if (!anchor) return;
            if (anchor === tipAnchor) {
                clearTimeout(tipHideTimer);
                return;
            }
            const gen = ++hoverGen;
            resolveNote(anchor).then((note) => {
                if (gen !== hoverGen) return;
                if (!note || !(note.body || note.title)) return;
                showTip(anchor, note.title, note.body);
            });
        });
        document.addEventListener('mouseout', (e) => {
            const anchor = e.target && e.target.closest && e.target.closest(ANCHOR_SEL);
            if (!anchor) return;
            const to = e.relatedTarget;
            if (anchor.contains && anchor.contains(to)) return;
            if (tipEl && to && tipEl.contains(to)) return;
            hideTipSoon();
        });
        document.addEventListener('scroll', () => {
            if (tipEl && tipEl.style.display === 'block') hideTip();
        }, true);
    }

    bindHover();
})();
