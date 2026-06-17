const { createApp, ref, computed, onMounted, watch, reactive } = Vue;
const { createRouter, createWebHashHistory, useRouter, useRoute } = VueRouter;

// Global Filter State
const filterState = reactive({
    type: [], // paper_type
    core: [], // core_type
    jcr: '',  // jcr_partition
    cas: '',  // cas_partition (Not used anymore but left in UI just in case)
    ccf: '',  // ccf_partition
    search: ''
});

// --- Views ---

// Image 1: "我的资料" (Dashboard)
const DashboardView = {
    template: `
        <div class="main-view" style="padding: 30px;">
            <div class="dashed-box" @click="triggerUpload" style="cursor: pointer;">
                <input type="file" id="libUploadInput" style="display:none;" @change="handleUpload">
                <div style="color: var(--text-muted); font-size: 18px;">拖拽文件到此上传 或 点击选择文件...</div>
            </div>
            
            <div style="font-size: 12px; color: var(--text-muted); margin-bottom: 10px;">最近上传</div>
            <div style="display: flex; flex-wrap: wrap; gap: 20px;">
                <div class="recent-card" v-for="doc in recentDocs" :key="doc.id" :title="doc.title" @click="openChat(doc.original_filename)">
                    <button class="delete-btn" @click="deleteDoc($event, doc.id)" title="永久删除">×</button>
                    <img :src="'/cover/' + (doc.original_filename.replace('.pdf',''))" onerror="this.src='/static/favicon.png'" />
                    <div style="position: absolute; bottom: 0; background: rgba(0,0,0,0.7); width: 100%; font-size: 12px; color: #fff; text-align: center; padding: 5px;">{{ doc.zh_title || doc.title }}</div>
                </div>
                <div v-if="recentDocs.length === 0" style="color: var(--text-muted);">暂无记录</div>
            </div>
            
            <div class="folder-row">
                <div class="folder-mock" v-for="folder in folders" :key="folder.id">
                    <div style="position: absolute; top: 40px; left: 15px; color: #fff; font-weight: bold; font-size: 14px;">{{ folder.name }}</div>
                </div>
            </div>
        </div>
    `,
    setup() {
        const folders = ref([]);
        const recentDocs = ref([]);

        onMounted(async () => {
            const fRes = await fetch('/api/library/folders');
            folders.value = await fRes.json();
            const dRes = await fetch('/api/library/documents');
            const allDocs = await dRes.json();
            recentDocs.value = allDocs.slice(-5).reverse(); // Last 5 docs
            
            // Attach upload button logic
            const uploadBtn = document.getElementById('finalUploadBtn');
            if (uploadBtn) {
                uploadBtn.onclick = async () => {
                    const file = window.uploadSelectedFile;
                    if(!file) return;
                    
                    uploadBtn.innerText = "上传引擎启动中...";
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
                    }
                    
                    try {
                        await fetch('/api/library/upload', { method: 'POST', body: formData });
                        window.location.reload();
                    } catch (e) {
                        alert("上传出错");
                        uploadBtn.innerText = "确认并开始上传";
                        uploadBtn.disabled = false;
                    }
                };
            }
        });

        const triggerUpload = () => { document.getElementById('libUploadInput').click(); };
        const handleUpload = (e) => {
            const file = e.target.files[0];
            if(!file) return;
            window.uploadSelectedFile = file;
            document.getElementById('selectedFileName').innerText = "当前文件: " + file.name;
            document.getElementById('upload_folder_select').innerHTML = '<option value="">默认文件夹</option>' + folders.value.map(f => `<option value="${f.id}">${f.name}</option>`).join('');
            document.getElementById('uploadModal').classList.add('active');
        };
        
        const openChat = (filename) => {
            const name = filename.replace('.pdf', '');
            window.location.href = '/chat/' + encodeURIComponent(name);
        };
        
        const deleteDoc = async (e, id) => {
            e.stopPropagation();
            if (confirm("确定要永久删除该文献吗？该操作不可逆转！")) {
                await fetch('/api/library/documents/' + id, { method: 'DELETE' });
                recentDocs.value = recentDocs.value.filter(d => d.id !== id);
            }
        };

        return { folders, recentDocs, triggerUpload, handleUpload, openChat, deleteDoc };
    }
};

