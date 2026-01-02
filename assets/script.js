// 全局状态
let apiConfigs = [];
let templates = [];
let tabs = []; // [{ templateName, tabId, history }]
let activeTabId = null;
let tabCounter = 0;

// 从 localStorage 加载历史记录（按模板分组）
function loadHistoryFromStorage() {
    const stored = localStorage.getItem('llm_history');
    if (!stored) return {};

    try {
        const allHistory = JSON.parse(stored);
        // 按模板分组历史记录
        const historyByTemplate = {};
        allHistory.forEach(item => {
            const templateName = item.template_name || 'default';
            if (!historyByTemplate[templateName]) {
                historyByTemplate[templateName] = [];
            }
            historyByTemplate[templateName].push(item);
        });
        return historyByTemplate;
    } catch (e) {
        console.error('Failed to load history:', e);
        return {};
    }
}

// 保存历史记录到 localStorage
function saveHistoryToStorage() {
    const allHistory = [];
    tabs.forEach(tab => {
        if (tab.history) {
            allHistory.push(...tab.history);
        }
    });
    // 保持最后 100 条记录
    allHistory.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    const limited = allHistory.slice(0, 100);
    localStorage.setItem('llm_history', JSON.stringify(limited));
}

// 加载 API 配置
async function loadApiConfigs() {
    try {
        const response = await fetch('/api/configs');
        const data = await response.json();
        apiConfigs = data.configs || [];
        return apiConfigs;
    } catch (error) {
        console.error('Failed to load API configurations:', error);
        return [];
    }
}

// 加载模板列表
async function loadTemplates() {
    try {
        const response = await fetch('/api/templates');
        const data = await response.json();
        templates = data.templates || [];
        return templates;
    } catch (error) {
        console.error('Failed to load templates:', error);
        return [];
    }
}

// 加载模板内容
async function loadTemplateContent(templateName) {
    try {
        const response = await fetch(`/api/templates/${templateName}`);
        if (!response.ok) {
            throw new Error('Failed to load template');
        }
        const data = await response.json();
        return data.content;
    } catch (error) {
        console.error('Failed to load template content:', error);
        return null;
    }
}

// 创建新标签页
function createTab(templateName) {
    const tabId = `tab-${tabCounter++}`;
    const tab = {
        templateName,
        tabId,
        history: []
    };

    tabs.push(tab);

    // 从存储中加载该模板的历史记录
    const historyByTemplate = loadHistoryFromStorage();
    if (historyByTemplate[templateName]) {
        tab.history = historyByTemplate[templateName];
    }

    // 创建标签按钮
    const tabButton = document.createElement('button');
    tabButton.className = 'tab-button';
    tabButton.dataset.tabId = tabId;
    tabButton.innerHTML = `
        <span>${templateName}</span>
        <span class="close-btn" onclick="event.stopPropagation(); closeTab('${tabId}')">×</span>
    `;
    tabButton.addEventListener('click', () => switchTab(tabId));

    const tabsHeader = document.getElementById('tabsHeader');
    tabsHeader.appendChild(tabButton);

    // 创建标签内容
    const tabTemplate = document.getElementById('tabTemplate');
    const tabContent = tabTemplate.content.cloneNode(true).querySelector('.tab-content');
    tabContent.dataset.tabId = tabId;
    tabContent.dataset.templateName = templateName;

    const tabsContent = document.getElementById('tabsContent');
    tabsContent.appendChild(tabContent);

    // 初始化标签页内容
    initializeTabContent(tabId, templateName);

    // 切换到新标签页
    switchTab(tabId);

    return tabId;
}

