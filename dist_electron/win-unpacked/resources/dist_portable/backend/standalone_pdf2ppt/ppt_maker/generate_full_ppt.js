import fs from 'fs';
import path from 'path';
import { execFileSync } from 'child_process';
import { fileURLToPath } from 'url';
import { OpenAI } from 'openai';
import pptxgen from 'pptxgenjs';
import sizeOf from 'image-size';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Paperfect PPT generator — human-style callout layout
 *
 * OLD (bad for talks / CHI figures):
 *   title → centered figure → bottom summary → bottom text columns + long crossing arrows
 *
 * NEW (human presenter style):
 *   title + one-line takeaway
 *   large figure in the center
 *   numbered badges on figure modules
 *   short labels/explanations in LEFT/RIGHT side cards next to modules
 *   short edge connectors only (no bottom strip, no long crossing arrows)
 */

const args = process.argv.slice(2);
if (args.length < 5) {
    console.error("Usage: node generate_full_ppt.js <mdPath> <imgDir> <outputPath> <mode: simple|creative> <apiKey> [modelName] [baseURL] [lang] [--force-refresh]");
    process.exit(1);
}

const mdPath = path.resolve(args[0]);
const imgDir = path.resolve(args[1]);
const outputPath = path.resolve(args[2]);
const MODE = args[3] || 'simple';
const apiKey = args[4];
const modelName = args[5] || 'Qwen/Qwen2.5-72B-Instruct';
const customBaseURL = args[6] || 'https://api.siliconflow.cn/v1';
const pptLang = args[7] || 'zh';
const forceRefresh = args.includes('--force-refresh') || process.env.PPT_FORCE_REFRESH === '1';
// Follow-up "补充说明" slides double deck length and break group-meeting flow
// (e.g. 24 figures → 48 slides). Default OFF; pass --followups or FOLLOWUP_SLIDES=1.
const allowFollowups =
    args.includes('--followups') ||
    process.env.FOLLOWUP_SLIDES === '1' ||
    process.env.FOLLOWUP_SLIDES === 'true';
// Optional cap on figure slides for huge papers (0 = no cap)
const maxFigures = (() => {
    const a = args.find(x => x.startsWith('--max-figures='));
    if (a) return Math.max(0, parseInt(a.split('=')[1], 10) || 0);
    const e = parseInt(process.env.PPT_MAX_FIGURES || '0', 10);
    return Number.isFinite(e) ? Math.max(0, e) : 0;
})();
const isEn = pptLang === 'en';

const client = new OpenAI({
    apiKey: apiKey,
    baseURL: customBaseURL
});

const is_deepseek = modelName.toLowerCase().includes("deepseek") || customBaseURL.toLowerCase().includes("deepseek");

const SLIDE_W = 1280;
const SLIDE_H = 720;
const PX = 128; // px per inch for pptxgen LAYOUT_16x9
const CALLOUT_COLORS = ['1E40AF', 'B45309', '047857', '9D174D', '6D28D9', '0E7490', 'C2410C', '334155'];

function cleanText(str) {
    if (!str) return '';
    return String(str)
        .replace(/Ê/g, "E'")
        .replace(/\\hat\{(.+?)\}/g, "$1'")
        .replace(/\$/g, '')
        .replace(/\\cos/g, 'cos')
        .replace(/\s+/g, ' ')
        .trim();
}

