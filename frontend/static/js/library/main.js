// Use window.* so this file works both as classic script and as module
const { createApp, ref, computed, onMounted, onUnmounted, watch, reactive } = window.Vue;
const { createRouter, createWebHashHistory, useRouter, useRoute } = window.VueRouter;

// Reactive Language State for Vue template bindings
// IMPORTANT: do NOT declare top-level `const t` / `let t` / `function t` —
// i18n.js already defines global `function t`, and classic scripts share one
// lexical scope. Redeclaring throws: "Identifier 't' has already been declared"
// which aborts this entire file → Vue never mounts → blank shell UI.
const currentLang = ref(getLang());
function translate(key, params) {
    // Touch currentLang so Vue templates re-render on language switch
    const _ = currentLang.value;
    return window.t(key, params);
}

// Global language listener to update Vue reactive state
window.addEventListener('lang-changed', (e) => {
    currentLang.value = e.detail.lang;
});

// AI-generated abstracts/Q&A answers are written in Markdown; render them
// properly instead of dumping raw "**bold**"/"- list" syntax as plain text.
if (window.marked) {
    window.marked.setOptions({ breaks: true, gfm: true });
}
function renderMarkdown(text) {
    if (!text) return '';
    try {
        return window.marked ? window.marked.parse(text) : text;
    } catch (e) {
        return text;
    }
}

// Backend stores several metadata fields (research_field, research_direction, ...)
// as a JSON string like {"zh": "人工智能", "en": "Artificial Intelligence"} so both
// languages are available without a re-tag. Any UI that displays these fields must
// go through this helper instead of printing the raw string.
function parseBilingualLabel(val) {
    if (!val) return '';
    if (typeof val === 'object') {
        return val[currentLang.value] || val.zh || val.en || '';
    }
    if (typeof val === 'string' && val.trim().startsWith('{')) {
        try {
            const parsed = JSON.parse(val);
            return parsed[currentLang.value] || parsed.zh || parsed.en || val;
        } catch (e) { /* not JSON — plain legacy string value */ }
    }
    return val;
}

// Global Filter State
const filterState = reactive({
    type: [], // paper_type
    core: [], // core_type
    jcr: '',  // jcr_partition
    cas: '',  // cas_partition (Not used anymore but left in UI just in case)
    ccf: '',  // ccf_partition
    search: ''
});

/** Allow opening as soon as backend says can_open, or when not hard-blocked. */
function canOpenDoc(doc) {
    if (!doc) return false;
    if (doc.can_open === true) return true;
    if (doc.can_open === false && doc.status === 'processing') return false;
    // Fallback for older API responses / interrupted partials
    return doc.status !== 'processing' || !!(doc.has_annotated || doc.has_kb || doc.has_translated);
}

// Folder icon SVG (reusable)
const FOLDER_SVG = `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M2 6C2 4.89543 2.89543 4 4 4H9L11 6H20C21.1046 6 22 6.89543 22 8V18C22 19.1046 21.1046 20 20 20H4C2.89543 20 2 19.1046 2 18V6Z" fill="currentColor" opacity="0.85"/></svg>`;

// Folder colors for visual variety
const FOLDER_COLORS = ['#6E88BD', '#88D6CC', '#E8A87C', '#C38BD6', '#7BC88D', '#D6736E', '#6EC5D6', '#BDB86E'];

