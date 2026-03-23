/**
 * Copyright (c) 2026 jasen chen. All rights reserved.
 *
 * Licensed under the MIT License (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     https://opensource.org/licenses/MIT
 *
 * Project Repository: https://github.com/jasen-ai/ia800UICS
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

const { createApp } = Vue;

createApp({
    data() {
        return {
            // 认证状态
            isAuthenticated: false,
            currentUser: null,
            sessionId: null,
            
            // 登录表单
            loginForm: {
                username: '',
                password: ''
            },
            loginError: null,
            showRegister: false,
            registerForm: {
                username: '',
                password: ''
            },
            registerError: null,
            
            // 标签页
            activeTab: 'excel',
            
            // Excel数据
            excelLoaded: false,
            loading: false,
            error: null,
            sheets: [],
            selectedSheet: null,
            excelData: {},
            hotInstance: null,
            
            // 生成配置
            generateConfig: {
                image: {
                    outputDir: './output',  // 后端会自动解析为UICS目录下的output（UICS/output）
                    episodeFilter: '',
                    shotFilter: '',  // 分镜过滤，空值表示所有分镜
                    generatorType: 'comfyui',
                    comfyuiServer: '127.0.0.1:8188',
                    generateReference: true,
                    generateFirstFrame: false,
                    generateLastFrame: false,
                    enablePromptExpansion: true
                },
                video: {
                    outputDir: './output',  // 后端会自动解析为UICS目录下的output（UICS/output）
                    episodeFilter: '',
                    shotFilter: '',
                    generatorType: 'comfyui',
                    comfyuiServer: '127.0.0.1:8188',
                    enablePromptExpansion: true
                },
                scene: {
                    outputDir: './output',  // 后端会自动解析为UICS目录下的output（UICS/output）
                    episodeFilter: '',
                    sceneFilter: '',  // 场景id/场景名，空值表示所有场景
                    generatorType: 'comfyui',
                    comfyuiServer: '127.0.0.1:8188'
                },
                audio: {
                    outputDir: './output',  // 后端会自动解析为UICS目录下的output（UICS/output）
                    episodeFilter: '',
                    shotFilter: '',
                    generatorType: 'volcengine',
                    comfyuiServer: '127.0.0.1:8188',
                    workflowPath: 'Qwen3-TTSVoiceCloneAPI.json'
                }
            },
            
            // 任务列表
            tasks: [],
            
            // 防抖定时器
            loadSheetDataTimer: null,
            scrollPosition: {
                row: 0,
                col: 0
            },
            // 预览 URL 加戳，重新加载后强制拉取最新文件（避免浏览器缓存旧图）
            previewCacheBust: 0
        };
    },
    
    mounted() {
        // 检查是否有保存的会话
        const savedSession = localStorage.getItem('uics_session');
        if (savedSession) {
            try {
                const session = JSON.parse(savedSession);
                this.sessionId = session.sessionId;
                this.currentUser = session.user;
                this.isAuthenticated = true;
                this.initSocket();
                this.loadTasks();
            } catch (e) {
                console.error('恢复会话失败:', e);
            }
        }
    },
    
    watch: {
        // 监听标签页切换
        activeTab(newTab, oldTab) {
            console.log(`[标签页] 切换到: ${newTab} (从 ${oldTab})`);
            
            // 如果切换到Excel编辑标签页，且数据已加载，重新渲染表格
            if (newTab === 'excel' && this.excelLoaded && this.selectedSheet) {
                // 清除之前的定时器
                if (this.loadSheetDataTimer) {
                    clearTimeout(this.loadSheetDataTimer);
                }
                // 使用nextTick确保DOM已更新
                this.$nextTick(() => {
                    console.log('[标签页] 重新渲染Excel表格');
                    // 延迟一下确保容器元素已渲染，使用防抖
                    this.loadSheetDataTimer = setTimeout(() => {
                        this.loadSheetData();
                        this.loadSheetDataTimer = null;
                    }, 50);
                });
            }
        },
        
        // 监听工作表切换
        selectedSheet(newSheet, oldSheet) {
            if (newSheet && newSheet !== oldSheet && this.excelLoaded) {
                console.log(`[Excel] 切换工作表: ${oldSheet} -> ${newSheet}`);
                // 清除之前的定时器
                if (this.loadSheetDataTimer) {
                    clearTimeout(this.loadSheetDataTimer);
                }
                this.$nextTick(() => {
                    this.loadSheetDataTimer = setTimeout(() => {
                        this.loadSheetData();
                        this.loadSheetDataTimer = null;
                    }, 50);
                });
            }
        }
    },
    
    methods: {
        async login() {
            this.loginError = null;
            console.log('[登录] 开始登录，用户名:', this.loginForm.username);

            // 基础校验（避免空提交导致“没反应”的体验）
            if (!this.loginForm.username || !this.loginForm.password) {
                this.loginError = '用户名和密码不能为空';
                console.error('[登录] 验证失败: 用户名或密码为空');
                return;
            }

            try {
                const response = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        username: this.loginForm.username,
                        password: this.loginForm.password
                    })
                });

                console.log('[登录] 响应状态:', response.status);

                let data;
                try {
                    data = await response.json();
                    console.log('[登录] 响应数据:', data);
                } catch (jsonError) {
                    const text = await response.text();
                    console.error('[登录] JSON解析失败:', jsonError);
                    console.error('[登录] 响应文本:', text);
                    this.loginError = '服务器响应格式错误';
                    return;
                }

                if (response.ok && data && data.success) {
                    this.sessionId = data.session_id;
                    this.currentUser = {
                        username: data.username,
                        role: data.role
                    };
                    this.isAuthenticated = true;

                    console.log('[登录] 登录成功，sessionId:', this.sessionId);

                    // 保存会话
                    localStorage.setItem('uics_session', JSON.stringify({
                        sessionId: this.sessionId,
                        user: this.currentUser
                    }));

                    this.initSocket();
                    this.loadTasks();
                    this.loginForm = { username: '', password: '' };
                } else {
                    // FastAPI错误通常是 { detail: "..." }
                    const errorMsg = (data && (data.detail || data.error || data.message)) || '登录失败';
                    console.error('[登录] 登录失败:', errorMsg);
                    this.loginError = errorMsg;
                }
            } catch (error) {
                console.error('[登录] 网络错误:', error);
                this.loginError = '网络错误: ' + error.message;
            }
        },
        
        async register() {
            this.registerError = null;
            console.log('[注册] 开始注册，用户名:', this.registerForm.username);
            console.log('[注册] 表单数据:', this.registerForm);
            
            // 验证输入
            if (!this.registerForm.username || !this.registerForm.password) {
                this.registerError = '用户名和密码不能为空';
                console.error('[注册] 验证失败: 用户名或密码为空');
                return;
            }
            
            if (this.registerForm.username.length < 3) {
                this.registerError = '用户名至少需要3个字符';
                console.error('[注册] 验证失败: 用户名太短');
                return;
            }
            
            if (this.registerForm.password.length < 6) {
                this.registerError = '密码至少需要6个字符';
                console.error('[注册] 验证失败: 密码太短');
                return;
            }
            
            try {
                console.log('[注册] 发送请求到 /api/auth/register');
                const response = await fetch('/api/auth/register', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        username: this.registerForm.username,
                        password: this.registerForm.password
                    })
                });
                
                console.log('[注册] 响应状态:', response.status);
                console.log('[注册] 响应头:', response.headers);
                
                let data;
                try {
                    data = await response.json();
                    console.log('[注册] 响应数据:', data);
                } catch (jsonError) {
                    const text = await response.text();
                    console.error('[注册] JSON解析失败:', jsonError);
                    console.error('[注册] 响应文本:', text);
                    this.registerError = '服务器响应格式错误';
                    return;
                }
                
                if (response.ok) {
                    console.log('[注册] 注册成功，响应:', data);
                    alert('注册成功！请使用新账号登录');
                    this.showRegister = false;
                    this.registerForm = { username: '', password: '' };
                    this.registerError = null;
                } else {
                    const errorMsg = data.detail || data.error || data.message || '注册失败';
                    console.error('[注册] 注册失败:', errorMsg);
                    this.registerError = errorMsg;
                }
            } catch (error) {
                console.error('[注册] 网络错误:', error);
                console.error('[注册] 错误详情:', error.stack);
                this.registerError = '网络错误: ' + error.message;
            }
        },
        
        async logout() {
            if (this.sessionId) {
                try {
                    await fetch('/api/auth/logout', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ session_id: this.sessionId })
                    });
                } catch (e) {
                    console.error('登出请求失败:', e);
                }
            }
            
            this.isAuthenticated = false;
            this.currentUser = null;
            this.sessionId = null;
            localStorage.removeItem('uics_session');
            
            if (this.socket) {
                this.socket.close();
            }
        },
        
        async loadExcel() {
            this.loading = true;
            this.error = null;
            
            try {
                console.log('[Excel] 开始加载Excel数据...');
                const response = await fetch('/api/excel/read', {
                    headers: {
                        'X-Session-ID': this.sessionId
                    }
                });
                
                const data = await response.json();
                
                if (response.ok) {
                    this.sheets = data.sheets;
                    this.excelData = data.data;
                    this.excelLoaded = true;
                    console.log('[Excel] Excel数据加载成功，工作表:', this.sheets);
                    
                    if (this.sheets.length > 0) {
                        // 保持当前选中的工作表
                        const currentSheet = this.selectedSheet || this.sheets[0];
                        if (this.sheets.includes(currentSheet)) {
                            this.selectedSheet = currentSheet;
                        } else {
                            this.selectedSheet = this.sheets[0];
                        }
                        
                        // 使用 try-catch 包裹，避免 loadSheetData 的错误影响 loadExcel
                        try {
                            console.log('[Excel] 加载工作表数据:', this.selectedSheet);
                            this.loadSheetData();
                        } catch (e) {
                            console.error('[Excel] loadSheetData 出错:', e);
                            this.error = '加载表格失败: ' + e.message;
                        }
                    }
                } else {
                    this.error = data.error || '加载失败';
                    console.error('[Excel] 加载失败:', this.error);
                }
            } catch (error) {
                this.error = '网络错误: ' + error.message;
                console.error('[Excel] 网络错误:', error);
            } finally {
                this.loading = false;
            }
        },
        
        loadSheetData() {
            if (!this.selectedSheet || !this.excelData[this.selectedSheet]) {
                return;
            }
            this.previewCacheBust = Date.now();
            
            const container = document.getElementById('excel-container');
            if (!container) {
                return;
            }
            
            // 保存当前滚动位置
            if (this.hotInstance) {
                try {
                    // 检查实例是否仍然有效
                    if (this.hotInstance.rootElement && this.hotInstance.rootElement.parentNode) {
                        // 获取当前选中的单元格位置作为滚动位置参考
                        const selected = this.hotInstance.getSelected();
                        if (selected && selected.length > 0) {
                            // 使用第一个选中单元格的位置
                            this.scrollPosition = {
                                row: selected[0][0],
                                col: selected[0][1]
                            };
                            console.log('[Excel] 保存滚动位置（从选中单元格）:', this.scrollPosition);
                        } else {
                            // 如果没有选中单元格，尝试从视口获取滚动位置
                            try {
                                // 使用 Handsontable 的内部 API 获取视口信息
                                if (this.hotInstance.view && this.hotInstance.view.wt && this.hotInstance.view.wt.wtTable) {
                                    const viewport = this.hotInstance.view.wt.wtTable.getViewport();
                                    if (viewport && viewport.length >= 4) {
                                        // viewport: [startRow, endRow, startCol, endCol]
                                        this.scrollPosition = {
                                            row: Math.max(0, viewport[0] || 0),
                                            col: Math.max(0, viewport[2] || 0)
                                        };
                                        console.log('[Excel] 保存滚动位置（从视口）:', this.scrollPosition);
                                    } else {
                                        // 如果无法获取视口，尝试从滚动容器获取
                                        const scrollableElement = this.hotInstance.rootElement.querySelector('.ht_master .wtHolder');
                                        if (scrollableElement) {
                                            const scrollTop = scrollableElement.scrollTop;
                                            const scrollLeft = scrollableElement.scrollLeft;
                                            // 估算行和列（每行大约30px，每列大约100px）
                                            const estimatedRow = Math.floor(scrollTop / 30);
                                            const estimatedCol = Math.floor(scrollLeft / 100);
                                            this.scrollPosition = {
                                                row: Math.max(0, estimatedRow),
                                                col: Math.max(0, estimatedCol)
                                            };
                                            console.log('[Excel] 保存滚动位置（从滚动容器估算）:', this.scrollPosition);
                                        }
                                    }
                                }
                            } catch (e) {
                                console.warn('[Excel] 无法获取滚动位置:', e.message);
                                // 如果所有方法都失败，保持之前的滚动位置
                            }
                        }
                    }
                } catch (e) {
                    console.warn('[Excel] 保存滚动位置时出错:', e.message);
                }
            }
            
            // 安全销毁现有实例
            if (this.hotInstance) {
                try {
                    // 检查实例是否仍然有效（通过检查是否有 rootElement 属性）
                    if (this.hotInstance.rootElement && this.hotInstance.rootElement.parentNode) {
                        // 实例仍然有效，安全销毁
                        this.hotInstance.destroy();
                    }
                } catch (e) {
                    // 如果销毁过程中出错（可能已经被销毁），只记录警告
                    console.warn('[Excel] 销毁实例时出错（可能已被销毁）:', e.message);
                } finally {
                    // 无论成功与否，都清空引用
                    this.hotInstance = null;
                }
            }
            
            // 清空容器内容，确保没有残留的DOM元素
            container.innerHTML = '';
            
            const data = this.excelData[this.selectedSheet];
            // 注意：不要只用第一行的 keys（某些列可能在第一行为空/缺失导致不显示）
            // 这里取“全表列名并集”，并把预览列强制追加到末尾，确保 UI 始终显示
            const columnsSet = new Set();
            if (Array.isArray(data)) {
                data.forEach((row) => {
                    if (row && typeof row === 'object') {
                        Object.keys(row).forEach((k) => columnsSet.add(k));
                    }
                });
            }
            
            // 预览列定义（无论数据中是否已有，都强制加入列集合，保证前端表格里一定能看到这四列）
            const previewColumns = this.selectedSheet === '场景汇总'
                ? ['场景图预览']
                : ['图像预览', '首帧预览', '末帧预览', '视频预览'];
            previewColumns.forEach(c => columnsSet.add(c));
            
            // 操作列（仅在图像汇总和图像提示词工作表显示）
            const actionColumn = '操作';
            const columns = Array.from(columnsSet);
            const hasPreviewCols = true; // 现在前端一定有这四列
            const isImageSheet = this.selectedSheet === '图像汇总' || this.selectedSheet === '图像提示词';

            // 强制把预览列和操作列放到末尾显示
            const baseCols = columns.filter((c) => !previewColumns.includes(c) && c !== actionColumn);
            const tailPreviewCols = previewColumns.filter((c) => columns.includes(c));
            // 如果是图像汇总或图像提示词，添加操作列
            const orderedColumns = isImageSheet 
                ? [...baseCols, ...tailPreviewCols, actionColumn]
                : [...baseCols, ...tailPreviewCols];
            
            // 固定列定义（剧集id、分镜号）
            const fixedColumns = ['剧集id', '分镜号'];
            // 计算需要固定的列数（找到最后一个固定列的索引+1）
            let fixedColumnsCount = 0;
            fixedColumns.forEach(colName => {
                const index = columns.indexOf(colName);
                if (index !== -1 && index >= fixedColumnsCount) {
                    fixedColumnsCount = index + 1;
                }
            });
            
            // 确保 fixedColumnsCount 不超过总列数，且至少为 0
            if (fixedColumnsCount > columns.length) {
                fixedColumnsCount = 0;
            }
            
            // 验证数据格式
            if (!Array.isArray(data) || data.length === 0) {
                console.error('[Excel] 数据格式错误或为空:', data);
                this.error = '数据格式错误或为空';
                return;
            }
            
            // 创建Handsontable实例
            // 使用 Vue 的 $nextTick 确保 DOM 完全准备好
            this.$nextTick(() => {
                // 再延迟一点确保容器完全渲染
                setTimeout(() => {
                    try {
                        // 再次检查容器是否存在
                        const currentContainer = document.getElementById('excel-container');
                        if (!currentContainer) {
                            console.warn('[Excel] 容器不存在，取消创建实例');
                            this.error = '容器不存在';
                            return;
                        }
                        
                        // 确保容器是空的
                        currentContainer.innerHTML = '';
                        
                        // 验证数据格式
                        if (!Array.isArray(data) || data.length === 0) {
                            console.error('[Excel] 数据无效:', { dataLength: data?.length });
                            this.error = '数据无效或为空';
                            return;
                        }
                        
                        if (!columns || columns.length === 0) {
                            console.error('[Excel] 列无效:', { columnsLength: columns?.length });
                            this.error = '列定义无效';
                            return;
                        }
                        
                        // 清理数据，确保所有值都是有效的
                        const cleanData = data.map((row, rowIndex) => {
                            const cleanRow = {};
                            orderedColumns.forEach(col => {
                                const value = row[col];
                                // 将 null, undefined, NaN 转换为空字符串
                                if (value === null || value === undefined || (typeof value === 'number' && isNaN(value))) {
                                    cleanRow[col] = '';
                                } else {
                                    cleanRow[col] = value;
                                }
                            });
                            
                            // 调试：检查第一行的预览列数据
                            if (rowIndex === 0 && previewColumns.some(c => orderedColumns.includes(c))) {
                                console.log('[Excel] 第一行预览列数据:', previewColumns.map(col => ({
                                    col,
                                    value: cleanRow[col],
                                    original: row[col]
                                })));
                            }
                            
                            return cleanRow;
                        });
                        
                        console.log('[Excel] 数据清理完成，行数:', cleanData.length, '列数:', orderedColumns.length);
                        console.log('[Excel] 预览列:', previewColumns.filter(c => orderedColumns.includes(c)));
                        
                        // 定义预览渲染器（在构建列定义前定义，以便复用）
                        const previewRenderer = (instance, td, row, col, prop, value, cellProperties) => {
                            td.innerHTML = '';
                            td.style.textAlign = 'center';
                            td.style.verticalAlign = 'middle';

                            // prop 就是列名（data 字段名）
                            const colName = prop || (instance.getSettings().columns[col]?.data);
                            
                            // 调试日志：检查渲染器是否被调用以及接收到的值
                            if (colName && previewColumns.includes(colName)) {
                                console.log(`[预览渲染] 列: ${colName}, 行: ${row}, 原始值:`, value, `类型: ${typeof value}`);
                            }

                            const filename = value ? String(value).trim() : '';
                            if (filename && filename !== 'None' && filename !== 'nan' && filename !== '') {
                                    if (colName && previewColumns.includes(colName)) {
                                    console.log(`[预览渲染] 处理文件名: "${filename}"`);
                                }
                                const ext = filename.split('.').pop().toLowerCase();
                                const isImage = ['png', 'jpg', 'jpeg', 'webp'].includes(ext);
                                const isVideo = ['mp4', 'webm'].includes(ext);

                                if (isImage) {
                                    const img = document.createElement('img');
                                    img.src = `/api/preview/${encodeURIComponent(filename)}?t=${this.previewCacheBust || 0}`;
                                    img.style.maxWidth = '150px';
                                    img.style.maxHeight = '150px';
                                    img.style.cursor = 'pointer';
                                    img.style.objectFit = 'contain';
                                    img.style.display = 'block';
                                    img.style.margin = '0 auto';
                                    img.onclick = () => window.open(img.src, '_blank');
                                    img.onerror = () => {
                                        td.innerHTML = `<span style="color: #f00;">图片未找到</span>`;
                                    };
                                    td.appendChild(img);
                                } else if (isVideo) {
                                    const video = document.createElement('video');
                                    video.src = `/api/preview/${encodeURIComponent(filename)}?t=${this.previewCacheBust || 0}`;
                                    video.style.maxWidth = '150px';
                                    video.style.maxHeight = '150px';
                                    video.style.display = 'block';
                                    video.style.margin = '0 auto';
                                    video.controls = true;
                                    video.muted = true;
                                    video.onerror = () => {
                                        td.innerHTML = `<span style="color: #f00;">视频未找到</span>`;
                                    };
                                    td.appendChild(video);
                                } else {
                                    td.textContent = filename;
                                }
                            } else {
                                td.innerHTML = '<span style="color: #ccc; font-size: 12px;">暂无预览</span>';
                            }
                            return td;
                        };
                        
                        // 构建列定义（使用 orderedColumns，确保预览列在末尾）
                        const columnDefs = orderedColumns.map((col) => {
                            const colDef = {
                                data: col,
                                title: col,
                                type: 'text'
                            };
                            
                            // 如果是固定列（剧集id、分镜号），添加样式和只读属性
                            if (fixedColumns.includes(col)) {
                                colDef.readOnly = true;
                            }
                            
                            // 如果是预览列，设置宽度、只读和渲染器
                            if (previewColumns.includes(col)) {
                                colDef.readOnly = true;
                                colDef.width = 180;
                                colDef.renderer = previewRenderer; // 直接在列定义中设置渲染器
                            }
                            
                            // 如果是操作列，设置宽度、只读和操作按钮渲染器
                            if (col === '操作' && isImageSheet) {
                                colDef.readOnly = true;
                                colDef.width = 280;
                                colDef.renderer = (instance, td, row, col, prop, value, cellProperties) => {
                                    td.innerHTML = '';
                                    td.style.textAlign = 'center';
                                    td.style.verticalAlign = 'middle';
                                    td.style.padding = '5px';
                                    
                                    // 获取当前行的数据
                                    const rowData = instance.getDataAtRow(row);
                                    const colHeaders = instance.getColHeader();
                                    const rowObj = {};
                                    colHeaders.forEach((header, idx) => {
                                        rowObj[header] = rowData[idx];
                                    });
                                    
                                    const episodeId = rowObj['剧集id'] || '';
                                    const shotId = rowObj['分镜号'] || '';
                                    
                                    // 创建按钮容器
                                    const btnContainer = document.createElement('div');
                                    btnContainer.style.display = 'flex';
                                    btnContainer.style.flexDirection = 'column';
                                    btnContainer.style.gap = '4px';
                                    btnContainer.style.alignItems = 'center';
                                    
                                    // 创建4个按钮
                                    const buttons = [
                                        { text: '重新生成图像', type: 'image', generateReference: true, generateFirstFrame: false, generateLastFrame: false },
                                        { text: '重新生成首帧', type: 'image', generateReference: false, generateFirstFrame: true, generateLastFrame: false },
                                        { text: '重新生成末帧', type: 'image', generateReference: false, generateFirstFrame: false, generateLastFrame: true },
                                        { text: '重新生成视频', type: 'video' }
                                    ];
                                    
                                    buttons.forEach(btnConfig => {
                                        const btn = document.createElement('button');
                                        btn.textContent = btnConfig.text;
                                        btn.style.padding = '4px 8px';
                                        btn.style.fontSize = '11px';
                                        btn.style.cursor = 'pointer';
                                        btn.style.border = '1px solid #ccc';
                                        btn.style.borderRadius = '3px';
                                        btn.style.backgroundColor = '#f8f9fa';
                                        btn.style.color = '#333';
                                        btn.style.width = '100%';
                                        
                                        btn.onmouseover = () => {
                                            btn.style.backgroundColor = '#e9ecef';
                                        };
                                        btn.onmouseout = () => {
                                            btn.style.backgroundColor = '#f8f9fa';
                                        };
                                        
                                        btn.onclick = async (e) => {
                                            e.stopPropagation();
                                            if (!episodeId || !shotId) {
                                                alert('缺少剧集id或分镜号');
                                                return;
                                            }
                                            
                                            btn.disabled = true;
                                            btn.textContent = '生成中...';
                                            
                                            try {
                                                if (btnConfig.type === 'image') {
                                                    await this.generateSingleImage({
                                                        episodeId,
                                                        shotId,
                                                        generateReference: btnConfig.generateReference || false,
                                                        generateFirstFrame: btnConfig.generateFirstFrame || false,
                                                        generateLastFrame: btnConfig.generateLastFrame || false
                                                    });
                                                } else if (btnConfig.type === 'video') {
                                                    await this.generateSingleVideo({
                                                        episodeId,
                                                        shotId
                                                    });
                                                }
                                                
                                                // 不显示alert，任务完成后会自动刷新预览
                                                btn.textContent = btnConfig.text;
                                                btn.disabled = false;
                                                console.log('[重新生成] 任务已创建，等待完成后自动刷新预览');
                                            } catch (error) {
                                                alert('生成失败: ' + error.message);
                                                btn.textContent = btnConfig.text;
                                                btn.disabled = false;
                                            }
                                        };
                                        
                                        btnContainer.appendChild(btn);
                                    });
                                    
                                    td.appendChild(btnContainer);
                                    return td;
                                };
                            }
                            
                            return colDef;
                        });
                        
                        // 构建最简配置对象（移除所有可能导致 ariaTags 错误的配置）
                        const hotConfig = {
                            data: cleanData,
                            columns: columnDefs,
                            colHeaders: true,
                            rowHeaders: true,
                            width: '100%',
                            height: 600,
                            // 用插件“冻结列”，避免 fixedColumnsLeft 引发 ariaTags 报错
                            manualColumnFreeze: true,
                            licenseKey: 'non-commercial-and-evaluation',
                            afterChange: (changes, source) => {
                                if (source !== 'loadData') {
                                    this.saveCellChanges(changes);
                                }
                            },
                            afterCreateRow: (index, amount) => {
                                this.addRow(index);
                            },
                            afterRemoveRow: (index, amount) => {
                                this.deleteRow(index);
                            }
                        };
                        
                        // 图像汇总/提示词页默认拉高行高
                        if (hasPreviewCols && isImageSheet) {
                            hotConfig.rowHeights = 170;
                        }
                        
                        console.log('[Excel] 准备创建实例，配置:', {
                            dataRows: cleanData.length,
                            columns: orderedColumns.length,
                            fixedColumnsCount: fixedColumnsCount
                        });
                        
                        // 创建实例
                        this.hotInstance = new Handsontable(currentContainer, hotConfig);
                        console.log('[Excel] Handsontable实例创建成功');
                        
                        // 实例创建成功后，添加固定列和自定义渲染器
                        if (this.hotInstance) {
                            // 冻结列：剧集id、分镜号（水平滚动保持固定）
                            setTimeout(() => {
                                try {
                                    const plugin = this.hotInstance.getPlugin('manualColumnFreeze');
                                    if (!plugin) {
                                        console.warn('[Excel] manualColumnFreeze 插件不可用，无法冻结列');
                                        return;
                                    }

                                    const colIndexesToFreeze = fixedColumns
                                        .map((name) => columns.indexOf(name))
                                        .filter((idx) => idx >= 0)
                                        .sort((a, b) => a - b);

                                    console.log('[Excel] 准备冻结列索引:', colIndexesToFreeze);
                                    colIndexesToFreeze.forEach((idx) => {
                                        try {
                                            plugin.freezeColumn(idx);
                                        } catch (e) {
                                            console.warn(`[Excel] 冻结列 ${idx} 失败:`, e.message);
                                        }
                                    });

                                    this.hotInstance.render();
                                    console.log('[Excel] 冻结列完成');
                                } catch (e) {
                                    console.warn('[Excel] 冻结列过程中出错:', e.message);
                                }
                            }, 150);
                            
                            // 为固定列添加样式（无论是否启用固定列功能）
                            if (fixedColumnsCount > 0) {
                                setTimeout(() => {
                                    try {
                                        this.applyFixedColumnsStyle(fixedColumns, columns);
                                    } catch (e) {
                                        console.warn('[Excel] 应用固定列样式失败:', e.message);
                                    }
                                }, 300);
                            }
                            
                            // 预览列的渲染器已经在列定义中设置，无需再次设置
                            // 但为了确保渲染器生效，触发一次重新渲染
                            setTimeout(() => {
                                this.hotInstance.render();
                                console.log('[Excel] 预览列渲染器已应用');
                                
                                // 在所有渲染完成后恢复滚动位置
                                if (this.scrollPosition && (this.scrollPosition.row > 0 || this.scrollPosition.col > 0)) {
                                    setTimeout(() => {
                                        try {
                                            if (this.hotInstance && this.hotInstance.rootElement) {
                                                const maxRow = this.hotInstance.countRows() - 1;
                                                const maxCol = this.hotInstance.countCols() - 1;
                                                const targetRow = Math.min(this.scrollPosition.row, maxRow);
                                                const targetCol = Math.min(this.scrollPosition.col, maxCol);
                                                
                                                // 滚动到保存的位置
                                                this.hotInstance.scrollViewportTo(targetRow, targetCol);
                                                // 选中该单元格，确保位置正确
                                                this.hotInstance.selectCell(targetRow, targetCol);
                                                console.log('[Excel] 恢复滚动位置:', { row: targetRow, col: targetCol, maxRow, maxCol });
                                            }
                                        } catch (e) {
                                            console.warn('[Excel] 恢复滚动位置时出错:', e.message);
                                        }
                                    }, 200);
                                }
                            }, 100);
                        }
                    } catch (e) {
                        console.error('[Excel] 创建Handsontable实例失败:', e);
                        console.error('[Excel] 错误详情:', {
                            message: e.message,
                            stack: e.stack,
                            name: e.name
                        });
                        this.error = '创建表格失败: ' + e.message;
                    }
                }, 150); // 延迟 150ms 确保 DOM 完全准备好
            });
        },
        
        // 应用固定列样式
        applyFixedColumnsStyle(fixedColumns, columns) {
            if (!this.hotInstance) return;
            
            fixedColumns.forEach((colName) => {
                const colIndex = columns.indexOf(colName);
                if (colIndex !== -1) {
                    // 通过 afterRender 钩子添加样式
                    this.hotInstance.addHook('afterRender', () => {
                        try {
                            const cells = this.hotInstance.getCellsAtColumn(colIndex);
                            if (cells && cells.length > 0) {
                                cells.forEach(cell => {
                                    if (cell && cell.style) {
                                        cell.style.backgroundColor = '#f5f7fa';
                                        cell.style.color = '#333';
                                        cell.style.fontWeight = '500';
                                        cell.style.borderRight = '2px solid #d0d7de';
                                    }
                                });
                            }
                            
                            // 表头样式
                            const header = this.hotInstance.getCell(-1, colIndex);
                            if (header && header.style) {
                                header.style.backgroundColor = '#e9ecef';
                                header.style.fontWeight = '600';
                                header.style.borderRight = '2px solid #d0d7de';
                            }
                        } catch (e) {
                            // 忽略样式应用错误
                        }
                    });
                }
            });
        },
        
        async saveCellChanges(changes) {
            if (!changes || changes.length === 0) return;
            
            const change = changes[0];
            const [row, col, oldValue, newValue] = change;
            
            if (oldValue === newValue) return;
            
            // 预览列是只读的，不保存
            const previewColumns = this.selectedSheet === '场景汇总'
                ? ['场景图预览']
                : ['图像预览', '首帧预览', '末帧预览', '视频预览'];
            const colHeader = this.hotInstance.getColHeader(col);
            if (previewColumns.includes(colHeader)) {
                return;
            }
            
            const rowData = {};
            const columns = Object.keys(this.excelData[this.selectedSheet][row] || {});
            
            // 获取整行数据（排除预览列）
            const data = this.hotInstance.getDataAtRow(row);
            columns.forEach((colName, idx) => {
                if (!previewColumns.includes(colName)) {
                    rowData[colName] = data[idx] || '';
                }
            });
            
            try {
                const response = await fetch('/api/excel/write', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify({
                        sheet_name: this.selectedSheet,
                        row_index: row,
                        row_data: rowData
                    })
                });
                
                const data = await response.json();
                if (!response.ok) {
                    console.error('保存失败:', data.error);
                } else {
                    // 如果是图像汇总且分镜号改变，重新加载以更新预览
                    if (this.selectedSheet === '图像汇总' && colHeader === '分镜号') {
                        await this.loadExcel();
                    }
                }
            } catch (error) {
                console.error('保存错误:', error);
            }
        },
        
        async addRow(index) {
            try {
                const columns = Object.keys(this.excelData[this.selectedSheet][0] || {});
                const rowData = {};
                columns.forEach(col => {
                    rowData[col] = '';
                });
                
                const response = await fetch('/api/excel/add_row', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify({
                        sheet_name: this.selectedSheet,
                        row_data: rowData
                    })
                });
                
                const data = await response.json();
                if (response.ok) {
                    await this.loadExcel();
                } else {
                    console.error('添加行失败:', data.error);
                }
            } catch (error) {
                console.error('添加行错误:', error);
            }
        },
        
        async deleteRow(index) {
            try {
                const response = await fetch('/api/excel/delete_row', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify({
                        sheet_name: this.selectedSheet,
                        row_index: index
                    })
                });
                
                const data = await response.json();
                if (!response.ok) {
                    console.error('删除行失败:', data.error);
                }
            } catch (error) {
                console.error('删除行错误:', error);
            }
        },
        
        async saveExcel() {
            // Excel数据已通过afterChange自动保存
            alert('Excel数据已自动保存');
        },
        
        async generateImage() {
            try {
                const response = await fetch('/api/generate/image', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify({
                        output_dir: this.generateConfig.image.outputDir,
                        episode_filter: this.generateConfig.image.episodeFilter || null,
                        shot_filter: this.generateConfig.image.shotFilter || null,
                        generator_type: this.generateConfig.image.generatorType,
                        comfyui_server: this.generateConfig.image.comfyuiServer,
                        generate_reference: this.generateConfig.image.generateReference,
                        generate_first_frame: this.generateConfig.image.generateFirstFrame,
                        generate_last_frame: this.generateConfig.image.generateLastFrame,
                        enable_prompt_expansion: this.generateConfig.image.enablePromptExpansion
                    })
                });
                
                const data = await response.json();
                if (response.ok) {
                    alert(`任务已创建: ${data.task_id}`);
                    this.activeTab = 'tasks';
                    await this.loadTasks();
                } else {
                    alert('创建任务失败: ' + (data.error || '未知错误'));
                }
            } catch (error) {
                alert('网络错误: ' + error.message);
            }
        },

        // 生成场景汇总表中的场景图（根据 scene.图像提示词 + scene.参考图）
        async generateSceneImages() {
            try {
                const response = await fetch('/api/generate/scene_images', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify({
                        output_dir: this.generateConfig.scene.outputDir,
                        episode_filter: this.generateConfig.scene.episodeFilter || null,
                        scene_filter: this.generateConfig.scene.sceneFilter || null,
                        generator_type: this.generateConfig.scene.generatorType,
                        comfyui_server: this.generateConfig.scene.comfyuiServer
                    })
                });

                const data = await response.json();
                if (response.ok) {
                    alert(`任务已创建: ${data.task_id}`);
                    this.activeTab = 'tasks';
                    await this.loadTasks();
                } else {
                    alert('创建任务失败: ' + (data.error || '未知错误'));
                }
            } catch (error) {
                alert('网络错误: ' + error.message);
            }
        },
        
        // 生成单个分镜的图像
        async generateSingleImage({ episodeId, shotId, generateReference, generateFirstFrame, generateLastFrame }) {
            try {
                const response = await fetch('/api/generate/image', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify({
                        output_dir: this.generateConfig.image.outputDir,
                        episode_filter: episodeId,
                        shot_filter: shotId, // 需要后端支持这个参数
                        generator_type: this.generateConfig.image.generatorType,
                        comfyui_server: this.generateConfig.image.comfyuiServer,
                        generate_reference: generateReference || false,
                        generate_first_frame: generateFirstFrame || false,
                        generate_last_frame: generateLastFrame || false,
                        enable_prompt_expansion: this.generateConfig.image.enablePromptExpansion
                    })
                });
                
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || '创建任务失败');
                }
                return data;
            } catch (error) {
                console.error('生成图像失败:', error);
                throw error;
            }
        },
        
        // 生成单个分镜的视频
        async generateSingleVideo({ episodeId, shotId }) {
            try {
                const response = await fetch('/api/generate/video', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify({
                        output_dir: this.generateConfig.video.outputDir,
                        episode_filter: episodeId,
                        shot_filter: shotId,
                        generator_type: this.generateConfig.video.generatorType,
                        comfyui_server: this.generateConfig.video.comfyuiServer,
                        enable_prompt_expansion: this.generateConfig.video.enablePromptExpansion
                    })
                });
                
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || '创建任务失败');
                }
                return data;
            } catch (error) {
                console.error('生成视频失败:', error);
                throw error;
            }
        },
        
        async generateVideo() {
            try {
                const response = await fetch('/api/generate/video', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify({
                        output_dir: this.generateConfig.video.outputDir,
                        episode_filter: this.generateConfig.video.episodeFilter || null,
                        shot_filter: this.generateConfig.video.shotFilter || null,
                        generator_type: this.generateConfig.video.generatorType,
                        comfyui_server: this.generateConfig.video.comfyuiServer,
                        enable_prompt_expansion: this.generateConfig.video.enablePromptExpansion
                    })
                });
                
                const data = await response.json();
                if (response.ok) {
                    alert(`任务已创建: ${data.task_id}`);
                    this.activeTab = 'tasks';
                    await this.loadTasks();
                } else {
                    alert('创建任务失败: ' + (data.error || '未知错误'));
                }
            } catch (error) {
                alert('网络错误: ' + error.message);
            }
        },
        
        async generateAudio() {
            try {
                const response = await fetch('/api/generate/audio', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Session-ID': this.sessionId
                    },
                    body: JSON.stringify({
                        output_dir: this.generateConfig.audio.outputDir,
                        episode_filter: this.generateConfig.audio.episodeFilter || null,
                        shot_filter: this.generateConfig.audio.shotFilter || null,
                        generator_type: this.generateConfig.audio.generatorType,
                        comfyui_server: this.generateConfig.audio.comfyuiServer,
                        workflow_path: this.generateConfig.audio.workflowPath || null
                    })
                });
                
                const data = await response.json();
                if (response.ok) {
                    alert(`任务已创建: ${data.task_id}`);
                    this.activeTab = 'tasks';
                    await this.loadTasks();
                } else {
                    alert('创建任务失败: ' + (data.error || '未知错误'));
                }
            } catch (error) {
                alert('网络错误: ' + error.message);
            }
        },
        
        async loadTasks() {
            try {
                const response = await fetch('/api/tasks', {
                    headers: {
                        'X-Session-ID': this.sessionId
                    }
                });
                
                const data = await response.json();
                if (response.ok) {
                    this.tasks = (data.tasks || []).sort((a, b) => 
                        new Date(b.created_at) - new Date(a.created_at)
                    );
                    console.log(`[任务列表] 加载了 ${this.tasks.length} 个任务`);
                } else {
                    console.error('加载任务失败:', data.error || '未知错误');
                    this.tasks = [];
                }
            } catch (error) {
                console.error('加载任务失败:', error);
                this.tasks = [];
            }
        },
        
        initSocket() {
            if (this.socket) {
                this.socket.close();
            }
            
            // 使用原生WebSocket连接
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/ws`;
            this.socket = new WebSocket(wsUrl);
            
            this.socket.onopen = () => {
                console.log('WebSocket连接成功');
            };
            
            this.socket.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    
                    if (message.type === 'excel_updated') {
                        const data = message.data;
                        if (data.sheet_name === this.selectedSheet) {
                            this.loadExcel();
                        }
                    } else if (message.type === 'refresh_preview') {
                        // 生成任务完成，刷新Excel预览
                        const data = message.data;
                        console.log('[WebSocket] 收到刷新预览通知:', data);
                        // 如果当前在Excel编辑页面，重新加载Excel数据以刷新预览
                        if (this.activeTab === 'excel') {
                            console.log('[WebSocket] 刷新Excel预览...');
                            // 延迟刷新，确保文件已完全写入（图片生成需要更长时间）
                            const delay = (data.task_type === 'image' || data.task_type === 'scene') ? 3000 : 1500;
                            setTimeout(() => {
                                console.log('[WebSocket] 开始刷新Excel数据...');
                                // 强制重新加载Excel数据
                                this.excelLoaded = false;
                                this.loadExcel().then(() => {
                                    console.log('[WebSocket] Excel数据刷新完成');
                                }).catch(err => {
                                    console.error('[WebSocket] Excel数据刷新失败:', err);
                                });
                            }, delay);
                        }
                    } else if (message.type === 'task_update') {
                        // 更新任务列表中的任务
                        const task = message.data;
                        console.log('[WebSocket] 收到任务更新:', task);
                        const index = this.tasks.findIndex(t => t.id === task.id);
                        if (index >= 0) {
                            // 更新现有任务
                            this.tasks[index] = task;
                            // 如果任务完成且当前在Excel编辑页面，刷新预览
                            if (task.status === 'completed' && this.activeTab === 'excel') {
                                console.log('[WebSocket] 任务完成，刷新Excel预览...');
                                // 延迟一下，确保文件已写入（图片生成可能需要更长时间）
                                const delay = task.type === 'image' ? 2000 : 1000;
                                setTimeout(() => {
                                    this.loadExcel();
                                }, delay);
                            }
                        } else {
                            // 如果是新任务，添加到列表开头
                            this.tasks.unshift(task);
                            // 重新排序
                            this.tasks.sort((a, b) => 
                                new Date(b.created_at) - new Date(a.created_at)
                            );
                            console.log(`[WebSocket] 新任务已添加，共 ${this.tasks.length} 个任务`);
                        }
                        console.log(`[WebSocket] 任务列表已更新，共 ${this.tasks.length} 个任务`);
                    }
                } catch (e) {
                    console.error('解析WebSocket消息失败:', e);
                }
            };
            
            this.socket.onerror = (error) => {
                console.error('WebSocket错误:', error);
            };
            
            this.socket.onclose = () => {
                console.log('WebSocket连接关闭');
                // 尝试重连
                setTimeout(() => {
                    if (this.isAuthenticated) {
                        this.initSocket();
                    }
                }, 3000);
            };
        },
        
        joinTaskRoom(taskId) {
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify({
                    type: 'join_task',
                    task_id: taskId
                }));
            }
        },
        
        leaveTaskRoom(taskId) {
            if (this.socket && this.socket.readyState === WebSocket.OPEN) {
                this.socket.send(JSON.stringify({
                    type: 'leave_task',
                    task_id: taskId
                }));
            }
        }
    }
}).mount('#app');