// 初始化标签页内容
async function initializeTabContent(tabId, templateName) {
    const tabContent = document.querySelector(`.tab-content[data-tab-id="${tabId}"]`);
    if (!tabContent) return;

    // 设置模板名称显示
    const templateNameDisplay = tabContent.querySelector('.template-name-display');
    templateNameDisplay.textContent = templateName;

    // 加载模板内容并显示预览
    const templateContent = await loadTemplateContent(templateName);
    if (templateContent) {
        const templatePreview = tabContent.querySelector('.template-preview');
        const highlightedContent = templateContent
            .replace(/\{input_txt\}/g, '<span class="template-preview-placeholder">{input_txt}</span>')
            .replace(/\{input2_txt\}/g, '<span class="template-preview-placeholder">{input2_txt}</span>')
            .replace(/\{input3_txt\}/g, '<span class="template-preview-placeholder">{input3_txt}</span>');
        templatePreview.innerHTML = highlightedContent;
        templatePreview.style.display = 'block';

        // 检查是否需要显示 input2 和 input3
        const hasInput2 = templateContent.includes('{input2_txt}');
        const hasInput3 = templateContent.includes('{input3_txt}');
        tabContent.querySelector('.inputText2Group').style.display = hasInput2 ? 'block' : 'none';
        tabContent.querySelector('.inputText3Group').style.display = hasInput3 ? 'block' : 'none';
    }

    // 填充 API 配置选择器
    const apiConfigSelect = tabContent.querySelector('.apiConfig');
    apiConfigSelect.innerHTML = '';
    apiConfigs.forEach((config, index) => {
        const option = document.createElement('option');
        option.value = index;
        option.textContent = config.name;
        apiConfigSelect.appendChild(option);
    });
    if (apiConfigs.length > 0) {
        apiConfigSelect.value = '0';
    }

    // 设置温度滑块事件
    const temperatureSlider = tabContent.querySelector('.temperature');
    const temperatureValue = tabContent.querySelector('.temperature-value');
    const temperatureGroup = temperatureSlider.closest('.input-group');
    const temperatureLabel = temperatureGroup.querySelector('label');

    // 更新 temperature 控件状态的函数
    function updateTemperatureControl() {
        const selectedIndex = parseInt(apiConfigSelect.value);
        if (isNaN(selectedIndex) || selectedIndex < 0 || selectedIndex >= apiConfigs.length) {
            return;
        }
        const selectedConfig = apiConfigs[selectedIndex];
        const hasTemperature = selectedConfig.default_temperature !== undefined && selectedConfig.default_temperature !== null;

        if (hasTemperature) {
            // 启用 temperature 控件
            temperatureSlider.disabled = false;
            temperatureSlider.style.opacity = '1';
            temperatureSlider.style.cursor = 'pointer';
            temperatureLabel.style.opacity = '1';

            // 设置默认值
            const defaultTemp = selectedConfig.default_temperature;
            temperatureSlider.value = defaultTemp;
            temperatureValue.textContent = parseFloat(defaultTemp).toFixed(1);
        } else {
            // 禁用 temperature 控件
            temperatureSlider.disabled = true;
            temperatureSlider.style.opacity = '0.5';
            temperatureSlider.style.cursor = 'not-allowed';
            temperatureLabel.style.opacity = '0.5';
        }
    }

    // 初始化 temperature 控件状态
    updateTemperatureControl();

    // 当 API 配置改变时，更新 temperature 控件状态
    apiConfigSelect.addEventListener('change', updateTemperatureControl);

    temperatureSlider.addEventListener('input', (e) => {
        temperatureValue.textContent = parseFloat(e.target.value).toFixed(1);
    });

    // 设置提交按钮事件
    const submitBtn = tabContent.querySelector('.submitBtn');
    submitBtn.addEventListener('click', () => submitPrompt(tabId));

    // 设置输入框 Enter 键事件
    const inputText = tabContent.querySelector('.inputText');
    inputText.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            submitPrompt(tabId);
        }
    });

    // 加载历史记录
    loadTabHistory(tabId);
}

// 切换标签页
function switchTab(tabId) {
    activeTabId = tabId;

    // 更新标签按钮状态
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tabId === tabId);
    });

    // 更新标签内容显示
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('active', content.dataset.tabId === tabId);
    });
}

// 关闭标签页
function closeTab(tabId) {
    const tabIndex = tabs.findIndex(t => t.tabId === tabId);
    if (tabIndex === -1) return;

    // 如果只有一个标签页，不允许关闭
    if (tabs.length <= 1) {
        alert('至少需要保留一个标签页');
        return;
    }

    // 保存该标签页的历史记录
    saveHistoryToStorage();

    // 移除标签按钮
    const tabButton = document.querySelector(`.tab-button[data-tab-id="${tabId}"]`);
    if (tabButton) tabButton.remove();

    // 移除标签内容
    const tabContent = document.querySelector(`.tab-content[data-tab-id="${tabId}"]`);
    if (tabContent) tabContent.remove();

    // 从 tabs 数组中移除
    tabs.splice(tabIndex, 1);

    // 如果关闭的是当前活动标签页，切换到第一个标签页
    if (activeTabId === tabId && tabs.length > 0) {
        switchTab(tabs[0].tabId);
    }
}