// Image 1: "My Files" (Dashboard) - Redesigned
const DashboardView = {
    template: `
        <div class="main-view" style="padding: 30px; overflow-y: auto;">
            <!-- Upload Zone -->
            <div class="upload-zone" 
                 @click="triggerUpload" 
                 @dragover.prevent="onDragOver" 
                 @dragleave.prevent="onDragLeave" 
                 @drop.prevent="onDrop"
                 :class="{dragover: isDragOver}">
                <input type="file" id="libUploadInput" accept=".pdf" multiple style="display:none;" @change="handleUpload">
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/>
                </svg>
                <div class="upload-zone-text">
                    <div class="main-text">{{ t('dash.upload_title') }}</div>
                    <div class="sub-text">{{ t('dash.upload_sub') }}</div>
                </div>
            </div>

            <!-- Breadcrumb (only when inside a folder) -->
            <div class="breadcrumb" v-if="currentFolder">
                <span class="breadcrumb-item" @click="exitFolder">{{ t('dash.all_folders') }}</span>
                <span class="breadcrumb-sep">›</span>
                <span class="breadcrumb-current">{{ currentFolder.name === '默认文件夹' && getLang() === 'en' ? 'Default Folder' : currentFolder.name }}</span>
                <span style="margin-left: auto; font-size: 12px; color: var(--text-muted);">{{ folderDocs.length }} {{ t('dash.files_unit') }}</span>
            </div>
            <!-- Drop targets while inside a folder -->
            <div class="folder-drop-rail" v-if="currentFolder" style="display:flex; flex-wrap:wrap; gap:8px; margin: 0 0 16px 0;">
                <div v-for="(folder, idx) in folders" :key="'rail-'+folder.id"
                     class="folder-rail-chip"
                     @dragover.prevent="onFolderDragOver($event, folder)"
                     @dragleave="onFolderDragLeave($event, folder)"
                     @drop.prevent="onFolderDrop($event, folder)"
                     :class="{ 'drop-target': dropFolderId === folder.id }"
                     style="padding:6px 12px; border-radius:999px; border:1px solid var(--header-border); background:var(--card-bg); font-size:12px; color:var(--text-color); cursor:default;"
                     :style="dropFolderId === folder.id ? { borderColor: 'var(--primary-accent)', borderStyle: 'dashed' } : {}">
                    {{ folder.name === '默认文件夹' && getLang() === 'en' ? 'Default Folder' : folder.name }}
                </div>
            </div>
 
            <!-- Folder Inner View -->
            <template v-if="currentFolder">
                <div class="file-grid" v-if="folderDocs.length > 0">
                    <div class="file-card" v-for="doc in folderDocs" :key="doc.id"
                         draggable="true"
                         @dragstart="onDocDragStart($event, doc)"
                         @dragend="onDocDragEnd"
                         @click="!dragMoved && canOpenDoc(doc) && openChat(doc.original_filename, doc)"
                         :style="{ cursor: canOpenDoc(doc) ? 'pointer' : 'default' }"
                         :title="(getLang() === 'en' ? doc.title : (doc.zh_title || doc.title)) + (getLang() === 'en' ? ' — drag to a folder' : ' — 可拖到文件夹')">
                        <button class="delete-btn" @click="deleteDoc($event, doc.id)">×</button>
                        <div class="file-cover" style="position: relative;">
                            <img :src="'/cover/' + encodeURIComponent(doc.original_filename.replace('.pdf',''))" onerror="this.src='/static/favicon.png'" />
                            <div v-if="doc.status === 'processing'" style="position: absolute; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.72); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; color: #fff; text-align: center; padding: 6px; z-index: 10;">
                                <div class="spinner" style="width: 18px; height: 18px; border: 2px solid rgba(255,255,255,0.2); border-top-color: var(--primary-accent); border-radius: 50%;"></div>
                                <div style="font-size: 10px; font-weight: 600; color: #fff;">{{ doc.progress }} {{ doc.percent }}%</div>
                                <div v-if="canOpenDoc(doc)" style="font-size: 9px; opacity: 0.85;">{{ getLang() === 'en' ? 'Click to open' : '可点击打开' }}</div>
                            </div>
                            <div v-else-if="doc.status === 'interrupted'" style="position: absolute; left: 0; right: 0; bottom: 0; background: rgba(127,29,29,0.9); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; color: #fff; text-align: center; padding: 8px; z-index: 10;" @click.stop>
                                <div style="font-size: 10px; font-weight: 600;">{{ doc.progress || (getLang() === 'en' ? 'Incomplete' : '未完成') }}</div>
                                <button type="button" @click.stop="resumeDoc(doc)" style="background:#10b981;border:none;color:#fff;padding:4px 10px;border-radius:6px;font-size:11px;cursor:pointer;font-weight:600;">{{ getLang() === 'en' ? 'Continue' : '继续' }}</button>
                            </div>
                        </div>
                        <div class="file-title">{{ getLang() === 'en' ? doc.title : (doc.zh_title || doc.title) }}</div>
                    </div>
                </div>
                <div class="empty-state" v-else>
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><polyline points="13 2 13 9 20 9"/></svg>
                    <div class="empty-title">{{ t('dash.folder_empty_title') }}</div>
                    <div class="empty-sub">{{ t('dash.folder_empty_sub') }}</div>
                </div>
            </template>
 
            <!-- Main Dashboard View -->
            <template v-else>
                <!-- Folders Section -->
                <div class="section-header">
                    <div class="section-title">{{ t('dash.folders_title') }}
                        <span class="drag-hint">{{ getLang() === 'en' ? '· Drag covers onto folders' : '· 将封面拖到文件夹' }}</span>
                    </div>
                </div>
                <div class="folder-grid">
                    <div class="folder-card" v-for="(folder, idx) in folders" :key="folder.id"
                         @click="enterFolder(folder)"
                         @dragover.prevent="onFolderDragOver($event, folder)"
                         @dragleave="onFolderDragLeave($event, folder)"
                         @drop.prevent="onFolderDrop($event, folder)"
                         :class="{ 'drop-target': dropFolderId === folder.id }">
                        <button class="folder-menu-btn" @click.stop="showContextMenu($event, folder)">⋯</button>
                        <div class="folder-icon" :style="{color: folderColor(idx)}">
                            ${FOLDER_SVG}
                        </div>
                        <div class="folder-name">{{ folder.name === '默认文件夹' && getLang() === 'en' ? 'Default Folder' : folder.name }}</div>
                        <div class="folder-count">{{ folder.doc_count || 0 }} {{ t('dash.files_unit') }}</div>
                    </div>
                    <!-- Add Folder Card -->
                    <div class="folder-card add-folder" @click="openCreateFolder">
                        <div class="folder-icon">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
                        </div>
                        <div class="folder-name">{{ t('dash.new_folder') }}</div>
                    </div>
                </div>
 
                <!-- Recent Uploads Section -->
                <div class="section-header" style="margin-top: 10px;">
                    <div class="section-title">{{ t('dash.recent_title') }}</div>
                </div>
                <div class="recent-scroll">
                    <div class="recent-card" v-for="doc in recentDocs" :key="doc.id"
                         draggable="true"
                         @dragstart="onDocDragStart($event, doc)"
                         @dragend="onDocDragEnd"
                         :title="(doc.title || '') + (getLang() === 'en' ? ' — drag to a folder' : ' — 可拖到文件夹')"
                         @click="!dragMoved && canOpenDoc(doc) && openChat(doc.original_filename, doc)"
                         :style="{ cursor: canOpenDoc(doc) ? 'pointer' : 'default' }">
                        <button class="delete-btn" @click="deleteDoc($event, doc.id)">×</button>
                        <div style="position: relative; width: 100%; height: 100%;">
                            <img :src="'/cover/' + encodeURIComponent(doc.original_filename.replace('.pdf',''))" onerror="this.src='/static/favicon.png'" style="width: 100%; height: 100%; object-fit: cover;" />
                            <div v-if="doc.status === 'processing'" style="position: absolute; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.72); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3px; color: #fff; text-align: center; padding: 5px; z-index: 10;">
                                <div class="spinner" style="width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.2); border-top-color: var(--primary-accent); border-radius: 50%;"></div>
                                <div style="font-size: 10px; font-weight: 600; color: #fff;">{{ doc.progress }} {{ doc.percent }}%</div>
                                <div v-if="canOpenDoc(doc)" style="font-size: 9px; opacity: 0.85;">{{ getLang() === 'en' ? 'Click to open' : '可点击打开' }}</div>
                            </div>
                            <div v-else-if="doc.status === 'interrupted'" style="position: absolute; left: 0; right: 0; bottom: 0; background: rgba(127,29,29,0.9); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 5px; color: #fff; text-align: center; padding: 6px; z-index: 10;" @click.stop>
                                <div style="font-size: 10px; font-weight: 600;">{{ doc.progress || (getLang() === 'en' ? 'Incomplete' : '未完成') }}</div>
                                <button type="button" @click.stop="resumeDoc(doc)" style="background:#10b981;border:none;color:#fff;padding:3px 8px;border-radius:6px;font-size:10px;cursor:pointer;font-weight:600;">{{ getLang() === 'en' ? 'Continue' : '继续' }}</button>
                            </div>
                        </div>
                        <div class="card-title-bar">{{ getLang() === 'en' ? doc.title : (doc.zh_title || doc.title) }}</div>
                    </div>
                    <div v-if="recentDocs.length === 0" class="empty-state" style="padding: 40px; width: 100%;">
                        <div class="empty-title">{{ t('dash.no_uploads') }}</div>
                        <div class="empty-sub">{{ t('dash.drop_hint') }}</div>
                    </div>
                </div>
            </template>
        </div>
    `,
    setup() {
        const folders = ref([]);
        const recentDocs = ref([]);
        const isDragOver = ref(false);
        const currentFolder = ref(null);
        const folderDocs = ref([]);
        const contextTarget = ref(null);
        const dropFolderId = ref(null);
        const dragMoved = ref(false);

        let statusPollInterval = null;
        const startStatusPolling = () => {
            if (statusPollInterval) return;
            statusPollInterval = setInterval(async () => {
                await loadRecentDocs();
                if (currentFolder.value) {
                    await loadFolderDocs(currentFolder.value.id);
                }
                const hasProcessingRecent = recentDocs.value.some(d => d.status === 'processing');
                const hasProcessingFolder = folderDocs.value.some(d => d.status === 'processing');
                if (!hasProcessingRecent && !hasProcessingFolder) {
                    clearInterval(statusPollInterval);
                    statusPollInterval = null;
                }
            }, 3000);
        };

        const checkAndStartPolling = () => {
            const hasProcessingRecent = recentDocs.value.some(d => d.status === 'processing');
            const hasProcessingFolder = folderDocs.value.some(d => d.status === 'processing');
            if (hasProcessingRecent || hasProcessingFolder) {
                startStatusPolling();
            } else {
                if (statusPollInterval) {
                    clearInterval(statusPollInterval);
                    statusPollInterval = null;
                }
            }
        };

        const loadFolders = async () => {
            try {
                const fRes = await fetch('/api/library/folders');
                if (!fRes.ok) throw new Error('folders ' + fRes.status);
                folders.value = await fRes.json();
            } catch (e) {
                console.error('[Dashboard] loadFolders failed', e);
                folders.value = folders.value || [];
            }
        };

        const loadRecentDocs = async () => {
            try {
                const dRes = await fetch('/api/library/documents');
                if (!dRes.ok) throw new Error('documents ' + dRes.status);
                const allDocs = await dRes.json();
                recentDocs.value = Array.isArray(allDocs) ? allDocs.slice(-8).reverse() : [];
                checkAndStartPolling();
            } catch (e) {
                console.error('[Dashboard] loadRecentDocs failed', e);
                recentDocs.value = recentDocs.value || [];
            }
        };

        const loadFolderDocs = async (folderId) => {
            try {
                const dRes = await fetch('/api/library/documents?folder_id=' + folderId);
                if (!dRes.ok) throw new Error('folder docs ' + dRes.status);
                folderDocs.value = await dRes.json();
                checkAndStartPolling();
            } catch (e) {
                console.error('[Dashboard] loadFolderDocs failed', e);
                folderDocs.value = [];
            }
        };

        onUnmounted(() => {
            if (statusPollInterval) {
                clearInterval(statusPollInterval);
                statusPollInterval = null;
            }
        });

        onMounted(async () => {
            await Promise.all([loadFolders(), loadRecentDocs()]);
            
            // Attach upload button logic
            const uploadBtn = document.getElementById('finalUploadBtn');
            if (uploadBtn) {
                uploadBtn.onclick = async () => {
                    const files = window.uploadSelectedFiles && window.uploadSelectedFiles.length
                        ? window.uploadSelectedFiles
                        : (window.uploadSelectedFile ? [window.uploadSelectedFile] : []);
                    if (!files.length) return;
                    uploadBtn.innerText = translate('upload.uploading');
                    uploadBtn.disabled = true;
                    try {
                        for (let i = 0; i < files.length; i++) {
                            const file = files[i];
                            uploadBtn.innerText = translate('upload.uploading') + ` (${i + 1}/${files.length})`;
                            const fd = new FormData();
                            fd.append('file', file);
                            fd.append('item_type', document.getElementById('upload_item_type').value);
                            const folderSelect = document.getElementById('upload_folder_select').value;
                            const folderNew = document.getElementById('upload_folder_new').value;
                            if (folderNew) fd.append('folder_name', folderNew);
                            else if (folderSelect) fd.append('folder_id', folderSelect);
                            if (document.getElementById('upload_item_type').value === 'paper') {
                                fd.append('prompt_type', document.getElementById('upload_prompt').value || '提示词汇总');
                                fd.append('ppt_mode', document.getElementById('upload_ppt_mode').value);
                                fd.append('ppt_lang', document.getElementById('upload_language').value);
                                fd.append('do_translate', document.getElementById('upload_do_translate').checked ? 'true' : 'false');
                                fd.append('do_annotate', document.getElementById('upload_do_annotate').checked ? 'true' : 'false');
                                fd.append('do_ppt', document.getElementById('upload_do_ppt').checked ? 'true' : 'false');
                            }
                            const res = await fetch('/api/library/upload', { method: 'POST', body: fd });
                            if (!res.ok) {
                                const err = await res.json().catch(() => ({}));
                                throw new Error(err.detail || err.message || ('HTTP ' + res.status));
                            }
                        }
                        window.location.reload();
                    } catch (e) {
                        alert(translate('upload.error') + (e && e.message ? ': ' + e.message : ''));
                        uploadBtn.innerText = translate('upload.confirm');
                        uploadBtn.disabled = false;
                    }
                };
            }

            // Create folder button
            const createBtn = document.getElementById('createFolderBtn');
            if (createBtn) {
                createBtn.onclick = async () => {
                    const name = document.getElementById('newFolderName').value.trim();
                    if (!name) return;
                    const formData = new FormData();
                    formData.append('name', name);
                    await fetch('/api/library/folders', { method: 'POST', body: formData });
                    document.getElementById('createFolderModal').classList.remove('active');
                    document.getElementById('newFolderName').value = '';
                    await loadFolders();
                };
            }

            // Rename folder button
            const renameBtn = document.getElementById('renameFolderBtn');
            if (renameBtn) {
                renameBtn.onclick = async () => {
                    const newName = document.getElementById('renameFolderInput').value.trim();
                    if (!newName || !contextTarget.value) return;
                    await fetch('/api/library/folders/' + contextTarget.value.id, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ name: newName })
                    });
                    document.getElementById('renameFolderModal').classList.remove('active');
                    await loadFolders();
                };
            }

            // Context menu actions
            const ctxRename = document.getElementById('ctxRename');
            const ctxDelete = document.getElementById('ctxDelete');
            if (ctxRename) {
                ctxRename.onclick = () => {
                    hideContextMenu();
                    if (!contextTarget.value) return;
                    document.getElementById('renameFolderInput').value = contextTarget.value.name;
                    document.getElementById('renameFolderModal').classList.add('active');
                    setTimeout(() => document.getElementById('renameFolderInput').focus(), 100);
                };
            }
            if (ctxDelete) {
                ctxDelete.onclick = async () => {
                    hideContextMenu();
                    if (!contextTarget.value) return;
                    if (confirm(translate('folder.confirm_delete', {name: contextTarget.value.name}))) {
                        await fetch('/api/library/folders/' + contextTarget.value.id, { method: 'DELETE' });
                        await loadFolders();
                    }
                };
            }

            // Close context menu on click elsewhere
            document.addEventListener('click', () => hideContextMenu());

            // Enter key for create folder modal
            document.getElementById('newFolderName').addEventListener('keyup', (e) => {
                if (e.key === 'Enter') document.getElementById('createFolderBtn').click();
            });
            document.getElementById('renameFolderInput').addEventListener('keyup', (e) => {
                if (e.key === 'Enter') document.getElementById('renameFolderBtn').click();
            });
        });

        // Drag and drop
        const onDragOver = () => { isDragOver.value = true; };
        const onDragLeave = () => { isDragOver.value = false; };
        const fillUploadModal = async (fileList) => {
            const files = Array.from(fileList || []).filter(f => (f.name || '').toLowerCase().endsWith('.pdf'));
            if (!files.length) return;
            window.uploadSelectedFiles = files;
            window.uploadSelectedFile = files[0];
            const nameEl = document.getElementById('selectedFileName');
            const listEl = document.getElementById('selectedFileList');
            if (nameEl) {
                nameEl.innerText = files.length === 1
                    ? (translate('upload.current_file') + files[0].name)
                    : (translate('upload.batch_count') + files.length);
            }
            if (listEl) {
                listEl.innerHTML = files.map(f => `<li>${f.name}</li>`).join('');
            }
            document.getElementById('upload_folder_select').innerHTML = '<option value="">' + translate('upload.folder_default') + '</option>' + folders.value.map(f => {
                const name = f.name === '默认文件夹' ? translate('upload.folder_default') : f.name;
                return `<option value="${f.id}">${name}</option>`;
            }).join('');
            try {
                const lang = getLang();
                const res = await fetch('/api/prompts?lang=' + lang);
                const data = await res.json();
                const sel = document.getElementById('upload_prompt');
                if (sel && data.prompts) {
                    sel.innerHTML = data.prompts.map(p => {
                        const id = p.id || p;
                        const name = p.name || p.id || p;
                        const selected = id === '提示词汇总' ? ' selected' : '';
                        return `<option value="${id}"${selected}>${name}</option>`;
                    }).join('');
                    if (!sel.value && data.prompts[0]) sel.value = data.prompts[0].id || data.prompts[0];
                }
            } catch (e) {}
            document.getElementById('uploadModal').classList.add('active');
        };

        const onDrop = (e) => {
            isDragOver.value = false;
            fillUploadModal(e.dataTransfer.files);
        };

        const triggerUpload = () => { document.getElementById('libUploadInput').click(); };
        const handleUpload = (e) => {
            fillUploadModal(e.target.files);
        };
        
        const openChat = (filename, doc) => {
            if (window.openReaderTab) window.openReaderTab(filename, doc);
            else window.location.href = '/chat/' + encodeURIComponent((filename || '').replace(/\.pdf$/i, ''));
        };

        const resumeDoc = async (doc) => {
            try {
                const book = (doc.original_filename || doc.title || '').replace(/\.pdf$/i, '');
                if (!book) return;
                const res = await fetch('/api/resume/' + encodeURIComponent(book), { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (data.status === 'error') {
                    alert(data.message || (getLang() === 'en' ? 'Resume failed' : '无法继续解析'));
                    return;
                }
                doc.status = 'processing';
                doc.progress = getLang() === 'en' ? 'Resuming…' : '继续解析中…';
                doc.percent = doc.percent || 5;
                startStatusPolling();
            } catch (e) {
                alert(getLang() === 'en' ? 'Resume failed' : '无法继续解析');
            }
        };
        
        const deleteDoc = async (e, id) => {
            e.stopPropagation();
            if (confirm(translate('confirm.delete_doc'))) {
                await fetch('/api/library/documents/' + id, { method: 'DELETE' });
                recentDocs.value = recentDocs.value.filter(d => d.id !== id);
                folderDocs.value = folderDocs.value.filter(d => d.id !== id);
            }
        };

        // Folder navigation
        const enterFolder = async (folder) => {
            currentFolder.value = folder;
            await loadFolderDocs(folder.id);
        };
        const exitFolder = () => {
            currentFolder.value = null;
            folderDocs.value = [];
        };

        // Folder CRUD
        const openCreateFolder = () => {
            document.getElementById('newFolderName').value = '';
            document.getElementById('createFolderModal').classList.add('active');
            setTimeout(() => document.getElementById('newFolderName').focus(), 100);
        };

        // Context menu
        const showContextMenu = (e, folder) => {
            e.preventDefault();
            e.stopPropagation();
            contextTarget.value = folder;
            const menu = document.getElementById('folderContextMenu');
            menu.style.display = 'block';
            menu.style.left = e.clientX + 'px';
            menu.style.top = e.clientY + 'px';
        };
        const hideContextMenu = () => {
            document.getElementById('folderContextMenu').style.display = 'none';
        };

        // Folder color helper
        const folderColor = (idx) => FOLDER_COLORS[idx % FOLDER_COLORS.length];

        // --- Drag paper covers into folders ---
        const onDocDragStart = (e, doc) => {
            if (!doc || doc.id == null) return;
            e.dataTransfer.setData('text/paperfect-doc-id', String(doc.id));
            e.dataTransfer.setData('text/plain', String(doc.id));
            e.dataTransfer.effectAllowed = 'move';
            try {
                e.dataTransfer.setDragImage(e.currentTarget, 40, 40);
            } catch (_) {}
        };
        const onDocDragEnd = () => {
            // Suppress the click that browsers fire after a successful drag
            dragMoved.value = true;
            dropFolderId.value = null;
            setTimeout(() => { dragMoved.value = false; }, 120);
        };
        const onFolderDragOver = (e, folder) => {
            // Only highlight for our document drags (or unknown types)
            e.dataTransfer.dropEffect = 'move';
            dropFolderId.value = folder.id;
        };
        const onFolderDragLeave = (e, folder) => {
            if (dropFolderId.value === folder.id) dropFolderId.value = null;
        };
        const onFolderDrop = async (e, folder) => {
            dropFolderId.value = null;
            const raw = e.dataTransfer.getData('text/paperfect-doc-id') || e.dataTransfer.getData('text/plain');
            const docId = parseInt(raw, 10);
            if (!docId || !folder) return;
            // Ignore PDF file drops here (upload zone handles those)
            if (e.dataTransfer.files && e.dataTransfer.files.length > 0) return;
            try {
                const res = await fetch('/api/library/documents/' + docId + '/move', {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ folder_id: folder.id })
                });
                if (!res.ok) throw new Error('move failed ' + res.status);
                await Promise.all([loadFolders(), loadRecentDocs()]);
                if (currentFolder.value) {
                    if (currentFolder.value.id === folder.id) {
                        await loadFolderDocs(folder.id);
                    } else {
                        // left current folder
                        folderDocs.value = folderDocs.value.filter(d => d.id !== docId);
                    }
                }
            } catch (err) {
                console.error('[Dashboard] move document failed', err);
                alert(getLang() === 'en' ? 'Failed to move paper' : '移动文献失败');
            }
        };

        return { 
            folders, recentDocs, isDragOver, currentFolder, folderDocs,
            dropFolderId, dragMoved,
            triggerUpload, handleUpload, openChat, resumeDoc, deleteDoc, canOpenDoc,
            onDragOver, onDragLeave, onDrop,
            onDocDragStart, onDocDragEnd, onFolderDragOver, onFolderDragLeave, onFolderDrop,
            enterFolder, exitFolder, openCreateFolder,
            showContextMenu, folderColor, t: translate, getLang
        };
    }
};

