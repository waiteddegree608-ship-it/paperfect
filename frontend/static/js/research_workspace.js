// Optional research jobs; credentials remain in the backend provider settings.
(() => {
    const dialog = document.getElementById('research-dialog');
    if (!dialog) return;
    const base = '/api/research/' + encodeURIComponent(dialog.dataset.book);
    const status = document.getElementById('research-status');
    for (const kind of ['reading', 'notes']) {
        document.getElementById(`research-${kind}-link`).href = `${base}/files/${kind}/index.html`;
        document.getElementById(`research-${kind}`).onclick = async () => {
            const button = document.getElementById(`research-${kind}`);
            try {
                let pages = null;
                const value = document.getElementById('research-pages').value.trim();
                if (kind === 'reading' && value) {
                    pages = [];
                    for (const piece of value.replace(/，/g, ',').split(',')) {
                        const match = piece.trim().match(/^(\d+)(?:-(\d+))?$/);
                        if (!match) throw new Error('页码格式应为 1-5,8');
                        const start = Number(match[1]), end = Number(match[2] || match[1]);
                        if (start < 1 || end < start || end-start > 999) throw new Error('页码范围无效');
                        for (let n = start; n <= end; n++) pages.push(n);
                    }
                }
                button.disabled = true;
                const response = await fetch(`${base}/jobs`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({kind, pages, localize:document.getElementById('research-localize').checked})});
                const result = await response.json();
                if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
                status.textContent = '任务已开始，可关闭窗口；重新点击会查看正在执行的任务。';
                const poll = async () => {
                    try {
                        const response = await fetch(`${base}/jobs/${kind}`);
                        if (!response.ok) throw new Error('无法读取任务状态');
                        const state = await response.json();
                        const names = {queued:'排队中',running:'生成中',complete:'生成完成，待校对',draft:'解读初稿已生成',partial:'部分完成，请检查失败记录',failed:'生成失败',interrupted:'已中断，可以继续'};
                        status.textContent = (names[state.status] || state.status) + (state.total_pages ? ` · ${state.completed_pages}/${state.total_pages} 页` : '') + (state.error ? ` · ${state.error}` : '');
                        if (['queued','running'].includes(state.status)) setTimeout(poll, 2500);
                        else button.disabled = false;
                    } catch (error) { status.textContent = error.message; button.disabled = false; }
                };
                poll();
            } catch (error) { status.textContent = error.message; button.disabled = false; }
        };
    }
})();
