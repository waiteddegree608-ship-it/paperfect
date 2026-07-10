const { createApp, ref, computed, onMounted, watch, reactive } = Vue;
const { createRouter, createWebHashHistory, useRouter, useRoute } = VueRouter;

// Reactive Language State for Vue template bindings
const currentLang = ref(getLang());
const t = (key, params) => {
    // Read currentLang value to register dependency in Vue templates
    const _ = currentLang.value;
    return window.t(key, params);
};

// Global language listener to update Vue reactive state
window.addEventListener('lang-changed', (e) => {
    currentLang.value = e.detail.lang;
});

// Global Filter State
const filterState = reactive({
    type: [], // paper_type
    core: [], // core_type
    jcr: '',  // jcr_partition
    cas: '',  // cas_partition (Not used anymore but left in UI just in case)
    ccf: '',  // ccf_partition
    search: ''
});

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
                <input type="file" id="libUploadInput" accept=".pdf" style="display:none;" @change="handleUpload">
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
 
            <!-- Folder Inner View -->
            <template v-if="currentFolder">
                <div class="file-grid" v-if="folderDocs.length > 0">
                    <div class="file-card" v-for="doc in folderDocs" :key="doc.id" @click="openChat(doc.original_filename)" :title="getLang() === 'en' ? doc.title : (doc.zh_title || doc.title)">
                        <button class="delete-btn" @click="deleteDoc($event, doc.id)">×</button>
                        <div class="file-cover">
                            <img :src="'/cover/' + (doc.original_filename.replace('.pdf',''))" onerror="this.src='/static/favicon.png'" />
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
                    <div class="section-title">{{ t('dash.folders_title') }}</div>
                </div>
                <div class="folder-grid">
                    <div class="folder-card" v-for="(folder, idx) in folders" :key="folder.id" @click="enterFolder(folder)">
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
                    <div class="recent-card" v-for="doc in recentDocs" :key="doc.id" :title="doc.title" @click="openChat(doc.original_filename)">
                        <button class="delete-btn" @click="deleteDoc($event, doc.id)">×</button>
                        <img :src="'/cover/' + (doc.original_filename.replace('.pdf',''))" onerror="this.src='/static/favicon.png'" />
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

        const loadFolders = async () => {
            const fRes = await fetch('/api/library/folders');
            folders.value = await fRes.json();
        };

        const loadRecentDocs = async () => {
            const dRes = await fetch('/api/library/documents');
            const allDocs = await dRes.json();
            recentDocs.value = allDocs.slice(-8).reverse();
        };

        const loadFolderDocs = async (folderId) => {
            const dRes = await fetch('/api/library/documents?folder_id=' + folderId);
            folderDocs.value = await dRes.json();
        };

        onMounted(async () => {
            await Promise.all([loadFolders(), loadRecentDocs()]);
            
            // Attach upload button logic
            const uploadBtn = document.getElementById('finalUploadBtn');
            if (uploadBtn) {
                uploadBtn.onclick = async () => {
                    const file = window.uploadSelectedFile;
                    if(!file) return;
                    
                    uploadBtn.innerText = t('upload.uploading');
                    uploadBtn.disabled = true;
                    
                    const formData = new FormData();
                    formData.append('file', file);
                    formData.append('item_type', document.getElementById('upload_item_type').value);
                    
                    const folderSelect = document.getElementById('upload_folder_select').value;
                    const folderNew = document.getElementById('upload_folder_new').value;
                    
                    if (folderNew) {
                        formData.append('folder_name', folderNew);
                    } else if (folderSelect) {
                        formData.append('folder_id', folderSelect);
                    }
                    
                    if (document.getElementById('upload_item_type').value === 'paper') {
                        formData.append('prompt_type', document.getElementById('upload_prompt').value);
                        formData.append('ppt_mode', document.getElementById('upload_ppt_mode').value);
                        formData.append('ppt_lang', document.getElementById('upload_language').value);
                    }
                    
                    try {
                        await fetch('/api/library/upload', { method: 'POST', body: formData });
                        window.location.reload();
                    } catch (e) {
                        alert(t('upload.error'));
                        uploadBtn.innerText = t('upload.confirm');
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
                    if (confirm(t('folder.confirm_delete', {name: contextTarget.value.name}))) {
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
        const onDrop = (e) => {
            isDragOver.value = false;
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                const file = files[0];
                window.uploadSelectedFile = file;
                document.getElementById('selectedFileName').innerText = t('upload.current_file') + file.name;
                document.getElementById('upload_folder_select').innerHTML = '<option value="">' + t('upload.folder_default') + '</option>' + folders.value.map(f => {
                    const name = f.name === '默认文件夹' ? t('upload.folder_default') : f.name;
                    return `<option value="${f.id}">${name}</option>`;
                }).join('');
                document.getElementById('uploadModal').classList.add('active');
            }
        };

        const triggerUpload = () => { document.getElementById('libUploadInput').click(); };
        const handleUpload = (e) => {
            const file = e.target.files[0];
            if(!file) return;
            window.uploadSelectedFile = file;
            document.getElementById('selectedFileName').innerText = t('upload.current_file') + file.name;
            document.getElementById('upload_folder_select').innerHTML = '<option value="">' + t('upload.folder_default') + '</option>' + folders.value.map(f => {
                const name = f.name === '默认文件夹' ? t('upload.folder_default') : f.name;
                return `<option value="${f.id}">${name}</option>`;
            }).join('');
            document.getElementById('uploadModal').classList.add('active');
        };
        
        const openChat = (filename) => {
            const name = filename.replace('.pdf', '');
            window.location.href = '/chat/' + encodeURIComponent(name);
        };
        
        const deleteDoc = async (e, id) => {
            e.stopPropagation();
            if (confirm(t('confirm.delete_doc'))) {
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

        return { 
            folders, recentDocs, isDragOver, currentFolder, folderDocs,
            triggerUpload, handleUpload, openChat, deleteDoc,
            onDragOver, onDragLeave, onDrop,
            enterFolder, exitFolder, openCreateFolder,
            showContextMenu, folderColor, t, getLang
        };
    }
};

// Wrapper for "自动分类" which has the Sub-Nav and Right Sidebar
const AutoLayout = {
    template: `
        <div style="display:flex; flex-direction:column; width: 100%; height: 100%; flex: 1; overflow: hidden;">
            <div class="content-area">
                <!-- Main Area for sub-routes -->
                <div class="main-view">
                    <router-view></router-view>
                </div>
                
                <!-- Right Sidebar (Only for List & Graph) -->
                <div class="right-sidebar" v-if="$route.path !== '/auto/search'">
                    
                    <!-- If in Graph View, show search and cards like Image 3 -->
                    <template v-if="$route.path === '/auto/graph'">
                        <input type="text" v-model="filterState.search" :placeholder="t('auto.search_graph_nodes')" style="background:var(--input-bg); border:1px solid var(--header-border); padding:8px; width:100%; box-sizing:border-box;">
                        
                        <div class="list-card" style="margin-bottom:10px; margin-top:20px;">
                            <div class="list-card-line" style="width: 100%;"></div>
                            <div style="display:flex; gap:10px;">
                                <div class="list-card-line" style="width: 40%;"></div>
                                <div class="list-card-line" style="width: 40%;"></div>
                            </div>
                        </div>
                    </template>
                    
                    <!-- If in List View, show Checkboxes & Buttons like Image 2 -->
                    <template v-else>
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

                        <!-- CAS Partition -->
                        <div class="filter-section" style="padding-bottom: 2px;">
                            <div style="text-align:center; font-size:12px; margin-bottom:5px;">{{ t('filter.cas_partition') }}</div>
                            <div class="segmented-control">
                                <button :class="{active: filterState.cas === '一区'}" @click="filterState.cas = filterState.cas === '一区' ? '' : '一区'">{{ t('filter.q1') }}</button>
                                <button :class="{active: filterState.cas === '二区'}" @click="filterState.cas = filterState.cas === '二区' ? '' : '二区'">{{ t('filter.q2') }}</button>
                                <button :class="{active: filterState.cas === '三区'}" @click="filterState.cas = filterState.cas === '三区' ? '' : '三区'">{{ t('filter.q3') }}</button>
                                <button :class="{active: filterState.cas === '四区'}" @click="filterState.cas = filterState.cas === '四区' ? '' : '四区'">{{ t('filter.q4') }}</button>
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
                    </template>
                    
                </div>
            </div>
        </div>
    `,
    setup() {
        return { filterState, t };
    }
};

// Image 2: Document List
const ListView = {
    template: `
        <div>
            <!-- Real Data List -->
            <div class="doc-list-item" v-for="doc in filteredDocuments" :key="doc.id" @click="openChat(doc.original_filename)">
                <button class="delete-btn" @click="deleteDoc($event, doc.id)" title="永久删除" style="right: 20px; top: 20px;">×</button>
                <div class="doc-title">
                    {{ getLang() === 'en' ? doc.title : (doc.zh_title || doc.title) }}
                    <div v-if="getLang() !== 'en' && doc.zh_title" style="font-size: 14px; color: var(--text-muted); font-weight: normal; margin-top: 5px;">{{ doc.title }}</div>
                </div>
                
                <!-- Display new metadata tags -->
                <div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; align-items: center;">
                    <span class="tag-badge" style="background: var(--header-bg); border: 1px solid var(--primary-accent); color: var(--primary-accent);" v-if="doc.venue && doc.venue !== 'Unknown'">{{ doc.venue }}</span>
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
        onMounted(async () => {
            const dRes = await fetch('/api/library/documents');
            rawDocuments.value = await dRes.json();
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
        
        const openChat = (filename) => {
            const name = filename.replace('.pdf', '');
            window.location.href = '/chat/' + encodeURIComponent(name);
        };
        
        const deleteDoc = async (e, id) => {
            e.stopPropagation();
            if (confirm(t('confirm.delete_doc'))) {
                await fetch('/api/library/documents/' + id, { method: 'DELETE' });
                rawDocuments.value = rawDocuments.value.filter(d => d.id !== id);
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
        
        return { filteredDocuments, openChat, deleteDoc, parseKeywords, tMetadata, t, getLang };
    }
};

// Image 3: Graph View
const GraphView = {
    template: `
        <div style="height: calc(100vh - 200px); min-height: 500px; width: 100%; display: flex; align-items:center; justify-content:center;">
            <div id="echarts-container" style="width:100%; height:100%;"></div>
        </div>
    `,
    async mounted() {
        const chartDom = document.getElementById('echarts-container');
        if(!chartDom) return;
        const myChart = echarts.init(chartDom);
        
        const rootStyle = getComputedStyle(document.body);
        const primaryColor = rootStyle.getPropertyValue('--primary-accent').trim() || '#3D71D9';
        const bg = rootStyle.getPropertyValue('--bg-color').trim() || '#282C34';
        const textColor = rootStyle.getPropertyValue('--text-color').trim() || '#ABB2BF';
        
        // Fetch Real Graph Data
        const res = await fetch('/api/library/graph');
        const data = await res.json();
        
        // Customize nodes based on whether they are documents (White rectangles with cover) or tags (Blue strips)
        data.nodes.forEach(node => {
            if (node.category === 0) {
                // Document: Use Circle without white box to not overlap text
                node.symbol = 'circle';
                node.symbolSize = 16;
                node.itemStyle = { color: '#ffffff', borderColor: '#888', borderWidth: 2 };
            } else {
                // Keyword Tag: Strip shape
                node.symbol = 'roundRect';
                node.symbolSize = [80, 26];
                node.itemStyle = { color: primaryColor, borderRadius: 13 };
                node.label = { show: true, color: '#fff', fontSize: 12, position: 'inside', formatter: '{b}' };
            }
        });

        const option = {
            tooltip: {},
            series: [{
                type: 'graph',
                layout: 'force',
                roam: true,
                force: { repulsion: 800, edgeLength: 100, gravity: 0.1 },
                data: data.nodes,
                links: data.links,
                label: {
                    show: true,
                    position: 'bottom',
                    formatter: (params) => {
                        return params.data.category === 0 ? params.data.name : '';
                    },
                    color: textColor,
                    fontSize: 14
                },
                lineStyle: { color: '#888', width: 2, curveness: 0.1 }
            }]
        };
        myChart.setOption(option);
        window.addEventListener('resize', () => myChart.resize());
    }
};

const SearchView = {
    template: `
        <div style="display:flex; height: 100%; width: 100%; overflow: hidden;">
            <!-- Left Pane: Search Results -->
            <div style="flex: 1; padding: 20px; overflow-y: auto; border-right: 2px solid var(--header-border);">
                <div v-if="loading" style="text-align: center; color: var(--text-muted); margin-top: 50px;">
                    <div style="margin-bottom: 10px; font-size: 16px;">🔍 AI 正在思考并检索知识库，请稍候...</div>
                    <div style="font-size: 13px; opacity: 0.7;">（如果文献较多或需要深入阅读，可能需要10-20秒）</div>
                </div>
                <div v-else-if="results.length > 0">
                    <div style="font-size: 14px; color: var(--text-muted); margin-bottom: 15px;">共找到 {{ results.length }} 篇相关文献：</div>
                    <div class="doc-list-item" v-for="doc in results" :key="doc.id" @click="openChat(doc.original_filename)">
                        <div class="doc-title">
                            {{ doc.title }}
                            <div v-if="doc.zh_title" style="font-size: 14px; color: var(--text-muted); font-weight: normal; margin-top: 5px;">{{ doc.zh_title }}</div>
                        </div>
                        <div style="margin-top: 8px; display: flex; flex-wrap: wrap; gap: 5px; align-items: center;">
                            <span class="tag-badge" style="background: var(--header-bg); border: 1px solid var(--primary-accent); color: var(--primary-accent);" v-if="doc.venue && doc.venue !== 'Unknown'">{{ doc.venue }}</span>
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
                            <span v-if="!loading" style="font-size: 18px;">➤</span>
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

        const openChat = (filename) => {
            const name = filename.replace('.pdf', '');
            window.location.href = '/chat/' + encodeURIComponent(name);
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
            const name = window.prompt(t('prompt.new_dialog'));
            if (!name) return;
            const initContent = '## ' + name + '\n### Section 1\n';
            await fetch('/api/prompts/' + encodeURIComponent(name) + '?lang=' + currentLang.value, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({content: initContent})
            });
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
            await fetch('/api/prompts/' + encodeURIComponent(currentPrompt.value) + '?lang=' + currentLang.value, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({content: content})
            });
            alert(t('prompt.save_ok'));
            loadList();
        };

        const deletePrompt = async () => {
            if (!currentPrompt.value) return;
            if (!confirm(t('prompt.confirm_delete', {name: currentPromptDisplayName.value}))) return;
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
                const def = promptNames.value.find(p => p.includes('人工智能')) || promptNames.value[0];
                loadPrompt(def);
            }
        });

        return { promptNames, currentPrompt, segments, loadList, loadPrompt, createPrompt, savePrompt, deletePrompt, addSegment, t };
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
                el.textContent = t(el.getAttribute('data-i18n'));
            });
            document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
                el.placeholder = t(el.getAttribute('data-i18n-placeholder'));
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

        const toggleDarkLight = () => {
            const lightThemes = ['cyan-light'];
            if (lightThemes.includes(currentTheme.value)) {
                currentTheme.value = localStorage.getItem('preferred_dark') || 'antigravity';
            } else {
                localStorage.setItem('preferred_dark', currentTheme.value);
                currentTheme.value = 'cyan-light';
            }
            changeTheme();
        };

        const switchMainTab = (tab) => {
            currentMainTab.value = tab;
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
                document.getElementById('parse_api_url').value = cfg.parse_api_url || 'https://generativelanguage.googleapis.com/v1beta/openai/';
                
                const keyList = document.getElementById('parse_api_key_list');
                if (keyList) {
                    keyList.innerHTML = '';
                    let parseKeys = cfg.parse_api_key || [];
                    if (typeof parseKeys === 'string') parseKeys = parseKeys.split(',');
                    if (parseKeys.length === 0) parseKeys = [''];
                    parseKeys.forEach(k => window.addParseKeyInput(k.trim()));
                }

                document.getElementById('parse_model').value = cfg.parse_model || 'gemini-2.5-flash';
            } catch (e) {
                console.error("加载配置失败", e);
            }
        };

        const closeSettings = () => {
            document.getElementById('settingsModal').classList.remove('active');
        };

        const saveSettings = async () => {
            const btn = document.querySelector('#settingsSaveBtn');
            const originalText = btn ? btn.innerText : "";
            if (btn) btn.innerText = t('settings.saving') || "保存中... / Saving...";
            try {
                const keyInputs = document.querySelectorAll('.parse-key-input');
                const parseKeysArray = Array.from(keyInputs).map(inp => inp.value.trim()).filter(v => v);
                const apiUrl = document.getElementById('parse_api_url').value.trim();
                const modelName = document.getElementById('parse_model').value.trim();

                const payload = {
                    parse_api_url: apiUrl,
                    parse_api_key: parseKeysArray,
                    parse_model: modelName,
                    
                    chat_api_url: apiUrl,
                    chat_api_key: parseKeysArray,
                    chat_model: modelName,
                    
                    paper_api_url: apiUrl,
                    paper_api_key: parseKeysArray,
                    paper_model: modelName,
                    
                    annotator_api_url: apiUrl,
                    annotator_api_key: parseKeysArray,
                    annotator_model: modelName,
                    
                    translate_api_url: apiUrl,
                    translate_api_key: parseKeysArray,
                    translate_model: modelName
                };
                await fetch('/api/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(payload)
                });
                if (btn) btn.innerText = t('settings.saved') || "配置已保存！/ Saved!";
                setTimeout(() => {
                    closeSettings();
                    if (btn) btn.innerText = originalText;
                }, 1000);
            } catch (e) {
                if (btn) btn.innerText = t('settings.failed') || "保存失败 / Failed";
                setTimeout(() => {
                    if (btn) btn.innerText = originalText;
                }, 1500);
            }
        };

        // Expose saveSettings and addParseKeyInput globally so they can be called from onclick attributes in inline HTML
        window.saveSettings = saveSettings;

        return { currentTheme, changeTheme, toggleDarkLight, currentMainTab, switchMainTab, lang, switchLang, t, openSettings, closeSettings, saveSettings };
    }
});

app.use(router);
app.mount('#app');