// Wrapper for "自动分类" which has the Sub-Nav and Right Sidebar
const AutoLayout = {
    template: `
        <div style="display:flex; flex-direction:column; width: 100%; height: 100%; flex: 1; overflow: hidden;">
            <div class="sub-nav-bar" style="display:flex;gap:8px;padding:10px 18px;border-bottom:1px solid var(--header-border);">
                <router-link to="/auto/list" class="layout-btn" active-class="active">{{ t('auto.tab_classify') }}</router-link>
                <router-link to="/auto/graph" class="layout-btn" active-class="active">{{ t('auto.tab_relations') }}</router-link>
                <router-link to="/auto/search" class="layout-btn" active-class="active">{{ t('auto.tab_search') }}</router-link>
            </div>
            <div class="content-area">
                <!-- Main Area for sub-routes -->
                <div class="main-view">
                    <router-view></router-view>
                </div>
                
                <!-- Right Sidebar (Only for List & Graph) -->
                <div class="right-sidebar" v-if="$route.path === '/auto/list'">
                        <div class="filter-section">
                            <div class="filter-title">{{ t('filter.search_title') }}</div>
                            <input type="text" v-model="filterState.search" :placeholder="t('filter.search_placeholder')" style="width:100%; box-sizing:border-box; background:var(--input-bg); color:var(--text-color); border:1px solid var(--header-border); height:28px; padding: 0 5px;">
                        </div>

                        <div class="filter-section">
                            <div class="filter-title">{{ t('filter.type_title') }}</div>
                            <label class="checkbox-row"><input type="checkbox" value="综述" v-model="filterState.type"> {{ t('filter.review') }}</label>
                            <label class="checkbox-row"><input type="checkbox" value="研究" v-model="filterState.type"> {{ t('filter.research') }}</label>
                        </div>

                        <div class="filter-section">
                            <div class="filter-title">{{ t('filter.core_title') }}</div>
                            <label class="checkbox-row"><input type="checkbox" value="南大核心" v-model="filterState.core"> {{ t('filter.cssci') }}</label>
                            <label class="checkbox-row"><input type="checkbox" value="北大核心" v-model="filterState.core"> {{ t('filter.pku') }}</label>
                            <label class="checkbox-row"><input type="checkbox" value="中文核心" v-model="filterState.core"> {{ t('filter.chinese') }}</label>
                        </div>
                        
                        <!-- JCR Partition -->
                        <div class="filter-section" style="padding-bottom: 2px;">
                            <div style="text-align:center; font-size:12px; margin-bottom:5px;">{{ t('filter.jcr_partition') }}</div>
                            <div class="segmented-control">
                                <button :class="{active: filterState.jcr === '一区'}" @click="filterState.jcr = filterState.jcr === '一区' ? '' : '一区'">{{ t('filter.q1') }}</button>
                                <button :class="{active: filterState.jcr === '二区'}" @click="filterState.jcr = filterState.jcr === '二区' ? '' : '二区'">{{ t('filter.q2') }}</button>
                                <button :class="{active: filterState.jcr === '三区'}" @click="filterState.jcr = filterState.jcr === '三区' ? '' : '三区'">{{ t('filter.q3') }}</button>
                                <button :class="{active: filterState.jcr === '四区'}" @click="filterState.jcr = filterState.jcr === '四区' ? '' : '四区'">{{ t('filter.q4') }}</button>
                            </div>
                        </div>

                        <!-- CCF Partition -->
                        <div class="filter-section" style="padding-bottom: 2px;">
                            <div style="text-align:center; font-size:12px; margin-bottom:5px;">{{ t('filter.ccf_partition') }}</div>
                            <div class="segmented-control">
                                <button :class="{active: filterState.ccf === 'A'}" @click="filterState.ccf = filterState.ccf === 'A' ? '' : 'A'">A</button>
                                <button :class="{active: filterState.ccf === 'B'}" @click="filterState.ccf = filterState.ccf === 'B' ? '' : 'B'">B</button>
                                <button :class="{active: filterState.ccf === 'C'}" @click="filterState.ccf = filterState.ccf === 'C' ? '' : 'C'">C</button>
                            </div>
                        </div>
                </div>
            </div>
        </div>
    `,
    setup() {
        return { filterState, t: translate };
    }
};

