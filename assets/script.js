let history = JSON.parse(localStorage.getItem('llm_history') || '[]');
let currentTemplateName = null;
let templateHasInput2 = false;
let templateHasInput3 = false;
let apiConfigs = [];
let currentApiConfig = null;

// Load API configurations on page load
async function loadApiConfigs() {
    try {
        const response = await fetch('/api/configs');
        const data = await response.json();
        apiConfigs = data.configs || [];
        const select = document.getElementById('apiConfig');

        // Clear existing options
        select.innerHTML = '';

        if (apiConfigs.length === 0) {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = '-- No configurations available --';
            select.appendChild(option);
            return;
        }

        // Add options for each configuration
        apiConfigs.forEach((config, index) => {
            const option = document.createElement('option');
            option.value = index;
            option.textContent = config.name;
            select.appendChild(option);
        });

        // Set default selection (first one)
        if (apiConfigs.length > 0) {
            select.value = '0';
            currentApiConfig = apiConfigs[0];
        }
    } catch (error) {
        console.error('Failed to load API configurations:', error);
        const select = document.getElementById('apiConfig');
        select.innerHTML = '<option value="">-- Error loading configurations --</option>';
    }
}

// Handle API config selection change
function setupApiConfigSelector() {
    const apiConfigSelect = document.getElementById('apiConfig');
    if (apiConfigSelect) {
        apiConfigSelect.addEventListener('change', (e) => {
            const index = parseInt(e.target.value);
            if (!isNaN(index) && index >= 0 && index < apiConfigs.length) {
                currentApiConfig = apiConfigs[index];
            } else {
                currentApiConfig = null;
            }
        });
    }
}