// 加载标签页历史记录
function loadTabHistory(tabId) {
    const tab = tabs.find(t => t.tabId === tabId);
    if (!tab) return;

    const tabContent = document.querySelector(`.tab-content[data-tab-id="${tabId}"]`);
    if (!tabContent) return;

    const historyDiv = tabContent.querySelector('.history');
    const history = tab.history || [];

    if (history.length === 0) {
        historyDiv.innerHTML = '<p style="color: #999; font-style: italic;">暂无历史记录</p>';
        return;
    }

    historyDiv.innerHTML = history.map((item, index) => {
        let apiInfo = '';
        if (item.config_id) {
            const config = apiConfigs.find(c => c.id === item.config_id);
            if (config) {
                apiInfo = ` • API: ${config.name}`;
            }
        }

        return `
        <div class="history-item">
            <div class="history-item-header">
                <div style="flex: 1;" onclick="loadHistoryItem('${tabId}', ${index})">
                    <div class="history-prompt">${escapeHtml(item.prompt || item.input_texts?.join(' | ') || '')}</div>
                    <div class="history-response">${escapeHtml((item.response || '').substring(0, 150))}${(item.response || '').length > 150 ? '...' : ''}</div>
                    <div class="history-meta">${item.temperature !== undefined ? `Temp: ${item.temperature}` : ''}${apiInfo} • ${new Date(item.timestamp).toLocaleString()}</div>
                </div>
                <button class="history-delete-btn" onclick="event.stopPropagation(); deleteHistoryItem('${tabId}', ${index})" title="删除">×</button>
            </div>
        </div>
    `;
    }).join('');
}

// 加载历史记录项
async function loadHistoryItem(tabId, index) {
    const tab = tabs.find(t => t.tabId === tabId);
    if (!tab || !tab.history || index >= tab.history.length) return;

    const item = tab.history[index];
    const tabContent = document.querySelector(`.tab-content[data-tab-id="${tabId}"]`);
    if (!tabContent) return;

    // 加载 API 配置
    if (item.config_id) {
        const configIndex = apiConfigs.findIndex(config => config.id === item.config_id);
        if (configIndex >= 0) {
            tabContent.querySelector('.apiConfig').value = configIndex;
        }
    }

    // 加载输入文本
    const inputTexts = item.input_texts || [];
    if (inputTexts.length > 0) {
        tabContent.querySelector('.inputText').value = inputTexts[0] || '';
        tabContent.querySelector('.inputText2').value = inputTexts[1] || '';
        tabContent.querySelector('.inputText3').value = inputTexts[2] || '';
    }

    // 加载温度（如果配置支持）
    const apiConfigSelect = tabContent.querySelector('.apiConfig');
    const selectedIndex = parseInt(apiConfigSelect.value);
    if (!isNaN(selectedIndex) && selectedIndex >= 0 && selectedIndex < apiConfigs.length) {
        const selectedConfig = apiConfigs[selectedIndex];
        if (selectedConfig.default_temperature !== undefined && selectedConfig.default_temperature !== null) {
            const temperature = item.temperature !== undefined ? item.temperature : selectedConfig.default_temperature;
            tabContent.querySelector('.temperature').value = temperature;
            tabContent.querySelector('.temperature-value').textContent = parseFloat(temperature).toFixed(1);
        }
    }

    // 显示响应
    tabContent.querySelector('.response').textContent = item.response || '';
    tabContent.querySelector('.response').classList.remove('loading');
    tabContent.querySelector('.error').style.display = 'none';
}

// 删除历史记录项
function deleteHistoryItem(tabId, index) {
    if (!confirm('确定要删除这条历史记录吗？')) return;

    const tab = tabs.find(t => t.tabId === tabId);
    if (!tab || !tab.history || index >= tab.history.length) return;

    tab.history.splice(index, 1);
    saveHistoryToStorage();
    loadTabHistory(tabId);
}