// Image 2: Document List
const ListView = {
    template: `
        <div>
            <div class="doc-list-item" v-for="doc in filteredDocuments" :key="doc.id" @click="canOpenDoc(doc) && openChat(doc.original_filename, doc)" :style="{ cursor: canOpenDoc(doc) ? 'pointer' : 'default', opacity: doc.status === 'processing' ? 0.92 : 1 }">
                <button class="delete-btn" @click="deleteDoc($event, doc.id)" title="永久删除" style="right: 20px; top: 20px;">×</button>
                <button class="delete-btn" @click="retagDoc($event, doc)" :title="t('auto.retag')" style="right: 52px; top: 20px; font-size:11px; width:auto; padding:0 8px;">{{ t('auto.retag') }}</button>
                <div class="doc-title" style="position: relative;">
                    {{ getLang() === 'en' ? doc.title : (doc.zh_title || doc.title) }}
                    <div v-if="getLang() !== 'en' && doc.zh_title" style="font-size: 14px; color: var(--text-muted); font-weight: normal; margin-top: 5px;">{{ doc.title }}</div>
                    <div v-if="isMetaPending(doc)" class="meta-pending-badge">{{ getLang() === 'en' ? 'Metadata pending' : '待补全分类信息' }}</div>
                    
                    <div v-if="doc.status === 'processing'" style="margin-top: 10px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                        <div class="spinner" style="width: 14px; height: 14px; border: 2px solid rgba(255,255,255,0.2); border-top-color: var(--primary-accent); border-radius: 50%;"></div>
                        <span style="font-size: 12px; color: var(--primary-accent); font-weight: bold;">{{ doc.progress }} ({{ doc.percent }}%)</span>
                        <div style="flex: 1; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; overflow: hidden; max-width: 200px;">
                            <div :style="{ width: doc.percent + '%' }" style="height: 100%; background: var(--primary-accent); transition: width 0.3s;"></div>
                        </div>
                        <span v-if="canOpenDoc(doc)" style="font-size: 11px; color: var(--text-muted);">{{ getLang() === 'en' ? 'Click to open (partial ready)' : '可点击打开（部分已就绪）' }}</span>
                    </div>
                    <div v-else-if="doc.status === 'interrupted'" style="margin-top: 10px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;" @click.stop>
                        <span style="font-size: 12px; color: #f87171; font-weight: 600;">{{ doc.progress || (getLang() === 'en' ? 'Incomplete' : '未完成') }}</span>
                        <button type="button" @click.stop="resumeDoc(doc)" style="background:#10b981;border:none;color:#fff;padding:4px 10px;border-radius:6px;font-size:11px;cursor:pointer;font-weight:600;">{{ getLang() === 'en' ? 'Continue' : '继续' }}</button>
                    </div>
                </div>
                
                <!-- Display new metadata tags -->
                <div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; align-items: center;">
                    <span class="tag-badge" style="background: var(--header-bg); border: 1px solid var(--primary-accent); color: var(--primary-accent);" v-if="doc.venue && doc.venue !== 'Unknown'">{{ doc.venue }}</span>
                    <span class="tag-badge" style="background: rgba(148, 163, 184, 0.2); color: #cbd5e1;" v-if="doc.year">{{ doc.year }}</span>
                    <span class="tag-badge" style="background: rgba(46, 204, 113, 0.2); color: #2ecc71;" v-if="doc.paper_type">{{ tMetadata(doc.paper_type) }}</span>
                    <span class="tag-badge" style="background: rgba(231, 76, 60, 0.2); color: #e74c3c;" v-if="doc.ccf_partition">CCF {{ doc.ccf_partition }}</span>
                    <span class="tag-badge" style="background: rgba(155, 89, 182, 0.2); color: #9b59b6;" v-if="doc.jcr_partition">JCR {{ tMetadata(doc.jcr_partition) }}</span>
                    <span class="tag-badge" style="background: rgba(241, 196, 15, 0.2); color: #f1c40f;" v-if="doc.core_type">{{ tMetadata(doc.core_type) }}</span>
                    <span class="tag-badge" style="background: rgba(52, 152, 219, 0.2); color: #3498db;" v-if="doc.research_field">{{ tMetadata(doc.research_field) }}</span>
                    <span class="tag-badge" style="background: rgba(52, 152, 219, 0.1); color: #2980b9; border: 1px solid rgba(52, 152, 219, 0.3);" v-if="doc.research_direction">{{ tMetadata(doc.research_direction) }}</span>
                </div>
                
                <div class="doc-abstract" style="margin-top: 10px;">
                    {{ getLang() === 'en' ? (doc.en_abstract || doc.abstract || 'No abstract available.') : (doc.abstract || doc.en_abstract || '该文献暂无摘要信息。') }}
                </div>
                
                <div class="doc-tags" style="margin-top: 8px;">
                    <template v-if="getLang() === 'en' && doc.en_keywords">
                        <span class="tag-badge" v-for="kw in parseKeywords(doc.en_keywords)" :key="kw">{{ kw }}</span>
                    </template>
                    <template v-else>
                        <span class="tag-badge" v-for="tag in doc.tags" :key="tag.id">{{ tag.name }}</span>
                    </template>
                </div>
            </div>
            <div v-if="filteredDocuments.length === 0" style="text-align: center; color: var(--text-muted); margin-top: 50px;">
                {{ getLang() === 'en' ? 'No classified documents' : '暂无分类文献' }}
            </div>
        </div>
    `,
    setup() {
        const rawDocuments = ref([]);
        
        let statusPollInterval = null;
        const startStatusPolling = () => {
            if (statusPollInterval) return;
            statusPollInterval = setInterval(async () => {
                await loadDocuments();
                const hasProcessing = rawDocuments.value.some(d => d.status === 'processing');
                if (!hasProcessing) {
                    clearInterval(statusPollInterval);
                    statusPollInterval = null;
                }
            }, 3000);
        };

        const checkAndStartPolling = () => {
            const hasProcessing = rawDocuments.value.some(d => d.status === 'processing');
            if (hasProcessing) {
                startStatusPolling();
            } else {
                if (statusPollInterval) {
                    clearInterval(statusPollInterval);
                    statusPollInterval = null;
                }
            }
        };

        const loadDocuments = async () => {
            const dRes = await fetch('/api/library/documents');
            rawDocuments.value = await dRes.json();
            checkAndStartPolling();
        };

        onMounted(async () => {
            await loadDocuments();
            
            onUnmounted(() => {
                if (statusPollInterval) {
                    clearInterval(statusPollInterval);
                    statusPollInterval = null;
                }
            });
        });
        
        const filteredDocuments = computed(() => {
            return rawDocuments.value.filter(doc => {
                // search text filter
                if (filterState.search) {
                    const q = filterState.search.toLowerCase();
                    const titleMatch = doc.title.toLowerCase().includes(q) || (doc.zh_title && doc.zh_title.toLowerCase().includes(q));
                    const tagMatch = doc.tags.some(t => t.name.toLowerCase().includes(q));
                    const absMatch = doc.abstract && doc.abstract.toLowerCase().includes(q);
                    if (!titleMatch && !tagMatch && !absMatch) return false;
                }
                
                // Type filter (综述/研究)
                if (filterState.type.length > 0) {
                    if (!filterState.type.includes(doc.paper_type)) return false;
                }
                
                // Core venue filter
                if (filterState.core.length > 0) {
                    let hasMatch = false;
                    for (let c of filterState.core) {
                        if (doc.core_type && doc.core_type.includes(c)) {
                            hasMatch = true;
                            break;
                        }
                    }
                    if (!hasMatch) return false;
                }
                
                // JCR filter
                if (filterState.jcr) {
                    if (doc.jcr_partition !== filterState.jcr) return false;
                }
                
                // CCF filter
                if (filterState.ccf) {
                    if (doc.ccf_partition !== filterState.ccf) return false;
                }
                
                return true;
            });
        });
        
        const openChat = (filename, doc) => {
            if (window.openReaderTab) window.openReaderTab(filename, doc);
            else window.location.href = '/chat/' + encodeURIComponent((filename || '').replace(/\.pdf$/i, ''));
        };

        const resumeDoc = async (doc) => {
            try {
                const book = (doc.original_filename || doc.title || '').replace(/\.pdf$/i, '');
                if (!book) return;
                const res = await fetch('/api/resume/' + encodeURIComponent(book), { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (data.status === 'error') {
                    alert(data.message || (getLang() === 'en' ? 'Resume failed' : '无法继续'));
                    return;
                }
                doc.status = 'processing';
                doc.progress = getLang() === 'en' ? 'Resuming…' : '继续中…';
                doc.percent = doc.percent || 5;
                startStatusPolling();
            } catch (e) {
                alert(getLang() === 'en' ? 'Resume failed' : '无法继续');
            }
        };
        
        const deleteDoc = async (e, id) => {
            e.stopPropagation();
            if (confirm(translate('confirm.delete_doc'))) {
                await fetch('/api/library/documents/' + id, { method: 'DELETE' });
                rawDocuments.value = rawDocuments.value.filter(d => d.id !== id);
            }
        };

        const retagDoc = async (e, doc) => {
            e.stopPropagation();
            try {
                const res = await fetch('/api/library/documents/' + doc.id + '/retag', { method: 'POST' });
                const data = await res.json().catch(() => ({}));
                if (!res.ok) throw new Error(data.detail || data.message || res.status);
                Object.assign(doc, data);
                alert(translate('auto.retag_ok'));
            } catch (err) {
                alert((translate('auto.retag_fail') || 'retag failed') + ': ' + (err.message || err));
            }
        };

        const parseKeywords = (kwStr) => {
            try { return JSON.parse(kwStr || '[]'); }
            catch { return []; }
        };

        const tMetadata = (val) => {
            if (!val) return '';
            const current_lang = currentLang.value;
            
            // Check if it is a JSON string containing multi-language translations (e.g. {"zh": "...", "en": "..."})
            try {
                if (typeof val === 'string' && val.trim().startsWith('{')) {
                    const parsed = JSON.parse(val);
                    return parsed[current_lang] || parsed['zh'] || val;
                }
            } catch (e) {}

            if (current_lang !== 'en') return val;
            const dict = {
                // Core
                'AI辅助文化视觉设计规划': 'AI-assisted Cultural Visual Design Planning',
                '研究': 'Research',
                '综述': 'Review',
                '南大核心': 'CSSCI',
                '北大核心': 'PKU Core',
                '中文核心': 'CSCD Core',
                '一区': 'Q1',
                '二区': 'Q2',
                '三区': 'Q3',
                '四区': 'Q4',
                '计算机视觉': 'Computer Vision',
                '自然语言处理': 'NLP',
                '人工智能': 'AI',
                '机器学习': 'Machine Learning',
                '深度学习': 'Deep Learning',
                '三维重建': '3D Reconstruction',
                '图像生成': 'Image Generation',
                '虚拟试衣': 'Virtual Try-on',
                '人机交互': 'HCI',
                '科学论文阅读增强': 'Paper Reading Enhancement',
                '可控服装生成': 'Controllable Garment Generation',
                '虚拟试穿': 'Virtual Try-on',
                '多模态学习': 'Multi-modal Learning',
                '中国风': 'Chinese-style',
                '中国画': 'Chinese Painting',
                '人机协同': 'Human-AI Collaboration',
                '设计辅助': 'Design Ideation',
                '多尺度目标检测': 'Multi-scale Object Detection',
                '计算机图形学': 'Computer Graphics',
                '参数化服装建模': 'Parametric Garment Modeling',
                '渲染到真实图像翻译': 'Render-to-Real Image Translation',
                '服装生成': 'Garment Generation',

                // Additional Database tags & directions
                '3D 服装': '3D Garment',
                '3D 环境': '3D Environment',
                '3D 虚拟试衣': '3D Virtual Try-on',
                'PDF 处理': 'PDF Processing',
                '临时词': 'Nonce Words',
                '交互式文档': 'Interactive Documents',
                '交互技术': 'Interaction Technology',
                '交叉注意力': 'Cross Attention',
                '人机协作': 'Human-AI Collaboration',
                '代理': 'Agent',
                '任意视角渲染': 'Any-view Rendering',
                '信息多样性': 'Information Diversity',
                '信息寻求': 'Information Seeking',
                '免训练': 'Training-free',
                '具身': 'Embodied',
                '卷积神经网络': 'Convolutional Neural Networks',
                '卷积网络': 'Convolutional Networks',
                '可控合成': 'Controllable Synthesis',
                '可控时尚生成': 'Controllable Fashion Generation',
                '可控生成': 'Controllable Generation',
                '回声室效应': 'Echo Chamber Effect',
                '图像合成': 'Image Synthesis',
                '图像操控': 'Image Manipulation',
                '图像编辑': 'Image Editing',
                '图形用户界面': 'GUI',
                '基于物理的渲染': 'Physically Based Rendering',
                '基础模型': 'Foundation Models',
                '多人虚拟试穿': 'Multi-person Virtual Try-on',
                '多模态引导': 'Multi-modal Guidance',
                '多模态扩散': 'Multi-modal Diffusion',
                '多视图': 'Multi-view',
                '多视图注意力': 'Multi-view Attention',
                '多视角': 'Multi-perspective',
                '多视角空间注意力': 'Multi-perspective Spatial Attention',
                '大语言模型': 'LLM',
                '大语言模型智能体': 'LLM Agent',
                '学术传播': 'Scholarly Communication',
                '学术合成': 'Academic Synthesis',
                '学术沟通': 'Scholarly Communication',
                '学术论文': 'Academic Papers',
                '定义': 'Definitions',
                '对照实验': 'User Study',
                '对话式搜索': 'Conversational Search',
                '属性级': 'Attribute-wise',
                '属性级条件控制': 'Attribute-wise Conditional Control',
                '工具包': 'Toolkit',
                '引用图': 'Citation Graph',
                '引用图谱': 'Citation Network',
                '意义构建': 'Sensemaking',
                '手先验': 'Hand Prior',
                '手部先验': 'Hand Prior',
                '手部姿态': 'Hand Pose',
                '手部遮挡': 'Hand Occlusion',
                '捕获': 'Capture',
                '掩码引导注意力': 'Mask-guided Attention',
                '播客': 'Podcast',
                '故事讲述': 'Storytelling',
                '数字时尚': 'Digital Fashion',
                '文档转音频': 'Document-to-Audio',
                '无需训练': 'Training-free',
                '时尚图像生成': 'Fashion Image Generation',
                '智能体': 'Agent',
                '服装融合': 'Garment Fusion',
                '服装重建': 'Garment Reconstruction',
                '材质外观': 'Material Appearance',
                '混合倡议': 'Mixed-initiative',
                '渲染到真实': 'Render-to-Real',
                '潜在扩散': 'Latent Diffusion',
                '潜在扩散模型': 'Latent Diffusion Models',
                '特征提取': 'Feature Extraction',
                '特征金字塔网络': 'Feature Pyramid Networks',
                '理解': 'Understanding',
                '生成式 AI': 'Generative AI',
                '生成式人工智能': 'Generative AI',
                '电子游戏': 'Video Games',
                '目标检测': 'Object Detection',
                '研究论文': 'Research Papers',
                '确认偏差': 'Confirmation Bias',
                '确认偏误': 'Confirmation Bias',
                '社交媒体讨论': 'Social Media Discussion',
                '科学文档': 'Scientific Documents',
                '科学论文': 'Scientific Papers',
                '笔记': 'Notes',
                '约束': 'Constraints',
                '纹理保持': 'Texture Preserving',
                '纹理迁移': 'Texture Transfer',
                '缝纫图案': 'Sewing Patterns',
                '虚拟试脱': 'Virtual Try-off',
                '虚拟试衣离线': 'Offline Virtual Try-on',
                '视觉对应': 'Visual Correspondence',
                '视觉对应关系': 'Visual Correspondence',
                '视觉语言模型': 'VLM',
                '视频游戏': 'Video Games',
                '计算机控制': 'Computer Control',
                '计算机控制代理': 'Computer Control Agent',
                '语义对应': 'Semantic Correspondence',
                '语义点': 'Semantic Points',
                '语言': 'Language',
                '身份保持': 'Identity Preserving',
                '野外图像': 'In-the-wild Images',
                '阅读': 'Reading',
                '阅读界面': 'Reading Interface',
                '饰品': 'Accessories',
                '高亮': 'Highlighting',
                '高保真': 'High-fidelity',
                '虚拟试穿生成': 'Virtual Try-on Generation',
                '文档阅读与高亮交互': 'Document Reading and Highlight Interaction',
                '材质生成': 'Material Generation',
                '多视图虚拟试衣': 'Multi-view Virtual Try-on',
                '人机协同研究叙事构建': 'Narrative Construction in Human-AI Collaboration',
                '科学文档处理': 'Scientific Document Processing',
                '具身智能': 'Embodied AI',
                '大语言模型搜索系统与信息多样性': 'LLM Search Systems & Information Diversity',
                '饰品虚拟试穿': 'Accessories Virtual Try-on',
                '基于扩散模型的虚拟试衣': 'Diffusion-based Virtual Try-on',
                '学术文献合成与理解': 'Academic Literature Synthesis & Understanding',
                '虚拟试脱与服装生成': 'Virtual Try-off & Garment Generation',
                '3D 虚拟试穿': '3D Virtual Try-on',
                '虚拟试穿与手部遮挡处理': 'Virtual Try-on with Hand Occlusion Handling',
                '3D 服装生成': '3D Garment Generation',
                '大语言模型辅助学术阅读': 'LLM-assisted Academic Reading',
                '学术阅读界面设计': 'Academic Reading Interface Design',
                'AI 辅助文档阅读设计': 'AI-assisted Document Reading Design'
            };
            return dict[val] || val;
        };
        
        const isMetaPending = (doc) => {
            if (!doc) return false;
            const noAbs = !doc.abstract && !doc.en_abstract;
            const noTags = !doc.tags || doc.tags.length === 0;
            const noType = !doc.paper_type;
            return noAbs && noTags && noType;
        };

        return { filteredDocuments, openChat, resumeDoc, deleteDoc, retagDoc, parseKeywords, tMetadata, t: translate, getLang, canOpenDoc, isMetaPending };
    }
};

// Image 3: Graph View
const GraphView = {
    template: `
        <div style="display:flex;height:100%;width:100%;overflow:hidden;">
            <div style="width:260px;flex-shrink:0;border-right:1px solid var(--header-border);overflow:auto;padding:12px;">
                <div style="font-size:13px;color:var(--text-muted);margin-bottom:8px;">{{ t('auto.lineage_pick') }}</div>
                <div v-for="doc in docs" :key="doc.id" @click="selectDoc(doc)"
                     :style="{padding:'8px',borderRadius:'8px',cursor:'pointer',marginBottom:'6px',background: selected && selected.id===doc.id ? 'var(--header-bg)' : 'transparent'}">
                    <div style="font-size:13px;font-weight:600;">{{ doc.zh_title || doc.title }}</div>
                    <div style="font-size:11px;color:var(--text-muted);">{{ doc.year || '' }} {{ doc.venue || '' }}</div>
                </div>
            </div>
            <div style="flex:1;overflow:auto;padding:18px;" v-if="lineage">
                <div class="lineage-hero-banner">
                    <div v-if="lineage.dossier && lineage.dossier.hero_figure" class="lineage-hero-bg" :style="{backgroundImage: 'url(\'' + lineage.dossier.hero_figure.url + '\')'}"></div>
                    <div class="lineage-hero-content">
                        <h3 style="margin:0 0 6px;">{{ lineage.document.zh_title || lineage.document.title }}</h3>
                        <div style="color:var(--text-muted);font-size:13px;margin-bottom:10px;">
                            {{ (lineage.document.authors||[]).join(', ') }}<span v-if="(lineage.document.authors||[]).length"> · </span>{{ lineage.document.year }}
                        </div>
                        <div style="display:flex;flex-wrap:wrap;gap:6px;">
                            <span v-if="lineage.document.venue" class="tag-badge" style="background:rgba(52,152,219,0.15);color:#3498db;">{{ lineage.document.venue }}</span>
                            <span v-if="lineage.document.ccf_partition" class="tag-badge" style="background:rgba(231,76,60,0.15);color:#e74c3c;">CCF {{ lineage.document.ccf_partition }}</span>
                        </div>
                    </div>
                </div>
                <div style="display:grid;grid-template-columns:minmax(260px,0.95fr) minmax(360px,1.15fr);gap:24px;">
                    <div>
                        <h4>{{ t('auto.lineage_related') }}</h4>
                        <div v-if="!(lineage.related||[]).length" style="color:var(--text-muted);">{{ t('auto.lineage_empty') }}</div>
                        <div v-for="r in lineage.related" :key="'rel'+r.id" class="lineage-related-card" :style="r.hero_url ? {backgroundImage: 'url(\'' + r.hero_url + '\')'} : {}" @click="selectById(r.id)">
                            <div class="lineage-related-card-overlay"></div>
                            <div class="lineage-related-card-content">
                                <div class="lineage-related-title">{{ r.zh_title || r.title }}</div>
                                <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:5px;">
                                    <span v-for="reason in r.reasons" :key="reason" class="tag-badge" :style="reasonBadgeStyle(reason)">{{ formatReasons([reason]) }}</span>
                                </div>
                            </div>
                        </div>
                        <h4>{{ t('auto.lineage_refs') }}</h4>
                        <div v-for="(r,i) in lineage.references" :key="'ref'+i" style="padding:8px 0;border-bottom:1px solid var(--header-border);font-size:13px;">
                            <div>{{ r.title }} <span v-if="r.ccf" class="tag-badge" style="background:rgba(231,76,60,0.15);color:#e74c3c;font-size:11px;padding:2px 8px;">CCF {{ r.ccf }}</span></div>
                            <div style="color:var(--text-muted);font-size:12px;margin-top:3px;">
                                {{ r.year }} <span v-if="r.in_library">· {{ t('auto.lineage_in_lib') }}</span>
                            </div>
                        </div>
                    </div>
                    <div>
                        <h4 style="margin-bottom:14px;">{{ t('auto.lineage_dossier') }}</h4>
                        <h5 style="margin:0 0 8px;font-size:13px;color:var(--text-muted);font-weight:600;">{{ t('auto.lineage_ai_abs') }}</h5>
                        <div class="markdown-body" style="margin-bottom:20px;" v-html="renderMarkdown((lineage.dossier && lineage.dossier.ai_abstract) || lineage.document.abstract || t('auto.lineage_no_abs'))"></div>
                        <div v-if="lineage.dossier && lineage.dossier.arch_figure && (!lineage.dossier.hero_figure || lineage.dossier.arch_figure.filename !== lineage.dossier.hero_figure.filename)" style="margin-bottom:18px;">
                            <div style="font-size:12px;color:var(--text-muted);margin-bottom:6px;">{{ t('auto.lineage_arch_fig') }}</div>
                            <div class="lineage-fig-frame"><img :src="lineage.dossier.arch_figure.url"></div>
                        </div>
                        <h4>{{ t('auto.lineage_qa') }}</h4>
                        <div v-if="!(lineage.dossier && lineage.dossier.qa && lineage.dossier.qa.length)" style="color:var(--text-muted);">{{ t('auto.lineage_no_qa') }}</div>
                        <div v-for="(item,i) in ((lineage.dossier && lineage.dossier.qa) || [])" :key="'qa'+i" style="margin-bottom:14px;padding:12px;border:1px solid var(--header-border);border-radius:10px;background:var(--card-bg);">
                            <div style="font-size:13px;font-weight:600;margin-bottom:6px;">{{ item.title }}</div>
                            <div v-if="item.question" style="font-size:12px;color:var(--text-muted);margin-bottom:8px;white-space:pre-wrap;">{{ item.question }}</div>
                            <div class="markdown-body" style="font-size:13px;line-height:1.65;max-height:280px;overflow:auto;" v-html="renderMarkdown(item.answer)"></div>
                        </div>
                    </div>
                </div>
            </div>
            <div v-else style="flex:1;display:flex;align-items:center;justify-content:center;color:var(--text-muted);">{{ t('auto.lineage_pick') }}</div>
        </div>
    `,
    setup() {
        const docs = ref([]);
        const selected = ref(null);
        const lineage = ref(null);
        const loadDocs = async () => {
            const res = await fetch('/api/library/documents');
            docs.value = await res.json();
        };
        const selectDoc = async (doc) => {
            selected.value = doc;
            const res = await fetch('/api/library/documents/' + doc.id + '/lineage');
            lineage.value = await res.json();
        };
        const selectById = (id) => {
            const d = docs.value.find(x => x.id === id);
            if (d) selectDoc(d);
        };
        const formatReasons = (reasons) => {
            const map = {
                shared_keywords: translate('auto.reason_keywords'),
                same_field: translate('auto.reason_field'),
                same_author: translate('auto.reason_author'),
            };
            return (reasons || []).map(r => map[r] || r).join(' · ');
        };
        const REASON_COLORS = {
            same_author: { background: 'rgba(155,89,182,0.15)', color: '#9b59b6' },
            shared_keywords: { background: 'rgba(46,204,113,0.15)', color: '#2ecc71' },
            same_field: { background: 'rgba(52,152,219,0.15)', color: '#3498db' },
        };
        const reasonBadgeStyle = (reason) => {
            const c = REASON_COLORS[reason] || { background: 'rgba(255,255,255,0.08)', color: 'var(--text-muted)' };
            return { background: c.background, color: c.color, fontSize: '11px', padding: '3px 9px' };
        };
        onMounted(loadDocs);
        return { docs, selected, lineage, selectDoc, selectById, formatReasons, reasonBadgeStyle, renderMarkdown, t: translate };
    }
};

const SearchView = {
    template: `
        <div style="display:flex; height: 100%; width: 100%; overflow: hidden;">
            <!-- Left Pane: Search Results -->
            <div style="flex: 1; padding: 20px; overflow-y: auto; border-right: 2px solid var(--header-border);">
                <div v-if="loading" style="text-align: center; color: var(--text-muted); margin-top: 50px;">
                    <div style="margin-bottom: 10px; font-size: 16px;">AI 正在思考并检索知识库，请稍候...</div>
                    <div style="font-size: 13px; opacity: 0.7;">（如果文献较多或需要深入阅读，可能需要10-20秒）</div>
                </div>
                <div v-else-if="results.length > 0">
                    <div style="font-size: 14px; color: var(--text-muted); margin-bottom: 15px;">共找到 {{ results.length }} 篇相关文献：</div>
                    <div class="doc-list-item" v-for="doc in results" :key="doc.id" @click="openChat(doc.original_filename, doc)">
                        <div class="doc-title">
                            {{ doc.title }}
                            <div v-if="doc.zh_title" style="font-size: 14px; color: var(--text-muted); font-weight: normal; margin-top: 5px;">{{ doc.zh_title }}</div>
                        </div>
                        <div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; align-items: center;">
                            <span class="tag-badge" style="background: var(--header-bg); border: 1px solid var(--primary-accent); color: var(--primary-accent);" v-if="doc.venue && doc.venue !== 'Unknown'">{{ doc.venue }}</span>
                            <span class="tag-badge" style="background: rgba(148, 163, 184, 0.2); color: #cbd5e1;" v-if="doc.year">{{ doc.year }}</span>
                            <span class="tag-badge" style="background: rgba(46, 204, 113, 0.2); color: #2ecc71;" v-if="doc.paper_type">{{ doc.paper_type }}</span>
                            <span class="tag-badge" style="background: rgba(231, 76, 60, 0.2); color: #e74c3c;" v-if="doc.ccf_partition">CCF {{ doc.ccf_partition }}</span>
                            <span class="tag-badge" style="background: rgba(155, 89, 182, 0.2); color: #9b59b6;" v-if="doc.jcr_partition">JCR {{ doc.jcr_partition }}</span>
                            <span class="tag-badge" style="background: rgba(241, 196, 15, 0.2); color: #f1c40f;" v-if="doc.core_type">{{ doc.core_type }}</span>
                            <span class="tag-badge" style="background: rgba(52, 152, 219, 0.2); color: #3498db;" v-if="doc.research_field">{{ doc.research_field }}</span>
                            <span class="tag-badge" style="background: rgba(52, 152, 219, 0.1); color: #2980b9; border: 1px solid rgba(52, 152, 219, 0.3);" v-if="doc.research_direction">{{ doc.research_direction }}</span>
                        </div>
                        <div class="doc-abstract" style="margin-top: 10px;">{{ doc.abstract || '该文献暂无摘要信息。' }}</div>
                        <div class="doc-tags" style="margin-top: 8px;">
                            <span class="tag-badge" v-for="tag in doc.tags" :key="tag.id">{{ tag.name }}</span>
                        </div>
                    </div>
                </div>
                <div v-else style="text-align: center; color: var(--text-muted); margin-top: 50px;">
                    请在右侧输入您的研究需求，AI将为您精准推荐相关文献。
                </div>
            </div>

            <!-- Right Pane: Chat -->
            <div style="width: 450px; display: flex; flex-direction: column; background: var(--card-bg);">
                <div style="flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 15px;" id="search-chat-container">
                    <div v-for="(msg, i) in chatHistory" :key="i" :style="{ alignSelf: msg.role === 'user' ? 'flex-end' : 'flex-start', maxWidth: '85%' }">
                        <div :style="{
                            background: msg.role === 'user' ? 'var(--primary-accent)' : 'var(--input-bg)',
                            color: msg.role === 'user' ? '#fff' : 'var(--text-color)',
                            padding: '12px 16px',
                            borderRadius: msg.role === 'user' ? '12px 12px 0 12px' : '12px 12px 12px 0',
                            border: msg.role === 'user' ? 'none' : '1px solid var(--header-border)',
                            lineHeight: '1.6',
                            fontSize: '14px',
                            whiteSpace: 'pre-wrap'
                        }">{{ msg.content }}</div>
                    </div>
                </div>
                <div style="padding: 15px; border-top: 1px solid var(--header-border); background: var(--bg-color);">
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <input type="text" v-model="userInput" @keyup.enter="sendMessage" placeholder="例如：我想找关于大语言模型的最新综述..." :disabled="loading"
                            style="flex: 1; background: var(--input-bg); border: 1px solid var(--header-border); color: var(--text-color); padding: 12px 15px; border-radius: 24px; outline: none; font-size: 14px;">
                        <button @click="sendMessage" :disabled="loading || !userInput.trim()" 
                            style="background: var(--primary-accent); border: none; color: white; width: 44px; height: 44px; border-radius: 50%; cursor: pointer; display: flex; align-items: center; justify-content: center; opacity: (loading || !userInput.trim()) ? 0.5 : 1;">
                            <svg v-if="!loading" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                            <span v-else style="font-size: 12px;">...</span>
                        </button>
                    </div>
                </div>
            </div>
        </div>
    `,
    setup() {
        const userInput = ref('');
        const chatHistory = ref([
            { role: 'assistant', content: getLang() === 'en' 
                ? 'Hello! I am your academic literature assistant. Tell me your research direction or what papers you are looking for, and I will search your knowledge base for precise recommendations.'
                : '您好！我是您的学术文献助手。您可以告诉我您正在研究什么方向，或者想找什么特定的论文，我会从您的知识库中为您精准检索和推荐。'
            }
        ]);
        const results = ref([]);
        const loading = ref(false);

        const scrollToBottom = () => {
            setTimeout(() => {
                const container = document.getElementById('search-chat-container');
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            }, 100);
        };

        const sendMessage = async () => {
            const text = userInput.value.trim();
            if (!text || loading.value) return;

            chatHistory.value.push({ role: 'user', content: text });
            userInput.value = '';
            loading.value = true;
            scrollToBottom();

            try {
                // Keep only a few previous turns to save tokens
                const historyToSend = chatHistory.value.slice(-6, -1).map(m => ({ role: m.role, content: m.content }));
                
                const res = await fetch('/api/library/universal_search', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text, chat_history: historyToSend, lang: getLang() })
                });

                if (!res.ok) throw new Error("API Request Failed");
                
                const data = await res.json();
                chatHistory.value.push({ role: 'assistant', content: data.reply });
                results.value = data.documents || [];
            } catch (e) {
                console.error(e);
                chatHistory.value.push({ role: 'assistant', content: getLang() === 'en' ? 'Sorry, a network or server error occurred. Please try again later.' : '抱歉，检索过程中出现了网络或服务器错误，请稍后再试。' });
            } finally {
                loading.value = false;
                scrollToBottom();
            }
        };

        const openChat = (filename, doc) => {
            if (window.openReaderTab) window.openReaderTab(filename, doc);
            else window.location.href = '/chat/' + encodeURIComponent((filename || '').replace(/\.pdf$/i, ''));
        };

        return { userInput, chatHistory, results, loading, sendMessage, openChat };
    }
};