function hasCJK(s) {
    return /[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/.test(s || '');
}

/**
 * Layout coordinate system (must match slide builders above):
 *   SLIDE_W=1280, PX=128  =>  128 layout-units = 1 inch
 * pptxgen `fontSize` is in **points** (1pt = 1/72 inch).
 *
 * Previous bug: treated fontSize as if it were layout pixels, so measured
 * widths were ~1.8× too small and text always overflowed real PPT boxes.
 */
const LAYOUT_PER_PT = 128 / 72; // ≈1.778 layout units per point

/**
 * Character width in **layout units** (same as sideW / imgW).
 * Em fractions are Arial-ish; safety factor over-estimates slightly.
 */
function charWidthLayout(ch, fontSizePt, bold) {
    let em;
    if (/[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/.test(ch)) {
        em = 1.05;
    } else if (ch === ' ') {
        em = 0.33;
    } else if (/[iIl1.,;:'!|`j]/.test(ch)) {
        em = 0.34;
    } else if (/[mwMW@%#&GODQU]/.test(ch)) {
        em = 0.85;
    } else if (/[A-Z]/.test(ch)) {
        em = 0.68;
    } else {
        // Real Arial-ish ~0.5em; keep mild safety (clip handles residual risk)
        em = 0.54;
    }
    if (bold) em *= 1.10;
    return fontSizePt * LAYOUT_PER_PT * em * 1.04;
}

function measureLineWidth(line, fontSizePt, bold) {
    let w = 0;
    for (const ch of line) w += charWidthLayout(ch, fontSizePt, bold);
    return w;
}

/** Hard-break a single overlong token into chunks that fit maxWidth. */
function hardBreakToken(token, maxWidth, fontSize, bold) {
    const out = [];
    let cur = '';
    for (const ch of token) {
        const trial = cur + ch;
        if (measureLineWidth(trial, fontSize, bold) <= maxWidth) cur = trial;
        else {
            if (cur) out.push(cur);
            cur = ch;
        }
    }
    if (cur) out.push(cur);
    return out.length ? out : [token];
}

/**
 * Word-wrap (EN) / char-wrap (CJK) into lines that each fit maxWidthPx.
 */
function wrapToLines(text, maxWidthPx, fontSize, bold) {
    const raw = cleanText(text);
    if (!raw) return [];
    const cjkHeavy = hasCJK(raw) && (raw.match(/[\u4e00-\u9fff]/g) || []).length > raw.length * 0.3;
    const lines = [];
    if (cjkHeavy) {
        let cur = '';
        for (const ch of raw) {
            const trial = cur + ch;
            if (measureLineWidth(trial, fontSize, bold) <= maxWidthPx) cur = trial;
            else {
                if (cur) lines.push(cur);
                cur = ch;
            }
        }
        if (cur) lines.push(cur);
        return lines;
    }
    // English / mixed: wrap on spaces
    const tokens = raw.split(/\s+/).filter(Boolean);
    let cur = '';
    for (const tok of tokens) {
        const trial = cur ? `${cur} ${tok}` : tok;
        if (measureLineWidth(trial, fontSize, bold) <= maxWidthPx) {
            cur = trial;
            continue;
        }
        if (cur) lines.push(cur);
        if (measureLineWidth(tok, fontSize, bold) <= maxWidthPx) {
            cur = tok;
        } else {
            const parts = hardBreakToken(tok, maxWidthPx, fontSize, bold);
            lines.push(...parts.slice(0, -1));
            cur = parts[parts.length - 1] || '';
        }
    }
    if (cur) lines.push(cur);
    return lines;
}

/**
 * Fit text into a layout-unit box by:
 *  1) shrinking font size (points)
 *  2) explicit wrap into \n lines using pt→layout width math
 *  3) dropping overflow lines with an ellipsis
 *
 * width/height arguments are in the same layout units as sideW (128 units = 1").
 */
function fitTextToBox(text, widthLayout, heightLayout, fontSizePt, opts = {}) {
    const raw = cleanText(text);
    if (!raw) return { text: '', fontSize: fontSizePt };
    const bold = !!opts.bold;
    const minFs = opts.minFontSize != null ? opts.minFontSize : Math.max(7, fontSizePt - 5);
    const lineHeight = opts.lineHeight || 1.30;
    // Leave padding inside the shape so glyphs never kiss the border
    // keep a small safety margin; in-shape + OOXML clip handle hard overflow
    const usableW = Math.max(16, widthLayout * 0.92);
    const usableH = Math.max(10, heightLayout * 0.92);

    let best = null;
    for (let fs = fontSizePt; fs >= minFs - 1e-6; fs -= 0.5) {
        // line height in layout units: pt → inch → layout
        const lineH = fs * LAYOUT_PER_PT * lineHeight;
        const maxLines = Math.max(1, Math.floor(usableH / lineH));
        let lines = wrapToLines(raw, usableW, fs, bold);
        let truncated = false;
        if (lines.length > maxLines) {
            truncated = true;
            lines = lines.slice(0, maxLines);
            let last = lines[lines.length - 1];
            while (last.length > 0 && measureLineWidth(last + '…', fs, bold) > usableW) {
                last = last.slice(0, -1).replace(/\s+$/u, '');
            }
            if (!hasCJK(last)) {
                const sp = last.lastIndexOf(' ');
                if (sp > last.length * 0.4) last = last.slice(0, sp);
            }
            if (opts.ellipsis !== false) {
                lines[lines.length - 1] = (last || '…') + (String(last).endsWith('…') ? '' : '…');
                if (lines[lines.length - 1] === '……') lines[lines.length - 1] = '…';
            } else {
                // Prefer ending on a complete sentence when we must hard-cut (no ugly "…")
                let joined = lines.join(' ').replace(/\s+/g, ' ').trim();
                const sentenceEnd = Math.max(joined.lastIndexOf('. '), joined.lastIndexOf('! '), joined.lastIndexOf('? '));
                if (sentenceEnd > joined.length * 0.45) {
                    joined = joined.slice(0, sentenceEnd + 1);
                    // re-wrap the sentence-trimmed text at this font size
                    lines = wrapToLines(joined, usableW, fs, bold).slice(0, maxLines);
                } else {
                    lines[lines.length - 1] = last || lines[lines.length - 1];
                }
            }
        }
        const fitted = lines.join('\n');
        if (!truncated) return { text: fitted, fontSize: fs };
        best = { text: fitted, fontSize: fs };
    }
    return best || { text: raw.slice(0, 12), fontSize: minFs };
}

function extractLabel(mod) {
    let lab = '';
    if (mod.label && String(mod.label).trim()) lab = cleanText(mod.label);
    else {
        const d = cleanText(mod.description || '');
        const m = d.match(/^(.{2,60}?)[:：\-—]/);
        lab = m ? m[1].trim() : d;
    }
    // Do NOT pre-truncate with "…" here — that caused "Output…" titles.
    // fitTextToBox shrinks font / wraps first; ellipsis only as last resort.
    const max = isEn ? 56 : 24;
    if (lab.length > max) lab = lab.slice(0, max);
    return lab;
}

function extractBody(mod) {
    const d = cleanText(mod.description || '');
    // Prefer full description for teaching value (not a 6-word stub)
    let body = d;
    if (mod.label) {
        const lab = cleanText(mod.label);
        // if description starts with "Label: rest", keep rest; else keep full d
        const m = d.match(/^.{2,48}?[:：\-—]\s*(.+)$/);
        if (m && d.toLowerCase().startsWith(lab.toLowerCase().slice(0, Math.min(8, lab.length)))) {
            body = m[1];
        }
    }
    // Pass nearly full LLM copy; layout fit decides final visible length
    const max = isEn ? 360 : 180;
    if (body.length > max) body = body.slice(0, max - 1) + '…';
    return body;
}

/** Presentation typeface — Calibri reads cleaner than Arial on Windows PPT */
const FONT = 'Calibri';

function fitImage(nativeW, nativeH, maxW, maxH) {
    let w = nativeW;
    let h = nativeH;
    if (w <= 0 || h <= 0) return { w: maxW, h: maxH };
    const s = Math.min(maxW / w, maxH / h);
    w = w * s;
    h = h * s;
    return { w, h };
}

/**
 * Pack callout cards into a vertical rail with EVEN spacing.
 *
 * Old approach followed each module's figure targetY (desiredY). When modules
 * 2 and 3 were far apart on the figure, a large empty gap appeared between
 * cards and card 4 was pushed past the slide bottom.
 *
 * New approach: sort by figure Y (reading order), then stack with equal
 * heights and equal gaps so everything stays inside [minY, maxY].
 */
function packRailStack(items, minY, maxY, gap) {
    const sorted = [...items].sort((a, b) => {
        const dy = (a.tY ?? 0) - (b.tY ?? 0);
        return Math.abs(dy) > 1e-6 ? dy : (a.idx - b.idx);
    });
    const n = sorted.length;
    if (n === 0) return sorted;

    const band = Math.max(0, maxY - minY);
    const gapTotal = gap * Math.max(0, n - 1);
    // Equal card height that fills the rail without overflow
    let cardH = (band - gapTotal) / n;
    // Keep a readable minimum; if impossible, shrink gap first
    let useGap = gap;
    if (cardH < 100 && n > 1) {
        useGap = Math.max(4, gap - 4);
        cardH = (band - useGap * (n - 1)) / n;
    }
    cardH = Math.max(88, Math.min(cardH, 300));

    // If still overflowing due to min height, scale to fit hard
    let total = cardH * n + useGap * (n - 1);
    if (total > band && band > 0) {
        cardH = (band - useGap * (n - 1)) / n;
        cardH = Math.max(72, cardH);
        total = cardH * n + useGap * (n - 1);
    }

    // Center the stack vertically if it undershoots the band (rare)
    let y = minY;
    if (total < band - 1) {
        y = minY + (band - total) / 2;
    }

    for (const it of sorted) {
        it.cardH = cardH;
        it.y = y;
        y += cardH + useGap;
    }

    // Final clamp: never let last card cross maxY
    const last = sorted[sorted.length - 1];
    if (last.y + last.cardH > maxY) {
        const shift = last.y + last.cardH - maxY;
        for (const it of sorted) it.y -= shift;
    }
    if (sorted[0].y < minY) {
        const shift = minY - sorted[0].y;
        for (const it of sorted) it.y += shift;
    }
    return sorted;
}

/**
 * Build one figure slide with side callouts (human presenter layout).
 * Text is always fitted to its box (no overflow).
 */
function addCalloutFigureSlide(pres, slideData) {
    const slide = pres.addSlide();
    slide.background = { color: 'FFFFFF' };

    const titleRaw = cleanText(slideData.slide_title || 'Figure');
    const overallRaw = cleanText(slideData.overall_explanation || '');

    // Title — larger, cleaner type
    const titleFit = fitTextToBox(titleRaw, SLIDE_W - 64, 40, 22, {
        bold: true, minFontSize: 14, lineHeight: 1.15
    });
    slide.addText(titleFit.text, {
        x: 32 / PX, y: 8 / PX, w: (SLIDE_W - 64) / PX, h: 40 / PX,
        fontSize: titleFit.fontSize, bold: true, color: '0F172A', align: 'center',
        fontFace: FONT, valign: 'middle', margin: 0, wrap: true
    });

    // Takeaway — allow a fuller 2-line teaching sentence
    let hasTakeaway = false;
    if (overallRaw) {
        hasTakeaway = true;
        const takeFit = fitTextToBox(overallRaw, SLIDE_W - 100, 48, 13, {
            bold: false, minFontSize: 10, lineHeight: 1.25
        });
        slide.addText(takeFit.text, {
            x: 50 / PX, y: 48 / PX, w: (SLIDE_W - 100) / PX, h: 48 / PX,
            fontSize: takeFit.fontSize, color: '334155', align: 'center',
            fontFace: FONT, valign: 'top', margin: 0, wrap: true
        });
    }

    const contentTop = hasTakeaway ? 100 : 56;
    // leave a bottom safety margin so card 4 never kisses/clip the slide edge
    const contentBottom = 695;
    /**
     * Right-rail layout (better for teaching text):
     *   [  large figure  ~58%  ][  wide callout cards ~38%  ]
     * Narrow dual-side rails forced 12–15 chars/line → telegraphic stubs.
     * A single wide rail allows ~30–36 chars/line and full sentences.
     */
    const railPad = 14;
    const railW = 430; // wide legend column
    const imgRegionX = railPad;
    const imgRegionW = SLIDE_W - railW - railPad * 3;
    const imgRegionY = contentTop;
    const imgRegionH = contentBottom - contentTop;
    const railX = SLIDE_W - railPad - railW;

    const nativeW = slideData.nativeW || slideData.imgW || 800;
    const nativeH = slideData.nativeH || slideData.imgH || 500;
    const fitted = fitImage(nativeW, nativeH, imgRegionW, imgRegionH);
    const imgW = fitted.w;
    const imgH = fitted.h;
    const imgX = imgRegionX + (imgRegionW - imgW) / 2;
    const imgY = imgRegionY + (imgRegionH - imgH) / 2;

    if (slideData.base64Data) {
        slide.addImage({
            data: slideData.base64Data,
            x: imgX / PX, y: imgY / PX, w: imgW / PX, h: imgH / PX
        });
    }

    slide.addShape(pres.ShapeType.roundRect, {
        x: (imgX - 2) / PX, y: (imgY - 2) / PX, w: (imgW + 4) / PX, h: (imgH + 4) / PX,
        fill: { type: 'none' }, line: { color: 'E2E8F0', width: 1.25 }, rectRadius: 0.05
    });

    // Keep up to 4 model-proposed modules (was hard-capped at 3 purely for layout).
    // Card height scales with count so 4 points still fit the vertical band.
    const MAX_CALLOUTS = 4;
    const annotations = Array.isArray(slideData.annotations)
        ? slideData.annotations.slice(0, MAX_CALLOUTS)
        : [];
    if (annotations.length === 0) return;

    const mods = annotations.map((mod, i) => {
        let tX = mod.targetX !== undefined ? parseFloat(mod.targetX) : (i + 0.5) / Math.max(annotations.length, 1);
        let tY = mod.targetY !== undefined ? parseFloat(mod.targetY) : 0.45;
        if (Number.isNaN(tX)) tX = 0.5;
        if (Number.isNaN(tY)) tY = 0.5;
        tX = Math.min(0.98, Math.max(0.02, tX));
        tY = Math.min(0.98, Math.max(0.02, tY));
        return {
            idx: i, tX, tY, side: 'right', color: CALLOUT_COLORS[i % CALLOUT_COLORS.length],
            label0: extractLabel(mod),
            body0: extractBody(mod),
            cardH: 160 // overwritten by packRailStack for even fit
        };
    });

    // Even vertical stack (NOT figure-Y glued) — fixes gaps between #2/#3 and #4 overflow
    const gap = annotations.length >= 4 ? 8 : 10;
    const minY = contentTop;
    const maxY = contentBottom;
    const rightPacked = packRailStack(mods.map(m => ({ ...m })), minY, maxY, gap);

    const drawCard = (item) => {
        const x = railX;
        const y = item.y;
        const cardH = item.cardH;
        const color = item.color;
        const sideW = railW;

        /**
         * CRITICAL FIX for "text outside decorative box":
         * Previously we drew an empty roundRect card, then SEPARATE text shapes
         * with wrap:false. PowerPoint still paints glyphs outside the text-frame
         * when a line is even slightly wider than the frame — so text spilled past
         * the card border.
         *
         * Now: ONE rounded-rect shape that IS the text container (shape + text
         * share the same bounds). Text is pre-wrapped to fit the inner content
         * area; OOXML clip is applied in post-process.
         */
        // pptxgen margin is in POINTS
        const marginPt = 8;
        const marginLayout = marginPt * LAYOUT_PER_PT;
        const contentW = Math.max(40, sideW - marginLayout * 2);
        const contentH = Math.max(40, cardH - marginLayout * 2);
        // Compact 2-line header → maximize body for full explanations (no "…")
        const headerH = Math.max(42, Math.min(52, Math.floor(contentH * 0.28)));
        const bodyH = Math.max(40, contentH - headerH - 2);

        const headerRaw = `${item.idx + 1}. ${item.label0}`;
        const headerFit = fitTextToBox(headerRaw, contentW, headerH, 12.5, {
            bold: true, minFontSize: 10, lineHeight: 1.10, ellipsis: false
        });
        const bodyFit = fitTextToBox(item.body0, contentW, bodyH, 11, {
            bold: false, minFontSize: 8.5, lineHeight: 1.15, ellipsis: false
        });

        // Single shape = decorative frame + text (keeps glyphs inside the card)
        slide.addText(
            [
                {
                    text: headerFit.text,
                    options: {
                        bold: true,
                        fontSize: headerFit.fontSize,
                        color: '0F172A',
                        fontFace: FONT,
                        breakLine: true
                    }
                },
                {
                    text: bodyFit.text,
                    options: {
                        bold: false,
                        fontSize: bodyFit.fontSize,
                        color: '1E293B',
                        fontFace: FONT,
                        breakLine: false
                    }
                }
            ],
            {
                x: x / PX,
                y: y / PX,
                w: sideW / PX,
                h: cardH / PX,
                shape: pres.ShapeType.roundRect,
                fill: { color: 'F8FAFC' },
                line: { color, width: 1.75 },
                rectRadius: 0.1,
                shadow: { type: 'outer', color: '000000', blur: 3, opacity: 0.08, offset: 1 },
                wrap: true,
                valign: 'top',
                align: 'left',
                margin: [marginPt, marginPt, marginPt, marginPt],
                fontFace: FONT
            }
        );

        // Short connector from rail card to figure + on-figure badge
        const cardMidY = y + cardH / 2;
        const targetAbsX = imgX + item.tX * imgW;
        const targetAbsY = imgY + item.tY * imgH;
        const edgeX = imgX + imgW; // right edge of figure
        const cardLeft = x;
        const gapW = cardLeft - edgeX;
        if (gapW > 6) {
            // horizontal: figure edge → card
            slide.addShape(pres.ShapeType.line, {
                x: edgeX / PX,
                y: cardMidY / PX,
                w: gapW / PX,
                h: 0.01,
                line: { color, width: 1.35, dashType: 'solid' }
            });
            const stubDx = targetAbsX - edgeX;
            const stubDy = targetAbsY - cardMidY;
            if (Math.hypot(stubDx, stubDy) < Math.max(imgW, imgH) * 0.65) {
                slide.addShape(pres.ShapeType.line, {
                    x: (stubDx < 0 ? edgeX + stubDx : edgeX) / PX,
                    y: (stubDy < 0 ? cardMidY + stubDy : cardMidY) / PX,
                    w: Math.max(Math.abs(stubDx), 1) / PX,
                    h: Math.max(Math.abs(stubDy), 1) / PX,
                    flipH: stubDx < 0, flipV: stubDy < 0,
                    line: { color, width: 1.15, dashType: 'lgDash' }
                });
            }
        }
        const onFig = 20;
        slide.addShape(pres.ShapeType.ellipse, {
            x: (targetAbsX - onFig / 2) / PX, y: (targetAbsY - onFig / 2) / PX,
            w: onFig / PX, h: onFig / PX,
            fill: { color }, line: { color: 'FFFFFF', width: 1.5 }
        });
        slide.addText(String(item.idx + 1), {
            x: (targetAbsX - onFig / 2) / PX, y: (targetAbsY - onFig / 2) / PX,
            w: onFig / PX, h: onFig / PX,
            fontSize: 11, bold: true, color: 'FFFFFF', align: 'center', valign: 'middle',
            fontFace: FONT, margin: 0
        });
    };

    rightPacked.forEach(it => drawCard(it));
}

function addFollowUpSlide(pres, fu) {
    const slide = pres.addSlide();
    slide.background = { color: 'FFFFFF' };
    slide.addText(cleanText(fu.slide_title || (isEn ? 'Details' : '补充说明')), {
        x: 40 / PX, y: 30 / PX, w: (SLIDE_W - 80) / PX, h: 50 / PX,
        fontSize: 26, bold: true, color: '0F172A', fontFace: 'Arial'
    });
    const bullets = Array.isArray(fu.bullet_points) ? fu.bullet_points : [];
    const text = bullets.map(b => `• ${cleanText(b)}`).join('\n');
    slide.addText(text || '—', {
        x: 60 / PX, y: 100 / PX, w: (SLIDE_W - 120) / PX, h: 560 / PX,
        fontSize: 16, color: '1E293B', fontFace: 'Arial', valign: 'top'
    });
}

async function processImage(imageName, mdContent) {
    console.log(`\n[Agent] -> Processing ${imageName}...`);
    const imgPath = path.join(imgDir, imageName);
    const imgBuffer = fs.readFileSync(imgPath);
    const base64Data = 'data:image/png;base64,' + imgBuffer.toString('base64');

    const dimensions = sizeOf(imgBuffer);
    const nativeW = dimensions.width;
    const nativeH = dimensions.height;
    console.log(`   * Native dimensions: ${nativeW}x${nativeH}`);

    const prompt = isEn ? `
You are an expert academic presentation designer. Explain ONE figure for a group-meeting slide.

Context (analysis report):
<<<
${mdContent}
>>>

Coordinate system on the image: X=0 left … 1 right; Y=0 top … 1 bottom.

Return ONLY JSON in a \`\`\`json block:
{
  "slide_title": "clear English title for a group meeting slide (<= 12 words)",
  "overall_explanation": "One teaching takeaway for the whole figure (1–2 sentences, about 25–45 words)",
  "annotations": [
    {
      "label": "2-5 word module name",
      "targetX": 0.22,
      "targetY": 0.40,
      "description": "Help a grad student understand this module: what it is, what happens here, and why it matters (2–3 sentences, about 35–55 words). Be specific to the figure, not generic."
    }
  ],
  "follow_up_slides": []
}

Rules:
- Output language: ENGLISH only.
- Identify 3–4 logical modules / sub-figures / pipeline stages (prefer architecture blocks). Prefer 4 when the figure clearly has 4+ parts; otherwise 3. Quality over quantity.
- targetX/targetY = **center of that module inside THIS cropped image** (0–1 relative to the image file you see, NOT the full PDF page).
- For multi-panel figures (a)(b)(c)(d) or left/right halves: put each target on the **panel center**, not on surrounding whitespace or body text.
- If the image is tall/narrow (single-column crop), still use 0–1 coords within the visible image; do not assume full-page layout.
- Labels stay short; descriptions should be pedagogically useful (not telegraphic stubs).
- Do NOT invent content not supported by the figure or report.
- follow_up_slides: always [] (do not emit extra text-only slides; keep one slide per figure).
` : `
你是学术组会 PPT 设计师。请为论文中的【一张图】设计讲解卡片。

分析报告上下文：
<<<
${mdContent}
>>>

图像坐标系：X=0 左 … 1 右；Y=0 上 … 1 下。

只输出 \`\`\`json 代码块：
{
  "slide_title": "中文短标题（<=16字）",
  "overall_explanation": "整张图的一句 takeaway（<=40字）",
  "annotations": [
    {
      "label": "2-6字模块名",
      "targetX": 0.22,
      "targetY": 0.40,
      "description": "该模块/子图在讲什么、为何重要（<=36字）"
    }
  ],
  "follow_up_slides": []
}

规则：
- 输出语言：中文。
- 识别 3–4 个逻辑模块（质量优先）；description 写 2–3 句、约 40–70 字，帮助理解“是什么/做什么/为何重要”。
- targetX/targetY = **本裁剪图内**模块中心（相对本图 0–1，不是整页 PDF）。
- 多子图 (a)(b)(c)(d) 或左右半栏：每个 target 落在对应**子图中心**，不要点在空白或正文上。
- 半栏/窄图同样用 0–1 坐标，不要按整页版式假设。
- label 可短；description 不要电报体空壳。
- 不要编造图中/报告中没有的内容。
- follow_up_slides：必须 []（不要额外补充说明页；一图一页即可）。
`;

    const maxRetries = 2;
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            let messages;
            if (is_deepseek) {
                messages = [{
                    role: 'user',
                    content: (isEn
                        ? `Figure file name: ${imageName}. Text-only model: infer modules from the report and assign approximate targetX/targetY.\n\n`
                        : `图片文件名：${imageName}。纯文本模型：请根据报告推断模块并给出近似 targetX/targetY。\n\n`) + prompt
                }];
            } else {
                messages = [{
                    role: 'user',
                    content: [
                        { type: 'image_url', image_url: { url: base64Data } },
                        { type: 'text', text: prompt }
                    ]
                }];
            }

            const response = await client.chat.completions.create({
                model: modelName,
                messages,
                temperature: 0.2
            });

            const result = response.choices[0].message.content;
            let parsed = null;
            const jsonMatch = result.match(/```json\s*([\s\S]*?)\s*```/);
            const rawBlob = jsonMatch ? jsonMatch[1] : (result.match(/\{\s*"slide_title"[\s\S]*\}/) || [])[0];
            if (!rawBlob) throw new Error('Unable to parse JSON');
            parsed = safeParseModelJson(rawBlob);

            console.log(`   * Success! annotations=${(parsed.annotations || []).length}`);
            return {
                imageName,
                base64Data,
                nativeW,
                nativeH,
                // legacy fields kept for cache compatibility
                imgW: nativeW,
                imgH: nativeH,
                imgX: 0,
                imgY: 0,
                ...parsed
            };
        } catch (e) {
            const errStr = String(e.message || e);
            const isRateLimit = errStr.includes('429') || errStr.includes('limit') || errStr.includes('quota');
            const sleepTime = isRateLimit ? 35000 : 8000;
            console.error(`   ! Error ${imageName} (Attempt ${attempt}/${maxRetries}):`, errStr);
            if (attempt === maxRetries) {
                console.error(`   ! Max retries reached for ${imageName} — using fallback slide (continue).`);
                return {
                    imageName,
                    base64Data,
                    nativeW,
                    nativeH,
                    imgW: nativeW,
                    imgH: nativeH,
                    imgX: 0,
                    imgY: 0,
                    slide_title: isEn ? cleanText(imageName) : cleanText(imageName),
                    overall_explanation: isEn
                        ? 'See the figure; auto labels failed for this panel.'
                        : '见图；该图自动标注失败，仅展示原图。',
                    annotations: [
                        {
                            label: isEn ? 'Overview' : '总览',
                            targetX: 0.5,
                            targetY: 0.5,
                            description: isEn
                                ? 'Full figure overview (fallback).'
                                : '整图总览（自动标注失败时的兜底）。'
                        }
                    ],
                    follow_up_slides: []
                };
            }
            await new Promise(r => setTimeout(r, sleepTime));
        }
    }
}

/** Tolerate common LLM JSON issues (bad backslashes, trailing commas). */
function safeParseModelJson(raw) {
    let s = String(raw || '').trim();
    // strip BOM / fences leftovers
    s = s.replace(/^\uFEFF/, '');
    const attempts = [
        s,
        // invalid escapes like \中 or \a → keep char
        s.replace(/\\(?!["\\/bfnrtu])/g, ''),
        s.replace(/,(\s*[}\]])/g, '$1'),
        s.replace(/\\(?!["\\/bfnrtu])/g, '').replace(/,(\s*[}\]])/g, '$1'),
    ];
    let lastErr;
    for (const cand of attempts) {
        try {
            return JSON.parse(cand);
        } catch (e) {
            lastErr = e;
        }
    }
    throw lastErr || new Error('JSON parse failed');
}

function hydrateFromCache(cached, file) {
    // Prefer fresh pixels from disk (cache base64 may be huge but ok); re-measure native size
    const imgPath = path.join(imgDir, file);
    let base64Data = cached.base64Data;
    let nativeW = cached.nativeW || cached.imgW;
    let nativeH = cached.nativeH || cached.imgH;
    try {
        if (fs.existsSync(imgPath)) {
            const buf = fs.readFileSync(imgPath);
            const dim = sizeOf(buf);
            nativeW = dim.width;
            nativeH = dim.height;
            base64Data = 'data:image/png;base64,' + buf.toString('base64');
        } else if (base64Data && base64Data.includes(',')) {
            const buf = Buffer.from(base64Data.split(',')[1], 'base64');
            const dim = sizeOf(buf);
            nativeW = dim.width;
            nativeH = dim.height;
        }
    } catch (e) {
        console.warn('   ! hydrate size failed, using cache metrics', e.message);
    }
    return {
        ...cached,
        imageName: file,
        base64Data,
        nativeW,
        nativeH,
        imgW: nativeW,
        imgH: nativeH
    };
}

async function run() {
    console.log('1. Reading Markdown and enumerating images...');
    console.log(`   Layout mode: SIDE CALLOUTS (human-style)`);
    console.log(`   Force refresh LLM: ${forceRefresh}`);
    console.log(`   Follow-up slides: ${allowFollowups ? 'ON' : 'OFF (default)'}`);
    console.log(`   Max figures: ${maxFigures || 'unlimited'}`);
    const mdContent = fs.readFileSync(mdPath, 'utf-8');

    let files = [];
    try {
        files = fs.readdirSync(imgDir).filter(f => /\.(png|jpg|jpeg)$/i.test(f));
        // Natural sort: Figure_2 before Figure_10
        files.sort((a, b) => {
            const na = a.match(/Figure_(\d+)/i);
            const nb = b.match(/Figure_(\d+)/i);
            if (na && nb) return parseInt(na[1], 10) - parseInt(nb[1], 10) || a.localeCompare(b);
            return a.localeCompare(b);
        });
    } catch (e) {
        console.log(`Warning: Image dir ${imgDir} missing.`);
    }
    // If both "Figure_1.png" and "PaperName_Figure_1.png" exist, keep one family.
    // Prefer short Figure_N.png (current extract_semantic_figures output); long names are legacy.
    const shortFigs = files.filter(f => /^Figure_\d+\.(png|jpg|jpeg)$/i.test(f));
    const longFigs = files.filter(f => /.+_Figure_\d+\.(png|jpg|jpeg)$/i.test(f));
    if (shortFigs.length >= 1 && longFigs.length >= 1) {
        files = shortFigs.length >= longFigs.length ? shortFigs : longFigs;
        // Always prefer short when both families exist and short has any files
        if (shortFigs.length > 0) files = shortFigs;
        console.log(`[Dedupe] Multiple figure naming schemes — preferring: ${files.join(', ')}`);
    }
    if (maxFigures > 0 && files.length > maxFigures) {
        console.log(`[Cap] Limiting figures ${files.length} → ${maxFigures}`);
        files = files.slice(0, maxFigures);
    }
    console.log(`Found ${files.length} images: ${files.join(', ')}`);

    // Separate EN/ZH caches so experiment English decks don't reuse Chinese labels
    const cachePath = path.join(path.dirname(outputPath), isEn ? 'ppt_cache_en.json' : 'ppt_cache_zh.json');
    let cache = {};
    // Always load cache for relayout when not force-refreshing LLM
    if (fs.existsSync(cachePath)) {
        try {
            cache = JSON.parse(fs.readFileSync(cachePath, 'utf-8'));
            console.log(`[Cache] Loaded ${Object.keys(cache).length} entries.`);
        } catch (e) {
            console.warn('Failed to load cache:', e.message);
        }
    }
    if (forceRefresh) {
        console.log('[Cache] --force-refresh: will re-call LLM (annotations); follow-ups still stripped unless --followups.');
    }

    const results = [];
    for (const file of files) {
        let res;
        if (!forceRefresh && cache[file] && cache[file].annotations) {
            console.log(`[Cache] -> Relayout only for ${file}`);
            res = hydrateFromCache(cache[file], file);
        } else if (forceRefresh && cache[file] && cache[file].annotations && process.env.PPT_RELAYOUT_ONLY === '1') {
            // Fast path: rebuild deck from cache without LLM
            console.log(`[Cache] -> Relayout-only (PPT_RELAYOUT_ONLY) for ${file}`);
            res = hydrateFromCache(cache[file], file);
        } else {
            res = await processImage(file, mdContent);
            if (res) {
                cache[file] = res;
                try {
                    fs.writeFileSync(cachePath, JSON.stringify(cache, null, 2), 'utf-8');
                } catch (e) {
                    console.warn('Failed to save cache:', e.message);
                }
            }
            await new Promise(r => setTimeout(r, 6000));
        }
        if (res) {
            // Strip follow-ups unless explicitly enabled
            if (!allowFollowups) res.follow_up_slides = [];
            results.push(res);
        }
    }

    // Do NOT write a blank / empty PPTX when network failed for every figure.
    // Exit non-zero so the pipeline marks the task interrupted and "重试继续" can resume
    // (per-figure cache ppt_cache_*.json is still on disk for successful slides).
    if (files.length > 0 && results.length === 0) {
        console.error(
            `\n[FATAL] No slides generated (${files.length} figures found, 0 succeeded). ` +
            `Likely network / API failure. Not writing empty PPTX. Re-run to resume from cache.`
        );
        process.exit(2);
    }
    if (files.length === 0) {
        console.warn('[WARN] No figure images found — writing title-only deck is skipped; abort.');
        process.exit(3);
    }
    const fallbackOnly = results.every(
        (r) => !r.annotations || r.annotations.length === 0 ||
            (r.overall_explanation || '').includes('自动标注失败') ||
            (r.overall_explanation || '').includes('auto labels failed')
    );
    if (fallbackOnly && results.length > 0) {
        console.warn(
            `[WARN] All ${results.length} slides are fallback placeholders (API likely failed). ` +
            `Still writing deck so images are visible; re-run after network recovery to fill labels from cache refresh.`
        );
    }

    console.log('\n2. Building presentation with side-callout layout...');
    const pres = new pptxgen();
    pres.layout = 'LAYOUT_16x9';
    pres.author = 'Paperfect';
    pres.title = path.basename(outputPath, '.pptx');

    // Build PDF↔PPT sync map: figure slides + optional follow-ups share the figure's PDF page
    const syncMap = [];
    let slideIdx = 0;
    let figPages = {};
    try {
        const metaPath = path.join(imgDir, 'figures_metadata.json');
        if (fs.existsSync(metaPath)) {
            figPages = JSON.parse(fs.readFileSync(metaPath, 'utf-8'));
            if (figPages && figPages.pages) figPages = figPages.pages;
        }
    } catch (_) {}

    results.forEach((slideData) => {
        addCalloutFigureSlide(pres, slideData);
        const figFile = slideData.imageName || '';
        let pdfPage = figPages[figFile];
        if (pdfPage == null) {
            const base = path.basename(figFile);
            pdfPage = figPages[base];
        }
        if (pdfPage == null) {
            const m = String(figFile).match(/Figure_(\d+)/i);
            pdfPage = m ? parseInt(m[1], 10) : null;
        }
        syncMap.push({
            slideIndex: slideIdx,
            kind: 'figure',
            figureFile: figFile,
            pdfPage: pdfPage
        });
        slideIdx += 1;

        const fus = slideData.follow_up_slides || [];
        if (allowFollowups && MODE === 'creative' && Array.isArray(fus)) {
            fus.forEach((fu, fi) => {
                addFollowUpSlide(pres, fu);
                syncMap.push({
                    slideIndex: slideIdx,
                    kind: 'followup',
                    figureFile: figFile,
                    followupIndex: fi,
                    pdfPage: pdfPage
                });
                slideIdx += 1;
            });
        }
    });

    // Ensure output dir; write via temp to avoid Windows file locks when PPT is open
    fs.mkdirSync(path.dirname(outputPath), { recursive: true });
    const tmpPath = outputPath.replace(/\.pptx$/i, `.__tmp_${Date.now()}.pptx`);
    let finalPath = outputPath;
    await pres.writeFile({ fileName: tmpPath });
    try {
        fs.copyFileSync(tmpPath, outputPath);
        fs.unlinkSync(tmpPath);
    } catch (e) {
        // If target is locked (open in PowerPoint), keep a sibling file
        finalPath = outputPath.replace(/\.pptx$/i, isEn ? '_EN.pptx' : '_ZH.pptx');
        try {
            fs.copyFileSync(tmpPath, finalPath);
            fs.unlinkSync(tmpPath);
            console.warn(`! Target locked, wrote alternate: ${finalPath}`);
            console.warn(`  Close PowerPoint and rename/replace the main file if needed.`);
        } catch (e2) {
            finalPath = tmpPath;
            console.warn(`! Could not replace target. PPT left at: ${tmpPath}`);
        }
    }
    // Post-process: force OOXML horz/vert overflow CLIP so glyphs never paint outside frames
    try {
        const clipPy = path.join(__dirname, 'clip_pptx_text.py');
        execFileSync('python', [clipPy, finalPath], { stdio: 'inherit' });
    } catch (e) {
        console.warn('! clip_pptx_text post-process skipped:', e.message);
    }

    // Persist slide↔PDF page map for the in-app editor (survives follow-up slides)
    try {
        const mapPath = path.join(path.dirname(outputPath), 'slide_sync_map.json');
        const pageMapping = {};
        for (const row of syncMap) {
            if (row.pdfPage != null) pageMapping[String(row.slideIndex)] = row.pdfPage;
        }
        fs.writeFileSync(mapPath, JSON.stringify({
            version: 1,
            slides: syncMap,
            page_mapping: pageMapping,
            n_slides: syncMap.length
        }, null, 2), 'utf-8');
        console.log(` Sync map: ${syncMap.length} slides → ${mapPath}`);
    } catch (e) {
        console.warn('! Failed to write slide_sync_map.json:', e.message);
    }

    console.log('========================================');
    console.log(' SUCCESS — human-style PPT exported:');
    console.log(' ' + finalPath);
    console.log(` slides: ${results.length} figure slides`);
    console.log('========================================');
}

run().catch((e) => {
    console.error('Global Error:', e);
    process.exit(1);
});
