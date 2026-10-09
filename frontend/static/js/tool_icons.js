/**
 * Paperfect — shared line-icon set for PDF tools.
 * Plain inline SVG (stroke=currentColor) so icons follow the current theme
 * color automatically; used by both the global toolbox (library.html) and
 * the per-paper tools menu (chat.html) so the two stay visually consistent.
 */
(function () {
    const S = 'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"';
    const svg = (inner) => `<svg viewBox="0 0 24 24" ${S} xmlns="http://www.w3.org/2000/svg">${inner}</svg>`;

    window.PAPERFECT_TOOL_ICONS = {
        images: svg('<rect x="3" y="3" width="18" height="18" rx="2.2"/><circle cx="8.5" cy="8.5" r="1.6"/><path d="M21 15.5l-5.2-5.2a1.4 1.4 0 0 0-2 0L5 19"/>'),
        figures: svg('<rect x="7" y="7" width="14" height="14" rx="2"/><path d="M17 7V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h2"/><circle cx="12.5" cy="12" r="1.3"/><path d="M21 17l-3.2-3.2a1.2 1.2 0 0 0-1.7 0L12 18"/>'),
        docx: svg('<path d="M7 2.5h7l3.5 3.5V21a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1z"/><path d="M14 2.5V6a1 1 0 0 0 1 1h3.5"/><path d="M8 13l1.4 5 1.6-3.6L12.6 18 14 13"/>'),
        md: svg('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M6.5 15V9l3 3.4L12.5 9v6"/><path d="M15.5 9v4.5M15.5 13.5l1.8-1.8M15.5 13.5l-1.8-1.8"/>'),
        tex: svg('<path d="M7 2.5h7l3.5 3.5V21a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1z"/><path d="M14 2.5V6a1 1 0 0 0 1 1h3.5"/><path d="M8 12.5h4M8 16.5c1 0 1.6-.4 1.6-1.4S8.8 13.9 8.8 13c0-.9.6-1.5 1.6-1.5M12.5 16.5h3l-1.6-2.5 1.6-2.5"/>'),
        ocr: svg('<rect x="3" y="4" width="13" height="16" rx="2"/><path d="M6.5 9h6M6.5 12h6M6.5 15h3.5"/><circle cx="17.5" cy="16.5" r="3"/><path d="M20 19l2 2"/>'),
        rotate: svg('<path d="M4 12a8 8 0 1 1 2.6 5.9"/><path d="M4 17v-5h5"/>'),
        split: svg('<circle cx="6.5" cy="6.5" r="2.3"/><circle cx="6.5" cy="17.5" r="2.3"/><path d="M8.2 8.2 19 19M19 5 8.2 15.8"/>'),
        compress: svg('<path d="M9 3v4a2 2 0 0 1-2 2H3M15 3v4a2 2 0 0 0 2 2h4M9 21v-4a2 2 0 0 0-2-2H3M15 21v-4a2 2 0 0 1 2-2h4"/>'),
        watermark: svg('<path d="M12 3c3.2 3.6 5 6.6 5 9.2A5 5 0 0 1 7 12.2C7 9.6 8.8 6.6 12 3z"/>'),
        protect: svg('<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/><circle cx="12" cy="15.2" r="1.3"/>'),
        unlock: svg('<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7a4 4 0 0 1 7.2-2.4"/><circle cx="12" cy="15.2" r="1.3"/>'),
        merge: svg('<rect x="3" y="4" width="10" height="13" rx="2"/><rect x="10" y="8" width="11" height="13" rx="2"/>'),
        upload: svg('<path d="M12 15V4M8 8l4-4 4 4"/><path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3"/>'),
        library: svg('<path d="M4 19.5V5a1 1 0 0 1 1-1h5v16"/><path d="M10 20V4h9a1 1 0 0 1 1 1v14.5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1"/>'),
        close: svg('<path d="M6 6l12 12M18 6L6 18"/>'),
        wrench: svg('<path d="M14.7 6.3a4 4 0 1 0-5.4 5.4L4 17l3 3 5.3-5.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2-2z"/>'),
        doc: svg('<path d="M7 2.5h7l3.5 3.5V21a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1z"/><path d="M14 2.5V6a1 1 0 0 0 1 1h3.5"/><path d="M8 13h6M8 16.5h6"/>'),
        highlighter: svg('<path d="M4 20.5l1-4 8.5-8.5 3 3-8.5 8.5z"/><path d="M13.5 8l2.6-2.6a1.7 1.7 0 0 1 2.4 0l.6.6a1.7 1.7 0 0 1 0 2.4L16.5 11"/><path d="M4 20.5H8"/>'),
        translate: svg('<circle cx="12" cy="12" r="9.2"/><path d="M2.8 12h18.4M12 2.8c2.4 2.6 3.7 5.9 3.7 9.2s-1.3 6.6-3.7 9.2c-2.4-2.6-3.7-5.9-3.7-9.2S9.6 5.4 12 2.8z"/>'),
        slides: svg('<rect x="2.5" y="4.5" width="19" height="12" rx="2"/><path d="M8 20.5h8M12 16.5v4"/><path d="M6.5 13l2.8-3.4 2 2 3-3.8"/>'),
        waveform: svg('<path d="M3 12h2.5l1.7-6 3 12 2-9.5 1.6 4.5H21"/>'),
        sparkle: svg('<path d="M12 3.5l1.4 4.3 4.3 1.4-4.3 1.4L12 15l-1.4-4.4-4.3-1.4 4.3-1.4z"/><path d="M18.5 15l.8 2.3 2.3.8-2.3.8-.8 2.3-.8-2.3-2.3-.8 2.3-.8z"/>'),
    };
})();
