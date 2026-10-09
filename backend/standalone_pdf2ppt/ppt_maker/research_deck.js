import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

export function fingerprint(...values) {
    return crypto.createHash('sha256').update(JSON.stringify(values)).digest('hex');
}

export function figureContext(markdown, filename, limit = 14000) {
    const number = filename.match(/Figure_(\d+)/i)?.[1];
    const chunks = String(markdown).split(/\n(?=#{1,4}\s)|\n\s*\n/);
    const pattern = number ? new RegExp(`(?:Figure|Fig\\.?|图)\\s*${number}(?![0-9])`, 'i') : null;
    const selected = new Set([0]);
    chunks.forEach((chunk, index) => {
        if (pattern?.test(chunk)) for (const i of [index-1, index, index+1]) if (i >= 0 && i < chunks.length) selected.add(i);
    });
    const result = [...selected].sort((a,b) => a-b).map(i => chunks[i]).join('\n\n');
    return result.slice(0, limit) + (result.length > limit ? '\n[Context excerpt truncated; do not infer unseen evidence.]' : '');
}

export function validateOutline(value, pageCount) {
    if (!Array.isArray(value.slides) || value.slides.length < 3 || value.slides.length > 16) throw new Error('Expected 3–16 narrative slides');
    for (const slide of value.slides) {
        if (typeof slide.title !== 'string' || !slide.title.trim() || !Array.isArray(slide.bullets) || !slide.bullets.length || slide.bullets.length > 4 || slide.bullets.some(x => typeof x !== 'string' || !x.trim())) throw new Error('Invalid slide content');
        if (typeof slide.speaker_notes !== 'string' || slide.speaker_notes.length < 40) throw new Error('Missing explanatory speaker notes');
        if (!Array.isArray(slide.source_pages) || !slide.source_pages.length || slide.source_pages.some(p => !Number.isInteger(p) || p < 1 || p > pageCount)) throw new Error('Invalid source page citation');
        if (!['before_figures', 'after_figures'].includes(slide.position)) throw new Error('Invalid slide position');
    }
    return value;
}

export async function planNarrative({client, model, baseURL, skill, context, cachePath, language, force}) {
    const hash = fingerprint(model, baseURL, skill, context, language);
    if (!force && fs.existsSync(cachePath)) {
        const cache = JSON.parse(fs.readFileSync(cachePath, 'utf8'));
        if (cache.fingerprint === hash) return validateOutline(cache.data, context.page_count);
    }
    const response = await client.chat.completions.create({model, max_tokens:10000, messages:[
        {role:'system', content:skill},
        {role:'user', content:`Write 6–10 narrative slides in ${language === 'en' ? 'English' : 'Simplified Chinese'} for a research group meeting. Cover the research question, prior limitation, core idea, detailed mechanism, evaluation conditions, findings and limitations. Put method/introduction slides before_figures; results/limits after_figures. Source is page text only: never claim visual verification. Return JSON {"slides":[{"title":"a precise claim (<=50 characters)","bullets":["up to three short points (<=90 characters each)"],"speaker_notes":"detailed explanation: motivation, mechanism, evidence, caveats (at least 150 Chinese characters or 90 English words)","source_pages":[1],"position":"before_figures|after_figures"}]}. Keep substantial explanation in notes.\nSource: ${JSON.stringify(context)}`}
    ]});
    if (response.choices[0]?.finish_reason !== 'stop') throw new Error('Narrative output incomplete');
    const raw = response.choices[0].message.content.replace(/<think>[\s\S]*?<\/think>/gi,'').trim().replace(/^```(?:json)?\s*|\s*```$/g,'');
    const data = validateOutline(JSON.parse(raw), context.page_count);
    fs.writeFileSync(cachePath, JSON.stringify({fingerprint:hash, data, usage:response.usage}, null, 2));
    return data;
}

export function addNarrativeSlide(pres, data, index, font='Microsoft YaHei') {
    // Split lengthy visible text into readable continuation slides; notes retain
    // the full explanation and are never clipped with the slide text.
    const pieces = data.bullets.flatMap(point => {
        const chars = Array.from(point);
        const result=[];
        while (chars.length) result.push(chars.splice(0, /[\u4e00-\u9fff]/.test(point) ? 68 : 140).join(''));
        return result;
    });
    const slides=[];
    for (let offset=0; offset<pieces.length; offset+=3) {
        const slide=pres.addSlide();
        const dark=index===0 && offset===0;
        slide.background={color:dark?'172B3A':'FFFFFF'};
        slide.addText(data.title, {x:.48,y:.4,w:9.04,h:.85,fontFace:font,fontSize:24,bold:true,color:dark?'FFFFFF':'172B3A',margin:0,breakLine:false,fit:'shrink'});
        pieces.slice(offset,offset+3).forEach((point,i)=>{
            const y=1.6+i*1.02;
            slide.addShape(pres.ShapeType.ellipse,{x:.5,y:y+.06,w:.32,h:.32,fill:{color:'0D9488'},line:{color:'0D9488'}});
            slide.addText(String(offset+i+1),{x:.5,y:y+.06,w:.32,h:.32,fontSize:10,bold:true,color:'FFFFFF',align:'center',valign:'mid',margin:0});
            slide.addText(point,{x:1,y,w:8.45,h:.88,fontFace:font,fontSize:18,color:dark?'E2E8F0':'334155',margin:0,breakLine:false,fit:'shrink'});
        });
        slide.addText(`PDF pp. ${data.source_pages.join(', ')} · ${offset ? 'continued · ' : ''}Paperfect`, {x:.5,y:5.13,w:9,h:.22,fontFace:font,fontSize:9,color:dark?'CBD5E1':'64748B',margin:0});
        slide.addNotes(data.speaker_notes + '\n\nSource: PDF pp. ' + data.source_pages.join(', '));
        slides.push(slide);
    }
    return slides;
}

export function localizedFigure(imgDir, filename, pageNumber) {
    const root=path.resolve(imgDir, '../research/reading');
    try {
        const manifest=JSON.parse(fs.readFileSync(path.join(root,'manifest.json'),'utf8'));
        const number=filename.match(/Figure_(\d+)/i)?.[1];
        if (!number) return null;
        const pattern=new RegExp(`(?:Figure|Fig\\.?|图)\\s*${number}(?![0-9])`,'i');
        const matches=manifest.figures.filter(f=>f.kind==='figure' && pattern.test(f.label || '') && (!pageNumber || f.page===Number(pageNumber)));
        if (matches.length!==1 || !matches[0].labels?.length) return null;
        const result=matches[0], original=path.resolve(root,result.original);
        if (!original.startsWith(root+path.sep)) return null;
        return {...result, path:original};
    } catch { return null; }
}

export function addLocalizedLabels(slide, labels, rect, font='Microsoft YaHei') {
    for (const label of labels || []) {
        if (!Array.isArray(label.bbox) || label.bbox.length!==4 || label.bbox.some(n=>!Number.isFinite(n) || n<0 || n>1000)) continue;
        const [a,b,c,d]=label.bbox;
        if (c<=a || d<=b || !/^#[0-9a-f]{6}$/i.test(label.background) || !/^#[0-9a-f]{6}$/i.test(label.color)) continue;
        const x=rect.x+a*rect.w/1000,y=rect.y+b*rect.h/1000,w=(c-a)*rect.w/1000,h=(d-b)*rect.h/1000;
        slide.addShape('rect',{x,y,w,h,fill:{color:label.background.slice(1)},line:{color:label.background.slice(1),transparency:100}});
        const rotation=label.rotation===-90?270:(label.rotation===90?90:0);
        const tw=rotation?h:w,th=rotation?w:h;
        slide.addText(label.text,{x:x+(w-tw)/2,y:y+(h-th)/2,w:tw,h:th,rotate:rotation,fontFace:font,fontSize:Math.min(16,th*72*.8),color:label.color.slice(1),margin:0,align:'center',valign:'mid',fit:'shrink'});
    }
}