// 提交提示
async function submitPrompt(tabId) {
    const tab = tabs.find(t => t.tabId === tabId);
    if (!tab) return;

    const tabContent = document.querySelector(`.tab-content[data-tab-id="${tabId}"]`);
    if (!tabContent) return;

    const templateName = tab.templateName;
    const temperature = parseFloat(tabContent.querySelector('.temperature').value);
    const submitBtn = tabContent.querySelector('.submitBtn');
    const responseDiv = tabContent.querySelector('.response');
    const errorDiv = tabContent.querySelector('.error');

    // 收集输入文本
    const inputText1 = tabContent.querySelector('.inputText').value.trim();
    const inputText2 = tabContent.querySelector('.inputText2').value.trim();
    const inputText3 = tabContent.querySelector('.inputText3').value.trim();

    if (!inputText1) {
        alert('请输入输入文本');
        return;
    }

    // 检查是否需要 input2 和 input3
    const templateContent = await loadTemplateContent(templateName);
    const hasInput2 = templateContent && templateContent.includes('{input2_txt}');
    const hasInput3 = templateContent && templateContent.includes('{input3_txt}');

    const input_texts = [inputText1];
    if (hasInput2) {
        if (!inputText2) {
            alert('请输入 Input Text 2 (用于 {input2_txt})');
            return;
        }
        input_texts.push(inputText2);
    }
    if (hasInput3) {
        if (!inputText3) {
            alert('请输入 Input Text 3 (用于 {input3_txt})');
            return;
        }
        if (!hasInput2 && input_texts.length === 1) {
            input_texts.push(inputText1);
        }
        input_texts.push(inputText3);
    }

    // 获取选中的 API 配置
    const apiConfigIndex = parseInt(tabContent.querySelector('.apiConfig').value);
    if (isNaN(apiConfigIndex) || apiConfigIndex < 0 || apiConfigIndex >= apiConfigs.length) {
        alert('请选择 API & Model 配置');
        return;
    }
    const currentApiConfig = apiConfigs[apiConfigIndex];

    // 准备请求
    const requestBody = {
        template_name: templateName,
        input_texts,
        config_id: currentApiConfig.id
    };

    // 只有当配置支持 temperature 时才添加 temperature 参数
    if (currentApiConfig.default_temperature !== undefined && currentApiConfig.default_temperature !== null) {
        requestBody.temperature = temperature;
    }

    submitBtn.disabled = true;
    responseDiv.textContent = '';
    responseDiv.classList.add('loading');
    responseDiv.textContent = '加载中...';
    errorDiv.style.display = 'none';

    try {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody)
        });

        if (!response.ok) {
            const contentType = response.headers.get('content-type');
            let errorMessage = '请求失败';

            if (contentType && contentType.includes('application/json')) {
                try {
                    const error = await response.json();
                    errorMessage = error.error || errorMessage;
                } catch (e) {
                    // Ignore
                }
            } else {
                try {
                    const text = await response.text();
                    if (text.includes('<html>')) {
                        const titleMatch = text.match(/<title>(.*?)<\/title>/i);
                        const h1Match = text.match(/<h1>(.*?)<\/h1>/i);
                        errorMessage = titleMatch ? titleMatch[1] : (h1Match ? h1Match[1] : `服务器错误 (${response.status})`);
                    } else {
                        errorMessage = text || `服务器错误 (${response.status})`;
                    }
                } catch (e) {
                    errorMessage = `服务器错误 (${response.status} ${response.statusText})`;
                }
            }

            throw new Error(errorMessage);
        }

        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }

        const fullResponse = data.response || '';
        responseDiv.textContent = fullResponse;
        responseDiv.classList.remove('loading');

        // 保存到历史记录
        const historyItem = {
            prompt: `[${templateName}] ${input_texts.join(' | ')}`,
            response: fullResponse,
            template_name: templateName,
            input_texts,
            config_id: currentApiConfig ? currentApiConfig.id : null,
            timestamp: new Date().toISOString()
        };

        // 只有当配置支持 temperature 时才保存 temperature
        if (currentApiConfig && currentApiConfig.default_temperature !== undefined && currentApiConfig.default_temperature !== null) {
            historyItem.temperature = temperature;
        }

        if (!tab.history) {
            tab.history = [];
        }
        tab.history.unshift(historyItem);
        // 每个标签页最多保留 50 条记录
        if (tab.history.length > 50) {
            tab.history = tab.history.slice(0, 50);
        }

        saveHistoryToStorage();
        loadTabHistory(tabId);

    } catch (error) {
        errorDiv.textContent = `错误: ${error.message}`;
        errorDiv.style.display = 'block';
        responseDiv.textContent = '';
        responseDiv.classList.remove('loading');
    } finally {
        submitBtn.disabled = false;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// 添加新标签页（从模板选择）
function addNewTab(templateName) {
    if (!templateName) return;

    // 检查该模板是否已经打开
    const existingTab = tabs.find(t => t.templateName === templateName);
    if (existingTab) {
        switchTab(existingTab.tabId);
        // 重置选择器
        document.getElementById('templateSelector').value = '';
        return;
    }

    createTab(templateName);
    // 重置选择器
    document.getElementById('templateSelector').value = '';
}

// 初始化页面
async function initializePage() {
    // 加载 API 配置和模板
    await loadApiConfigs();
    await loadTemplates();

    // 设置模板选择器
    const templateSelector = document.getElementById('templateSelector');
    templates.forEach(template => {
        const option = document.createElement('option');
        option.value = template;
        option.textContent = template;
        templateSelector.appendChild(option);
    });

    templateSelector.addEventListener('change', (e) => {
        if (e.target.value) {
            addNewTab(e.target.value);
        }
    });

    // 从存储中加载历史记录，为有历史记录的模板创建标签页
    const historyByTemplate = loadHistoryFromStorage();
    const templatesWithHistory = Object.keys(historyByTemplate);

    if (templatesWithHistory.length > 0) {
        // 为有历史记录的模板创建标签页
        templatesWithHistory.forEach(templateName => {
            // 确保模板仍然存在
            if (templates.includes(templateName)) {
                createTab(templateName);
            }
        });
    }

    // 如果没有标签页被创建（没有历史记录），创建第一个模板的标签页
    if (tabs.length === 0 && templates.length > 0) {
        createTab(templates[0]);
    } else if (templates.length === 0) {
        alert('没有可用的模板');
    }
}

// 页面加载完成后初始化
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePage);
} else {
    initializePage();
}