// --- Prompt Management View ---
const PromptsView = {
    template: `
        <div class="prompts-layout">
            <div class="prompts-sidebar">
                <div class="prompts-sidebar-header">
                    <span class="prompts-sidebar-title">{{ t('prompt.saved_list') }}</span>
                    <button class="prompts-add-btn" @click="createPrompt" title="New">+</button>
                </div>
                <div class="prompts-list">
                    <div v-if="promptNames.length === 0" style="padding: 20px; text-align: center; color: var(--text-muted); font-size: 13px;">
                        {{ t('prompt.no_prompts') }}
                    </div>
                    <div v-for="item in promptNames" :key="item.id"
                         class="prompts-item" :class="{active: currentPrompt === item.id}"
                         @click="loadPrompt(item.id)">
                        {{ item.name }}
                    </div>
                </div>
            </div>
            <div class="prompts-editor" v-if="currentPrompt">
                <div class="prompts-editor-header">
                    <div class="prompts-editor-title">{{ t('prompt.editing') }} <strong>{{ currentPromptDisplayName }}</strong></div>
                    <div style="display:flex;gap:10px;">
                        <button class="prompts-btn-danger" @click="deletePrompt">{{ t('prompt.delete') }}</button>
                        <button class="prompts-btn-save" @click="savePrompt">{{ t('prompt.save') }}</button>
                    </div>
                </div>
                <div class="prompts-segments">
                    <div v-for="(seg, i) in segments" :key="i" class="prompts-segment-card">
                        <div class="prompts-segment-head">
                            <input class="prompts-segment-title-input" v-model="seg.displayTitle" @input="seg.title = '### ' + seg.displayTitle" />
                            <button class="prompts-segment-del" @click="segments.splice(i, 1)">{{ t('prompt.segment_delete') }}</button>
                        </div>
                        <textarea class="prompts-segment-text" v-model="seg.text" rows="4"></textarea>
                    </div>
                    <button class="prompts-add-segment-btn" @click="addSegment">{{ t('prompt.add_segment') }}</button>
                </div>
            </div>
            <div class="prompts-editor prompts-empty-state" v-else>
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.3;margin-bottom:12px;">
                    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/>
                </svg>
                <div style="color: var(--text-muted);">{{ t('prompt.empty_hint') }}</div>
            </div>
        </div>
    `,
    setup() {
        const promptNames = ref([]);
        const currentPrompt = ref('');
        const segments = ref([]);
        let fileHeader = '';
        const ORDER = ['一','二','三','四','五','六','七','八','九','十','十一','十二'];

        const currentPromptDisplayName = computed(() => {
            const found = promptNames.value.find(p => p.id === currentPrompt.value);
            return found ? found.name : currentPrompt.value;
        });

        const loadList = async () => {
            const res = await fetch('/api/prompts?lang=' + currentLang.value);
            const data = await res.json();
            promptNames.value = data.prompts || [];
        };

        const parseSegments = (rawText) => {
            const lines = rawText.split('\n');
            const segs = [];
            let curTitle = '', curLines = [];
            fileHeader = '';
            for (const line of lines) {
                if (line.trim().startsWith('## ') && segs.length === 0 && curTitle === '') {
                    fileHeader = line;
                    continue;
                }
                if (line.trim().startsWith('### ')) {
                    if (curLines.length > 0 || curTitle !== '') {
                        segs.push({ title: curTitle, displayTitle: curTitle.replace(/^#+\s*/, ''), text: curLines.join('\n').trim() });
                    }
                    curTitle = line.trim();
                    curLines = [];
                } else {
                    curLines.push(line);
                }
            }
            if (curTitle !== '' || curLines.join('').trim() !== '') {
                const t = curTitle === '' ? '### Section 1' : curTitle;
                segs.push({ title: t, displayTitle: t.replace(/^#+\s*/, ''), text: curLines.join('\n').trim() });
            }
            if (segs.length === 0 && fileHeader === '') {
                segs.push({ title: '### Section 1', displayTitle: 'Section 1', text: rawText.trim() });
            }
            segments.value = segs;
        };

        const loadPrompt = async (id) => {
            currentPrompt.value = id;
            const res = await fetch('/api/prompts/' + encodeURIComponent(id) + '?lang=' + currentLang.value);
            const data = await res.json();
            parseSegments(data.content || '');
        };

        const createPrompt = async () => {
            const name = window.prompt(translate('prompt.new_dialog'));
            if (!name) return;
            const initContent = '## ' + name + '\n### Section 1\n';
            const res = await fetch('/api/prompts/' + encodeURIComponent(name) + '?lang=' + currentLang.value, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({content: initContent})
            });
            if (!res.ok) {
                alert(translate('prompt.save_fail') || ('HTTP ' + res.status));
                return;
            }
            await loadList();
            loadPrompt(name);
        };

        const reconstructMarkdown = () => {
            const lines = [];
            if (fileHeader) lines.push(fileHeader);
            segments.value.forEach(seg => {
                lines.push(seg.title);
                if (seg.text.trim()) lines.push(seg.text);
            });
            return lines.join('\n');
        };

        const savePrompt = async () => {
            if (!currentPrompt.value) return;
            const content = reconstructMarkdown();
            const res = await fetch('/api/prompts/' + encodeURIComponent(currentPrompt.value) + '?lang=' + currentLang.value, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({content: content})
            });
            if (!res.ok) {
                alert(translate('prompt.save_fail') || ('HTTP ' + res.status));
                return;
            }
            alert(translate('prompt.save_ok'));
            loadList();
        };

        const deletePrompt = async () => {
            if (!currentPrompt.value) return;
            if (!confirm(translate('prompt.confirm_delete', {name: currentPromptDisplayName.value}))) return;
            await fetch('/api/prompts/' + encodeURIComponent(currentPrompt.value), {method: 'DELETE'});
            currentPrompt.value = '';
            segments.value = [];
            loadList();
        };

        const addSegment = () => {
            const title = '### Section ' + (segments.value.length + 1);
            segments.value.push({ title, displayTitle: title.replace(/^#+\s*/, ''), text: '' });
        };

        watch(currentLang, () => {
            loadList();
            if (currentPrompt.value) {
                loadPrompt(currentPrompt.value);
            }
        });

        onMounted(async () => {
            await loadList();
            if (promptNames.value.length > 0) {
                const def = promptNames.value.find(p => (p.id || '').includes('提示词汇总') || (p.id || '').includes('人工智能')) || promptNames.value[0];
                loadPrompt(def.id || def);
            }
        });

        return { promptNames, currentPrompt, segments, loadList, loadPrompt, createPrompt, savePrompt, deletePrompt, addSegment, t: translate };
    }
};

// --- Router Setup ---
const routes = [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', component: DashboardView },
    { 
        path: '/auto', 
        component: AutoLayout,
        redirect: '/auto/list',
        children: [
            { path: 'list', component: ListView },
            { path: 'graph', component: GraphView },
            { path: 'search', component: SearchView }
        ]
    },
    { path: '/prompts', component: PromptsView }
];

const router = createRouter({
    history: createWebHashHistory(),
    routes,
});

// --- Main App ---
const app = createApp({
    setup() {
        const router = useRouter();
        const route = useRoute();
        const currentTheme = ref(localStorage.getItem('theme') || 'antigravity');
        const currentMainTab = ref('dashboard');
        const lang = currentLang;

        // Refresh data-i18n elements in the DOM
        const refreshI18nDom = () => {
            document.querySelectorAll('[data-i18n]').forEach(el => {
                el.textContent = translate(el.getAttribute('data-i18n'));
            });
            document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
                el.placeholder = translate(el.getAttribute('data-i18n-placeholder'));
            });
        };

        onMounted(() => {
            document.body.setAttribute('data-theme', currentTheme.value);
            if(route.path.startsWith('/auto')) {
                currentMainTab.value = 'auto';
            } else if(route.path.startsWith('/prompts')) {
                currentMainTab.value = 'prompts';
            }
            refreshI18nDom();
            // Listen for lang changes from any source
            window.addEventListener('lang-changed', (e) => {
                lang.value = e.detail.lang;
                refreshI18nDom();
            });

            // Restore reader tabs from a previous session (all start hibernated except
            // the one that was active, so re-opening the app doesn't reload a pile of PDFs).
            try {
                const raw = localStorage.getItem(READER_STORAGE_KEY);
                if (raw) {
                    const data = JSON.parse(raw) || {};
                    (data.tabs || []).forEach(t => {
                        if (!t || !t.book) return;
                        readerTabs.push(reactive({
                            book: t.book, title: t.title || t.book,
                            field: t.field || '', direction: t.direction || '',
                            groupId: t.groupId || '',
                            hibernated: t.book !== data.active,
                            lastActive: Date.now(),
                        }));
                    });
                    if (data.active && readerTabs.some(x => x.book === data.active)) {
                        activeReaderBook.value = data.active;
                    }
                }
            } catch (e) { /* ignore corrupt/old storage */ }

            hibernateTimer = setInterval(() => {
                const now = Date.now();
                readerTabs.forEach(t => {
                    if (t.book !== activeReaderBook.value && !t.hibernated && (now - t.lastActive) > HIBERNATE_MS) {
                        t.hibernated = true;
                    }
                });
            }, 60 * 1000);

            document.addEventListener('click', hideTabContextMenu);
            document.addEventListener('contextmenu', (e) => {
                if (!e.target.closest || !e.target.closest('.reader-tab')) hideTabContextMenu();
            });
        });

        onUnmounted(() => {
            if (hibernateTimer) clearInterval(hibernateTimer);
        });
        
        watch(() => route.path, (newPath) => {
            if(newPath.startsWith('/auto')) {
                currentMainTab.value = 'auto';
            } else if (newPath.startsWith('/dashboard')) {
                currentMainTab.value = 'dashboard';
            } else if (newPath.startsWith('/prompts')) {
                currentMainTab.value = 'prompts';
            }
        });

        const changeTheme = () => {
            document.body.setAttribute('data-theme', currentTheme.value);
            localStorage.setItem('theme', currentTheme.value);
        };

        const isLightTheme = computed(() => {
            const t = currentTheme.value || '';
            return t.includes('light') || t === 'cyan-light';
        });

        const toggleDarkLight = () => {
            const lightThemes = ['cyan-light'];
            if (lightThemes.includes(currentTheme.value) || isLightTheme.value) {
                currentTheme.value = localStorage.getItem('preferred_dark') || 'antigravity';
            } else {
                localStorage.setItem('preferred_dark', currentTheme.value);
                currentTheme.value = localStorage.getItem('preferred_light') || 'cyan-light';
            }
            changeTheme();
        };

        const switchMainTab = (tab) => {
            currentMainTab.value = tab;
            readerWorkspaceVisible.value = false;
            if (tab === 'dashboard') {
                router.push('/dashboard');
            } else if (tab === 'prompts') {
                router.push('/prompts');
            } else {
                router.push('/auto/list');
            }
        };

        const switchLang = (newLang) => {
            setLang(newLang);
            lang.value = newLang;
            refreshI18nDom();
        };
        
        window.addParseKeyInput = (val) => {
            const container = document.getElementById('parse_api_key_list');
            if (!container) return;
            const row = document.createElement('div');
            row.className = 'key-row';
            row.innerHTML = `
                <input type="text" class="parse-key-input" placeholder="sk-..." value="${val}">
                <button class="remove-key-btn" onclick="this.parentElement.remove()" title="移除此秘钥">&times;</button>
            `;
            container.appendChild(row);
        };

        const openSettings = async () => {
            document.getElementById('settingsModal').classList.add('active');
            try {
                const res = await fetch('/api/config');
                const cfg = await res.json();
                document.getElementById('parse_api_url').value = cfg.parse_api_url || 'https://opencode.ai/zen/go/v1';
                
                const keyList = document.getElementById('parse_api_key_list');
                if (keyList) {
                    keyList.innerHTML = '';
                    let parseKeys = cfg.parse_api_key || [];
                    if (typeof parseKeys === 'string') parseKeys = parseKeys.split(',');
                    if (parseKeys.length === 0) parseKeys = [''];
                    parseKeys.forEach(k => window.addParseKeyInput(k.trim()));
                }

                document.getElementById('parse_model').value = cfg.parse_model || 'qwen3.7-plus';
                const textEl = document.getElementById('text_model');
                if (textEl) {
                    textEl.value = cfg.translate_model || cfg.chat_model || cfg.parse_model || 'qwen3.7-plus';
                }
            } catch (e) {
                console.error("加载配置失败", e);
            }
        };

        const closeSettings = () => {
            document.getElementById('settingsModal').classList.remove('active');
        };

        // ---- Reader Workspace: browser-like tabbed PDF reading with grouping + hibernation ----
        const READER_STORAGE_KEY = 'paperfect_reader_tabs_v1';
        const HIBERNATE_MS = 10 * 60 * 1000; // idle 10min in the background -> discard iframe
        const GROUP_COLORS = ['#60a5fa', '#34d399', '#f59e0b', '#f472b6', '#a78bfa', '#38bdf8', '#fb7185', '#4ade80'];

        const readerTabs = reactive([]);
        const activeReaderBook = ref('');
        const readerWorkspaceVisible = ref(false);
        const smartGroupOn = ref(false);
        let hibernateTimer = null;

        const persistReaderTabs = () => {
            try {
                localStorage.setItem(READER_STORAGE_KEY, JSON.stringify({
                    tabs: readerTabs.map(t => ({ book: t.book, title: t.title, field: t.field, direction: t.direction, groupId: t.groupId || '' })),
                    active: activeReaderBook.value,
                }));
            } catch (e) { /* ignore quota errors */ }
        };

        const openReaderTab = (filename, doc) => {
            const book = (filename || '').replace(/\.pdf$/i, '');
            if (!book) return;
            let tab = readerTabs.find(x => x.book === book);
            if (!tab) {
                tab = reactive({
                    book,
                    title: (doc && (doc.zh_title || doc.title)) || book,
                    field: (doc && doc.research_field) || '',
                    direction: (doc && doc.research_direction) || '',
                    groupId: '',
                    hibernated: false,
                    lastActive: Date.now(),
                });
                readerTabs.push(tab);
            } else {
                tab.hibernated = false;
                tab.lastActive = Date.now();
            }
            activeReaderBook.value = book;
            readerWorkspaceVisible.value = true;
            _expandGroupFor(tab);
            persistReaderTabs();
        };
        window.openReaderTab = openReaderTab;

        const switchReaderTab = (book) => {
            const tab = readerTabs.find(x => x.book === book);
            if (!tab) return;
            tab.hibernated = false;
            tab.lastActive = Date.now();
            activeReaderBook.value = book;
            readerWorkspaceVisible.value = true;
            _expandGroupFor(tab);
            persistReaderTabs();
        };

        const closeReaderTab = (book) => {
            const idx = readerTabs.findIndex(x => x.book === book);
            if (idx === -1) return;
            readerTabs.splice(idx, 1);
            if (activeReaderBook.value === book) {
                if (readerTabs.length > 0) {
                    const next = readerTabs[Math.max(0, idx - 1)] || readerTabs[0];
                    next.hibernated = false;
                    next.lastActive = Date.now();
                    activeReaderBook.value = next.book;
                } else {
                    activeReaderBook.value = '';
                    readerWorkspaceVisible.value = false;
                }
            }
            persistReaderTabs();
        };

        const closeAllReaderTabs = () => {
            readerTabs.splice(0, readerTabs.length);
            activeReaderBook.value = '';
            readerWorkspaceVisible.value = false;
            persistReaderTabs();
        };

        const showLibraryFromReader = () => {
            readerWorkspaceVisible.value = false;
        };

        const wakeReaderTab = (book) => {
            const tab = readerTabs.find(x => x.book === book);
            if (!tab) return;
            tab.hibernated = false;
            tab.lastActive = Date.now();
            persistReaderTabs();
        };

        const readerFrameSrc = (tab) => `/chat/${encodeURIComponent(tab.book)}?embed=1`;

        const toggleSmartGroup = () => { smartGroupOn.value = !smartGroupOn.value; };

        const _hashColor = (key) => {
            let h = 0;
            const s = key || 'default';
            for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
            return GROUP_COLORS[h % GROUP_COLORS.length];
        };

        // A tab's color is keyed by its manual drag-merge group first (so grouped
        // tabs always share one color no matter what field they belong to),
        // falling back to the parsed (non-JSON) research field otherwise.
        const groupColor = (tab) => _hashColor(tab && (tab.groupId || parseBilingualLabel(tab.field)));

        // Manual drag-merge grouping: dragging tab A onto tab B assigns both the
        // same groupId and moves A next to B. Rendered as contiguous same-color tabs
        // with a connecting bar (no text separator needed). Only active while smart
        // grouping is off, since smart grouping owns the tab order by itself.
        const manualGroupedReaderTabs = computed(() => {
            return readerTabs.map((t, idx) => {
                const prev = readerTabs[idx - 1];
                const next = readerTabs[idx + 1];
                const inGroup = !!t.groupId;
                return {
                    type: 'tab',
                    tab: t,
                    manualGroup: inGroup,
                    groupStart: inGroup && (!prev || prev.groupId !== t.groupId),
                    groupEnd: inGroup && (!next || next.groupId !== t.groupId),
                };
            });
        });

        // Smart grouping clusters open tabs by discipline (research_field) only —
        // one coarse bucket per field, not sub-split by direction, so it actually
        // consolidates instead of fragmenting into many tiny groups. Each bucket is
        // collapsible: collapsed groups shrink down to a small chip (saving space
        // for papers you're not looking at right now); the group holding the active
        // tab expands by default so you never lose sight of what you're reading.
        const groupCollapse = reactive({});

        const _fieldKeyFor = (tab) => parseBilingualLabel(tab && tab.field) || translate('reader.uncategorized') || '未分类';

        // Whenever a tab becomes active (opened or clicked), make sure its group
        // isn't sitting collapsed — you should always be able to see what you're reading.
        const _expandGroupFor = (tab) => {
            const key = _fieldKeyFor(tab);
            if (groupCollapse[key]) delete groupCollapse[key];
        };

        const toggleGroupCollapse = (key) => {
            const hasActive = readerTabs.some(t => _fieldKeyFor(t) === key && t.book === activeReaderBook.value);
            const effective = key in groupCollapse ? groupCollapse[key] : !hasActive;
            groupCollapse[key] = !effective;
        };

        const groupedReaderTabs = computed(() => {
            if (!smartGroupOn.value || readerTabs.length === 0) {
                return manualGroupedReaderTabs.value;
            }
            const buckets = new Map();
            readerTabs.forEach(t => {
                const key = _fieldKeyFor(t);
                if (!buckets.has(key)) buckets.set(key, []);
                buckets.get(key).push(t);
            });
            const keys = Array.from(buckets.keys()).sort((a, b) => a.localeCompare(b));
            const out = [];
            keys.forEach(key => {
                const members = buckets.get(key);
                const hasActive = members.some(t => t.book === activeReaderBook.value);
                const collapsed = key in groupCollapse ? groupCollapse[key] : !hasActive;
                out.push({ type: 'chip', key, label: key, color: _hashColor(key), count: members.length, collapsed, hasActive });
                if (!collapsed) {
                    members.forEach(t => out.push({ type: 'tab', tab: t, manualGroup: false, groupStart: false, groupEnd: false }));
                }
            });
            return out;
        });

        // ---- Tab drag-and-drop reordering (disabled while smart-group auto-sorts tabs) ----
        const draggingBook = ref('');
        let dragSrcBook = null;

        const onTabDragStart = (e, book) => {
            dragSrcBook = book;
            draggingBook.value = book;
            try {
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', book);
            } catch (err) { /* ignore */ }
        };

        const onTabDragOver = (e, _book) => {
            if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
        };

        let groupSeq = 0;
        const newGroupId = () => 'g' + Date.now() + '_' + (groupSeq++);

        // Dropping near the left/right edge of a tab just reorders (browser-like).
        // Dropping on the middle ~44% of a tab merges src+target into one manual
        // group (both take the same groupId, colored dot, and end up adjacent).
        const onTabDrop = (e, targetBook) => {
            const srcBook = dragSrcBook || (e.dataTransfer && e.dataTransfer.getData('text/plain'));
            dragSrcBook = null;
            draggingBook.value = '';
            if (!srcBook || srcBook === targetBook) return;
            const srcIdx = readerTabs.findIndex(t => t.book === srcBook);
            const tgtIdx = readerTabs.findIndex(t => t.book === targetBook);
            if (srcIdx === -1 || tgtIdx === -1) return;

            let mergeZone = false;
            let before = tgtIdx > srcIdx ? false : true;
            try {
                const rect = e.currentTarget.getBoundingClientRect();
                const relX = (e.clientX - rect.left) / rect.width;
                mergeZone = relX > 0.28 && relX < 0.72;
                before = relX <= 0.28;
            } catch (err) { /* keep index-based fallback above */ }

            const srcTab = readerTabs[srcIdx];
            const tgtTab = readerTabs[tgtIdx];

            if (mergeZone) {
                const gid = tgtTab.groupId || srcTab.groupId || newGroupId();
                readerTabs.forEach(t => { if (t.groupId && t.groupId === srcTab.groupId) t.groupId = gid; });
                tgtTab.groupId = gid;
                const [moved] = readerTabs.splice(srcIdx, 1);
                moved.groupId = gid;
                const newTgtIdx = readerTabs.findIndex(t => t.book === targetBook);
                readerTabs.splice(newTgtIdx + 1, 0, moved);
            } else {
                const [moved] = readerTabs.splice(srcIdx, 1);
                let insertAt = readerTabs.findIndex(t => t.book === targetBook);
                if (!before) insertAt += 1;
                readerTabs.splice(insertAt, 0, moved);
                if (moved.groupId) {
                    const idx2 = readerTabs.indexOf(moved);
                    const prevT = readerTabs[idx2 - 1];
                    const nextT = readerTabs[idx2 + 1];
                    const stillAdjacent = (prevT && prevT.groupId === moved.groupId) || (nextT && nextT.groupId === moved.groupId);
                    if (!stillAdjacent) moved.groupId = '';
                }
            }
            persistReaderTabs();
        };

        const onTabDragEnd = () => {
            dragSrcBook = null;
            draggingBook.value = '';
        };

        // ---- Tab right-click context menu ----
        const contextMenuTargetBook = ref('');

        const hideTabContextMenu = () => {
            const menu = document.getElementById('readerTabContextMenu');
            if (menu) menu.style.display = 'none';
        };

        const showTabContextMenu = (e, book) => {
            contextMenuTargetBook.value = book;
            const menu = document.getElementById('readerTabContextMenu');
            if (!menu) return;
            menu.style.display = 'block';
            const x = Math.min(e.clientX, window.innerWidth - 180);
            const y = Math.min(e.clientY, window.innerHeight - 160);
            menu.style.left = x + 'px';
            menu.style.top = y + 'px';
        };

        const ctxCloseTab = () => {
            const book = contextMenuTargetBook.value;
            hideTabContextMenu();
            if (book) closeReaderTab(book);
        };

        const ctxCloseOthers = () => {
            const keep = contextMenuTargetBook.value;
            hideTabContextMenu();
            if (!keep) return;
            for (let i = readerTabs.length - 1; i >= 0; i--) {
                if (readerTabs[i].book !== keep) readerTabs.splice(i, 1);
            }
            const tab = readerTabs.find(t => t.book === keep);
            if (tab) { tab.hibernated = false; tab.lastActive = Date.now(); }
            activeReaderBook.value = keep;
            readerWorkspaceVisible.value = true;
            persistReaderTabs();
        };

        const ctxCloseRight = () => {
            const book = contextMenuTargetBook.value;
            hideTabContextMenu();
            const idx = readerTabs.findIndex(t => t.book === book);
            if (idx === -1) return;
            const activeWasRemoved = readerTabs.slice(idx + 1).some(t => t.book === activeReaderBook.value);
            readerTabs.splice(idx + 1);
            if (activeWasRemoved) {
                const tab = readerTabs[idx];
                if (tab) { tab.hibernated = false; tab.lastActive = Date.now(); }
                activeReaderBook.value = book;
            }
            persistReaderTabs();
        };

        const ctxCloseAllFromMenu = () => {
            hideTabContextMenu();
            closeAllReaderTabs();
        };

        const contextMenuTargetHasGroup = computed(() => {
            const tab = readerTabs.find(t => t.book === contextMenuTargetBook.value);
            return !!(tab && tab.groupId);
        });

        const ctxUngroup = () => {
            const book = contextMenuTargetBook.value;
            hideTabContextMenu();
            const tab = readerTabs.find(t => t.book === book);
            if (tab) tab.groupId = '';
            persistReaderTabs();
        };

        // ---- Toolbox: run PDF tools on any document(s) without opening the reader ----
        let toolboxDocs = [];
        const toolboxSelected = new Set();

        const renderToolboxDocs = (filterText) => {
            const box = document.getElementById('toolbox-doc-list');
            if (!box) return;
            const q = (filterText || '').trim().toLowerCase();
            const filtered = toolboxDocs.filter(d => {
                if (!q) return true;
                const hay = `${d.title || ''} ${d.zh_title || ''} ${d.original_filename || ''}`.toLowerCase();
                return hay.includes(q);
            }).slice(0, 200);
            box.innerHTML = filtered.map(d => {
                const book = (d.original_filename || '').replace(/\.pdf$/i, '');
                const label = d.zh_title || d.title || book;
                const checked = toolboxSelected.has(book) ? 'checked' : '';
                return `<label class="checkbox-row" style="display:flex;gap:6px;padding:4px 2px;">
                    <input type="checkbox" data-book="${book}" ${checked} onchange="window.onToolboxDocToggle(this)">
                    <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${label}">${label}</span>
                </label>`;
            }).join('') || `<div style="color:var(--text-muted);font-size:12px;padding:6px;">${translate('toolbox.no_docs') || '无匹配文献'}</div>`;
        };

        window.onToolboxDocToggle = (el) => {
            const book = el.getAttribute('data-book');
            if (el.checked) toolboxSelected.add(book);
            else toolboxSelected.delete(book);
        };

        const TOOLBOX_PARAM_HTML = {
            images: '<label>DPI</label><input type="number" id="tb-dpi" value="300" min="72" max="600">',
            figures: '<label>DPI</label><input type="number" id="tb-dpi" value="300" min="72" max="600">',
            docx: '',
            md: '',
            tex: '',
            ocr: '',
            compress: '',
            rotate: '<label data-i18n="toolbox.angle">旋转角度</label><input type="number" id="tb-angle" value="90" step="90">',
            split: '<label data-i18n="toolbox.range">页面范围（如 1-5）</label><input type="text" id="tb-range" placeholder="1-5" value="1-5">',
            watermark: '<label data-i18n="toolbox.wm_text">水印文字</label><input type="text" id="tb-text" placeholder="Paperfect" value="Paperfect">',
            protect: '<label data-i18n="toolbox.password">设置密码</label><input type="text" id="tb-password" placeholder="password">',
            unlock: '<label data-i18n="toolbox.password_current">当前密码（无则留空）</label><input type="text" id="tb-password" placeholder="">',
            merge: '<div style="font-size:12px;color:var(--text-muted);" data-i18n="toolbox.merge_hint">请在上方勾选 2 篇及以上文献，将按勾选顺序合并为一个 PDF。</div>',
        };

        window.onToolboxToolChange = () => {
            const sel = document.getElementById('toolbox-tool-select');
            const wrap = document.getElementById('toolbox-params');
            if (!sel || !wrap) return;
            wrap.innerHTML = TOOLBOX_PARAM_HTML[sel.value] || '';
            document.querySelectorAll('#toolbox-params [data-i18n]').forEach(el => {
                el.textContent = translate(el.getAttribute('data-i18n'));
            });
        };

        const openToolbox = async () => {
            document.getElementById('toolboxModal').classList.add('active');
            toolboxSelected.clear();
            const search = document.getElementById('toolbox-doc-search');
            if (search) {
                search.value = '';
                search.oninput = () => renderToolboxDocs(search.value);
            }
            const resultBox = document.getElementById('toolbox-result');
            if (resultBox) resultBox.innerHTML = '';
            try {
                const res = await fetch('/api/library/documents');
                toolboxDocs = await res.json();
            } catch (e) {
                toolboxDocs = [];
            }
            renderToolboxDocs('');
            window.onToolboxToolChange();
        };

        window.runToolboxTool = async () => {
            const tool = (document.getElementById('toolbox-tool-select') || {}).value;
            const books = Array.from(toolboxSelected);
            const resultBox = document.getElementById('toolbox-result');
            const btn = document.getElementById('toolboxRunBtn');
            if (!tool || books.length === 0) {
                if (resultBox) resultBox.textContent = translate('toolbox.pick_at_least_one') || '请至少选择一篇文献';
                return;
            }
            const dpi = (document.getElementById('tb-dpi') || {}).value || '300';
            const angle = (document.getElementById('tb-angle') || {}).value || '90';
            const range = (document.getElementById('tb-range') || {}).value || '1-5';
            const text = (document.getElementById('tb-text') || {}).value || '';
            const password = (document.getElementById('tb-password') || {}).value || '';
            const rangeMatch = String(range).match(/(\d+)\s*-\s*(\d+)/);

            if (btn) { btn.disabled = true; btn.dataset.orig = btn.innerText; btn.innerText = translate('toolbox.running') || '执行中...'; }
            if (resultBox) resultBox.innerHTML = '';

            try {
                if (tool === 'merge') {
                    if (books.length < 2) {
                        if (resultBox) resultBox.textContent = translate('toolbox.merge_need_two') || '合并至少需要选择两篇文献';
                        return;
                    }
                    const res = await fetch('/api/tools/merge', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ book_names: books }),
                    });
                    const data = await res.json().catch(() => ({}));
                    if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
                    if (resultBox) resultBox.innerHTML = `<a href="${data.download}" target="_blank">${translate('toolbox.download') || '下载合并结果'}</a>`;
                    return;
                }

                const links = [];
                for (const book of books) {
                    const q = new URLSearchParams({ book_name: book });
                    let url = '';
                    if (tool === 'images') { q.set('dpi', dpi); url = '/api/tools/export/images'; }
                    else if (tool === 'figures') { q.set('dpi', dpi); url = '/api/tools/export/figures'; }
                    else if (tool === 'docx') { url = '/api/tools/export/docx'; }
                    else if (tool === 'md') { q.set('fmt', 'md'); url = '/api/tools/export/text'; }
                    else if (tool === 'tex') { q.set('fmt', 'tex'); url = '/api/tools/export/text'; }
                    else if (tool === 'ocr') { url = '/api/tools/ocr'; }
                    else if (tool === 'compress') { url = '/api/tools/compress'; }
                    else if (tool === 'rotate') { q.set('angle', angle); url = '/api/tools/rotate'; }
                    else if (tool === 'split') { q.set('start', rangeMatch ? rangeMatch[1] : '1'); if (rangeMatch) q.set('end', rangeMatch[2]); url = '/api/tools/split'; }
                    else if (tool === 'watermark') { q.set('text', text || 'Paperfect'); url = '/api/tools/watermark'; }
                    else if (tool === 'protect') { q.set('password', password); url = '/api/tools/protect'; }
                    else if (tool === 'unlock') { q.set('password', password); url = '/api/tools/unlock'; }
                    if (!url) continue;

                    try {
                        const res = await fetch(`${url}?${q.toString()}`, { method: 'POST' });
                        const data = await res.json().catch(() => ({}));
                        if (!res.ok) throw new Error(data.detail || ('HTTP ' + res.status));
                        links.push({ book, href: data.download });
                    } catch (e) {
                        links.push({ book, error: e.message || String(e) });
                    }
                }
                if (resultBox) {
                    resultBox.innerHTML = links.map(l => l.href
                        ? `<div><a href="${l.href}" target="_blank">${l.book}</a></div>`
                        : `<div style="color:#f87171;">${l.book}: ${l.error}</div>`
                    ).join('');
                }
            } catch (e) {
                if (resultBox) resultBox.textContent = e.message || String(e);
            } finally {
                if (btn) { btn.disabled = false; btn.innerText = btn.dataset.orig || (translate('toolbox.run') || '执行'); }
            }
        };

        const saveSettings = async () => {
            const btn = document.querySelector('#settingsSaveBtn');
            const originalText = btn ? btn.innerText : "";
            if (btn) btn.innerText = translate('settings.saving') || "保存中... / Saving...";
            try {
                const keyInputs = document.querySelectorAll('.parse-key-input');
                const parseKeysArray = Array.from(keyInputs).map(inp => inp.value.trim()).filter(v => v);
                const apiUrl = document.getElementById('parse_api_url').value.trim();
                const modelName = document.getElementById('parse_model').value.trim();
                const textRaw = (document.getElementById('text_model') || {}).value || '';
                const textModel = textRaw.trim() || modelName;

                const payload = {
                    parse_api_url: apiUrl,
                    parse_api_key: parseKeysArray,
                    parse_model: modelName,
                    
                    chat_api_url: apiUrl,
                    chat_api_key: parseKeysArray,
                    chat_model: textModel,
                    
                    paper_api_url: apiUrl,
                    paper_api_key: parseKeysArray,
                    paper_model: modelName,
                    
                    annotator_api_url: apiUrl,
                    annotator_api_key: parseKeysArray,
                    annotator_model: textModel,
                    
                    translate_api_url: apiUrl,
                    translate_api_key: parseKeysArray,
                    translate_model: textModel
                };
                await fetch('/api/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                if (btn) btn.innerText = translate('settings.saved') || "配置已保存！/ Saved!";
                setTimeout(() => {
                    closeSettings();
                    if (btn) btn.innerText = originalText;
                }, 1000);
            } catch (e) {
                if (btn) btn.innerText = translate('settings.failed') || "保存失败 / Failed";
                setTimeout(() => {
                    if (btn) btn.innerText = originalText;
                }, 1500);
            }
        };

        // Expose saveSettings and addParseKeyInput globally so they can be called from onclick attributes in inline HTML
        window.saveSettings = saveSettings;

        return {
            currentTheme, changeTheme, toggleDarkLight, isLightTheme, currentMainTab, switchMainTab, lang, switchLang,
            t: translate, openSettings, closeSettings, saveSettings, openToolbox,
            readerTabs, activeReaderBook, readerWorkspaceVisible, smartGroupOn, groupedReaderTabs,
            switchReaderTab, closeReaderTab, closeAllReaderTabs, showLibraryFromReader, wakeReaderTab,
            readerFrameSrc, groupColor, toggleSmartGroup,
            draggingBook, onTabDragStart, onTabDragOver, onTabDrop, onTabDragEnd,
            showTabContextMenu, ctxCloseTab, ctxCloseOthers, ctxCloseRight, ctxCloseAllFromMenu,
            contextMenuTargetHasGroup, ctxUngroup, toggleGroupCollapse,
        };
    }
});

app.use(router);
app.mount('#app');