// Wrapper for "自动分类" which has the Sub-Nav and Right Sidebar
const AutoLayout = {
    template: `
        <div style="display:flex; flex-direction:column; width: 100%; height: 100%; flex: 1; overflow: hidden;">
            <!-- Sub Navigation Bar (Image 2 & 3) -->
            <div class="sub-nav-bar">
                <button class="sub-tab" :class="{active: $route.path === '/auto/list'}" @click="$router.push('/auto/list')">分类</button>
                <button class="sub-tab" :class="{active: $route.path === '/auto/graph'}" @click="$router.push('/auto/graph')">查看联系</button>
                <button class="sub-tab" :class="{active: $route.path === '/auto/search'}" @click="$router.push('/auto/search')">万能搜索</button>
            </div>
            
            <div class="content-area">
                <!-- Main Area for sub-routes -->
                <div class="main-view">
                    <router-view></router-view>
                </div>
                
                <!-- Right Sidebar (Only for List & Graph) -->
                <div class="right-sidebar" v-if="$route.path !== '/auto/search'">
                    
                    <!-- If in Graph View, show search and cards like Image 3 -->
                    <template v-if="$route.path === '/auto/graph'">
                        <input type="text" v-model="filterState.search" placeholder="在图谱中搜索节点..." style="background:var(--input-bg); border:1px solid var(--header-border); padding:8px; width:100%; box-sizing:border-box;">
                        
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
                            <div class="filter-title">文献检索</div>
                            <input type="text" v-model="filterState.search" placeholder="标题/摘要关键词..." style="width:100%; box-sizing:border-box; background:var(--input-bg); color:var(--text-color); border:1px solid var(--header-border); height:28px; padding: 0 5px;">
                        </div>

                        <div class="filter-section">
                            <div class="filter-title">文献类型</div>
                            <label class="checkbox-row"><input type="checkbox" value="综述" v-model="filterState.type"> 综述</label>
                            <label class="checkbox-row"><input type="checkbox" value="研究" v-model="filterState.type"> 研究</label>
                        </div>

                        <div class="filter-section">
                            <div class="filter-title">核心期刊</div>
                            <label class="checkbox-row"><input type="checkbox" value="南大核心" v-model="filterState.core"> 南大核心</label>
                            <label class="checkbox-row"><input type="checkbox" value="北大核心" v-model="filterState.core"> 北大核心</label>
                            <label class="checkbox-row"><input type="checkbox" value="中文核心" v-model="filterState.core"> 中文核心</label>
                        </div>
                        
                        <!-- JCR Partition -->
                        <div class="filter-section" style="padding-bottom: 2px;">
                            <div style="text-align:center; font-size:12px; margin-bottom:5px;">Jcr分区-2026</div>
                            <div class="segmented-control">
                                <button :class="{active: filterState.jcr === '一区'}" @click="filterState.jcr = filterState.jcr === '一区' ? '' : '一区'">一区</button>
                                <button :class="{active: filterState.jcr === '二区'}" @click="filterState.jcr = filterState.jcr === '二区' ? '' : '二区'">二区</button>
                                <button :class="{active: filterState.jcr === '三区'}" @click="filterState.jcr = filterState.jcr === '三区' ? '' : '三区'">三区</button>
                                <button :class="{active: filterState.jcr === '四区'}" @click="filterState.jcr = filterState.jcr === '四区' ? '' : '四区'">四区</button>
                            </div>
                        </div>

                        <!-- CAS Partition -->
                        <div class="filter-section" style="padding-bottom: 2px;">
                            <div style="text-align:center; font-size:12px; margin-bottom:5px;">中科院分区-2026</div>
                            <div class="segmented-control">
                                <button :class="{active: filterState.cas === '一区'}" @click="filterState.cas = filterState.cas === '一区' ? '' : '一区'">一区</button>
                                <button :class="{active: filterState.cas === '二区'}" @click="filterState.cas = filterState.cas === '二区' ? '' : '二区'">二区</button>
                                <button :class="{active: filterState.cas === '三区'}" @click="filterState.cas = filterState.cas === '三区' ? '' : '三区'">三区</button>
                                <button :class="{active: filterState.cas === '四区'}" @click="filterState.cas = filterState.cas === '四区' ? '' : '四区'">四区</button>
                            </div>
                        </div>

                        <!-- CCF Partition -->
                        <div class="filter-section" style="padding-bottom: 2px;">
                            <div style="text-align:center; font-size:12px; margin-bottom:5px;">CCF分区-2026</div>
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
        return { filterState };
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
                    {{ doc.title }}
                    <div v-if="doc.zh_title" style="font-size: 14px; color: var(--text-muted); font-weight: normal; margin-top: 5px;">{{ doc.zh_title }}</div>
                </div>
                
                <!-- Display new metadata tags -->
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
            <div v-if="filteredDocuments.length === 0" style="text-align: center; color: var(--text-muted); margin-top: 50px;">
                暂无分类文献
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
            if (confirm("确定要永久删除该文献吗？该操作不可逆转！")) {
                await fetch('/api/library/documents/' + id, { method: 'DELETE' });
                rawDocuments.value = rawDocuments.value.filter(d => d.id !== id);
            }
        };
        
        return { filteredDocuments, openChat, deleteDoc };
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
            { role: 'assistant', content: '您好！我是您的学术文献助手。您可以告诉我您正在研究什么方向，或者想找什么特定的论文，我会从您的知识库中为您精准检索和推荐。' }
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
                    body: JSON.stringify({ message: text, chat_history: historyToSend })
                });

                if (!res.ok) throw new Error("API Request Failed");
                
                const data = await res.json();
                chatHistory.value.push({ role: 'assistant', content: data.reply });
                results.value = data.documents || [];
            } catch (e) {
                console.error(e);
                chatHistory.value.push({ role: 'assistant', content: '抱歉，检索过程中出现了网络或服务器错误，请稍后再试。' });
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
    }
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

        onMounted(() => {
            document.body.setAttribute('data-theme', currentTheme.value);
            // Sync main tab state on load
            if(route.path.startsWith('/auto')) {
                currentMainTab.value = 'auto';
            }
        });
        
        watch(() => route.path, (newPath) => {
            if(newPath.startsWith('/auto')) {
                currentMainTab.value = 'auto';
            } else if (newPath.startsWith('/dashboard')) {
                currentMainTab.value = 'dashboard';
            }
        });

        const changeTheme = () => {
            document.body.setAttribute('data-theme', currentTheme.value);
            localStorage.setItem('theme', currentTheme.value);
        };

        const switchMainTab = (tab) => {
            currentMainTab.value = tab;
            if (tab === 'dashboard') {
                router.push('/dashboard');
            } else {
                router.push('/auto/list');
            }
        };

        return { currentTheme, changeTheme, currentMainTab, switchMainTab };
    }
});

app.use(router);
app.mount('#app');