// Load templates on page load
async function loadTemplates() {
    try {
        const response = await fetch('/api/templates');
        const data = await response.json();
        const select = document.getElementById('template');

        // Clear existing options except the first one
        while (select.options.length > 1) {
            select.remove(1);
        }

        data.templates.forEach(template => {
            const option = document.createElement('option');
            option.value = template;
            option.textContent = template;
            select.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load templates:', error);
    }
}

// Load selected template
async function loadTemplate() {
    const templateName = document.getElementById('template').value;
    const previewDiv = document.getElementById('templatePreview');

    if (!templateName) {
        currentTemplateName = null;
        templateHasInput2 = false;
        templateHasInput3 = false;
        document.getElementById('inputTextGroup').style.display = 'none';
        document.getElementById('inputText2Group').style.display = 'none';
        document.getElementById('inputText3Group').style.display = 'none';
        document.getElementById('inputText').value = '';
        document.getElementById('inputText2').value = '';
        document.getElementById('inputText3').value = '';
        previewDiv.style.display = 'none';
        return;
    }

    try {
        const response = await fetch(`/api/templates/${templateName}`);
        if (!response.ok) {
            throw new Error('Failed to load template');
        }

        const data = await response.json();
        currentTemplateName = templateName;
        templateHasInput2 = data.content.includes('{input2_txt}');
        templateHasInput3 = data.content.includes('{input3_txt}');

        // Display template preview with highlighted placeholders
        const templateContent = data.content;
        const highlightedContent = templateContent
            .replace(/\{input_txt\}/g, '<span class="template-preview-placeholder">{input_txt}</span>')
            .replace(/\{input2_txt\}/g, '<span class="template-preview-placeholder">{input2_txt}</span>')
            .replace(/\{input3_txt\}/g, '<span class="template-preview-placeholder">{input3_txt}</span>');

        previewDiv.innerHTML = highlightedContent;
        previewDiv.style.display = 'block';

        // Always show input text field when template is loaded
        document.getElementById('inputTextGroup').style.display = 'block';
        document.getElementById('inputText2Group').style.display = templateHasInput2 ? 'block' : 'none';
        document.getElementById('inputText3Group').style.display = templateHasInput3 ? 'block' : 'none';
        document.getElementById('inputText').focus();
    } catch (error) {
        alert(`Error loading template: ${error.message}`);
        currentTemplateName = null;
        templateHasInput2 = false;
        templateHasInput3 = false;
        document.getElementById('inputTextGroup').style.display = 'none';
        document.getElementById('inputText2Group').style.display = 'none';
        document.getElementById('inputText3Group').style.display = 'none';
        previewDiv.style.display = 'none';
    }
}

// Update temperature display
document.getElementById('temperature').addEventListener('input', (e) => {
    document.getElementById('tempValue').textContent = parseFloat(e.target.value).toFixed(1);
});

// Auto-load template when dropdown changes
document.getElementById('template').addEventListener('change', (e) => {
    if (!e.target.value) {
        currentTemplateName = null;
        templateHasInput2 = false;
        templateHasInput3 = false;
        document.getElementById('inputTextGroup').style.display = 'none';
        document.getElementById('inputText2Group').style.display = 'none';
        document.getElementById('inputText3Group').style.display = 'none';
        document.getElementById('inputText').value = '';
        document.getElementById('inputText2').value = '';
        document.getElementById('inputText3').value = '';
        document.getElementById('templatePreview').style.display = 'none';
    } else {
        // Auto-load the selected template
        loadTemplate();
    }
});

// Load history on page load
function loadHistory() {
    const historyDiv = document.getElementById('history');
    if (history.length === 0) {
        historyDiv.innerHTML = '<p style="color: #999; font-style: italic;">No history yet</p>';
        return;
    }

    historyDiv.innerHTML = history.map((item, index) => {
        // Find config name from config_id
        let apiInfo = '';
        if (item.config_id) {
            const config = apiConfigs.find(c => c.id === item.config_id);
            if (config) {
                apiInfo = ` • API: ${config.name}`;
            }
        } else if (item.api_config) {
            // Fallback for old format
            apiInfo = ` • API: ${item.api_config.name}`;
        }
        return `
        <div class="history-item">
            <div class="history-item-header">
                <div style="flex: 1;" onclick="loadHistoryItem(${index})">
                    <div class="history-prompt">${escapeHtml(item.prompt)}</div>
                    <div class="history-response">${escapeHtml(item.response.substring(0, 150))}${item.response.length > 150 ? '...' : ''}</div>
                    <div class="history-meta">Temp: ${item.temperature}${apiInfo} • ${new Date(item.timestamp).toLocaleString()}</div>
                </div>
                <button class="history-delete-btn" onclick="event.stopPropagation(); deleteHistoryItem(${index})" title="Delete">×</button>
            </div>
        </div>
    `;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function deleteHistoryItem(index) {
    if (confirm('Are you sure you want to delete this history item?')) {
        history.splice(index, 1);
        localStorage.setItem('llm_history', JSON.stringify(history));
        loadHistory();
    }
}

async function loadHistoryItem(index) {
    const item = history[index];

    // Load API configuration from history
    if (item.config_id) {
        // New format: find config by ID
        const configIndex = apiConfigs.findIndex(config => config.id === item.config_id);
        if (configIndex >= 0) {
            document.getElementById('apiConfig').value = configIndex;
            currentApiConfig = apiConfigs[configIndex];
        }
    } else if (item.api_config) {
        // Fallback for old format: try to find matching config
        // Try exact match first (api_url, model, and api_key_name)
        const exactMatch = apiConfigs.findIndex(config =>
            config.api_url === item.api_config.api_url &&
            config.model === item.api_config.model &&
            (config.api_key_name || null) === (item.api_config.api_key_name || null)
        );
        if (exactMatch >= 0) {
            document.getElementById('apiConfig').value = exactMatch;
            currentApiConfig = apiConfigs[exactMatch];
        } else {
            // If exact match not found, try match by api_url and model only
            const matchingIndex = apiConfigs.findIndex(config =>
                config.api_url === item.api_config.api_url &&
                config.model === item.api_config.model
            );
            if (matchingIndex >= 0) {
                document.getElementById('apiConfig').value = matchingIndex;
                currentApiConfig = apiConfigs[matchingIndex];
            } else {
                // If still not found, try to find by name or use first available
                const nameMatch = apiConfigs.findIndex(config =>
                    config.name === item.api_config.name
                );
                if (nameMatch >= 0) {
                    document.getElementById('apiConfig').value = nameMatch;
                    currentApiConfig = apiConfigs[nameMatch];
                }
            }
        }
    }

    // Load template and input text from history
    if (item.template_name) {
        // New format with template_name field
        document.getElementById('template').value = item.template_name;
        await loadTemplate();
        let texts = item.input_texts || [];
        if ((!texts || texts.length === 0) && item.input_text) {
            // Fallback for older saved format with single input_text
            texts = [item.input_text];
        }
        if ((!texts || texts.length === 0) && item.prompt) {
            // Last resort: try parsing from prompt
            const parsed = item.prompt.replace(/^\[Template: .+?\] /, '').split(' | ');
            if (parsed.length > 0 && parsed[0].trim()) {
                texts = parsed;
            }
        }
        document.getElementById('inputText').value = texts[0] || '';
        document.getElementById('inputText2').value = texts[1] || '';
        document.getElementById('inputText3').value = texts[2] || '';
    } else {
        // Old format - try to parse from prompt string
        const templateMatch = item.prompt.match(/^\[Template: (.+?)\]/);
        if (templateMatch) {
            const templateName = templateMatch[1];
            document.getElementById('template').value = templateName;
            await loadTemplate();
            const inputText = item.prompt.replace(/^\[Template: .+?\] /, '');
            document.getElementById('inputText').value = inputText;
            document.getElementById('inputText2').value = '';
            document.getElementById('inputText3').value = '';
        } else {
            alert('This history item does not have template information');
            return;
        }
    }

    document.getElementById('temperature').value = item.temperature;
    document.getElementById('tempValue').textContent = parseFloat(item.temperature).toFixed(1);
    document.getElementById('response').textContent = item.response;
    document.getElementById('response').classList.remove('loading');
    document.getElementById('error').style.display = 'none';
}

async function submitPrompt() {
    const temperature = parseFloat(document.getElementById('temperature').value);
    const submitBtn = document.getElementById('submitBtn');
    const responseDiv = document.getElementById('response');
    const errorDiv = document.getElementById('error');

    // Require template selection
    if (!currentTemplateName) {
        alert('Please select and load a template first');
        return;
    }

    // Collect inputs based on placeholders
    const inputText1 = document.getElementById('inputText').value.trim();
    const inputText2 = document.getElementById('inputText2').value.trim();
    const inputText3 = document.getElementById('inputText3').value.trim();

    if (!inputText1) {
        alert('Please enter input text');
        return;
    }

    const input_texts = [inputText1];
    if (templateHasInput2) {
        if (!inputText2) {
            alert('Please enter Input Text 2 (for {input2_txt})');
            return;
        }
        input_texts.push(inputText2);
    }
    if (templateHasInput3) {
        if (!inputText3) {
            alert('Please enter Input Text 3 (for {input3_txt})');
            return;
        }
        // If template has input3 but not input2, ensure order; push empty second if needed
        if (!templateHasInput2 && input_texts.length === 1) {
            input_texts.push(inputText1);
        }
        input_texts.push(inputText3);
    }

    // Get selected API configuration
    if (!currentApiConfig) {
        alert('Please select an API & Model configuration');
        return;
    }

    // Prepare request payload with template and API config ID
    const requestBody = {
        temperature,
        template_name: currentTemplateName,
        input_texts,
        config_id: currentApiConfig.id
    };

    console.log('Submitting with:', requestBody);

    submitBtn.disabled = true;
    responseDiv.textContent = '';
    responseDiv.classList.add('loading');
    responseDiv.textContent = 'Loading...';
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
            let errorMessage = 'Request failed';

            if (contentType && contentType.includes('application/json')) {
                try {
                    const error = await response.json();
                    errorMessage = error.error || errorMessage;
                } catch (e) {
                    // If JSON parsing fails, fall through to text parsing
                }
            } else {
                // If not JSON, try to read as text
                try {
                    const text = await response.text();
                    // Try to extract meaningful error from HTML or text
                    if (text.includes('<html>')) {
                        // It's an HTML error page, extract title or h1 if available
                        const titleMatch = text.match(/<title>(.*?)<\/title>/i);
                        const h1Match = text.match(/<h1>(.*?)<\/h1>/i);
                        errorMessage = titleMatch ? titleMatch[1] : (h1Match ? h1Match[1] : `Server error (${response.status})`);
                    } else {
                        errorMessage = text || `Server error (${response.status})`;
                    }
                } catch (e) {
                    errorMessage = `Server error (${response.status} ${response.statusText})`;
                }
            }

            throw new Error(errorMessage);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value);
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = line.substring(6);
                    if (data === '[DONE]') {
                        break;
                    }
                    if (data.startsWith('ERROR: ')) {
                        throw new Error(data.substring(7));
                    }
                    fullResponse += data;
                    responseDiv.textContent = fullResponse;
                    responseDiv.classList.remove('loading');
                }
            }
        }

        // Save to history
        const historyItem = {
            prompt: `[Template: ${currentTemplateName}] ${input_texts.join(' | ')}`,
            response: fullResponse,
            temperature,
            template_name: currentTemplateName,
            input_texts,
            config_id: currentApiConfig ? currentApiConfig.id : null,
            timestamp: new Date().toISOString()
        };
        history.unshift(historyItem);
        // Keep only last 20 items
        if (history.length > 20) {
            history = history.slice(0, 20);
        }
        localStorage.setItem('llm_history', JSON.stringify(history));
        loadHistory();

    } catch (error) {
        errorDiv.textContent = `Error: ${error.message}`;
        errorDiv.style.display = 'block';
        responseDiv.textContent = '';
        responseDiv.classList.remove('loading');
    } finally {
        submitBtn.disabled = false;
    }
}

// Allow Enter key to submit in textarea (Shift+Enter for new line)
document.getElementById('inputText').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitPrompt();
    }
});

// Load API configs, templates and history on page load
async function initializePage() {
    await loadApiConfigs();
    setupApiConfigSelector();
    loadTemplates();
    loadHistory();
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initializePage);
} else {
    initializePage();
}

