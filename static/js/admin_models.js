let modelState = {
    allModels: [],
    filteredModels: [],
    page: 1,
    pageSize: 25,
    query: '',
};

const STORAGE_KEYS = {
    query: 'admin_models_query',
    pageSize: 'admin_models_page_size',
};

let reformatSettingsCache = {};
let smartContextSettingsCache = {};

function showModelNotification(message, type = 'success') {
    if (typeof window.showNotification === 'function') {
        window.showNotification('model_notification_area', message, type, 4000);
    }
}

function escapeHtml(text) {
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function applyFilters() {
    const query = modelState.query.trim().toLowerCase();
    if (!query) {
        modelState.filteredModels = [...modelState.allModels];
        return;
    }
    modelState.filteredModels = modelState.allModels.filter((model) => {
        const id = String(model.id || '').toLowerCase();
        const owner = String(model.owned_by || '').toLowerCase();
        return id.includes(query) || owner.includes(query);
    });
}

function debounce(fn, waitMs) {
    let timer = null;
    return (...args) => {
        if (timer) clearTimeout(timer);
        timer = setTimeout(() => fn(...args), waitMs);
    };
}

function readPositiveInt(value, fallback) {
    const n = Number(value);
    return Number.isFinite(n) && n > 0 ? Math.floor(n) : fallback;
}

function persistUiState() {
    try {
        localStorage.setItem(STORAGE_KEYS.query, modelState.query);
        localStorage.setItem(STORAGE_KEYS.pageSize, String(modelState.pageSize));
    } catch (_e) {}
}

function syncUrlState() {
    try {
        const url = new URL(window.location.href);
        if (modelState.query) url.searchParams.set('q', modelState.query);
        else url.searchParams.delete('q');
        url.searchParams.set('page', String(modelState.page));
        url.searchParams.set('size', String(modelState.pageSize));
        window.history.replaceState({}, '', `${url.pathname}?${url.searchParams.toString()}`);
    } catch (_e) {}
}

function renderPagination(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const total = modelState.filteredModels.length;
    const pages = Math.max(1, Math.ceil(total / modelState.pageSize));
    const start = total === 0 ? 0 : (modelState.page - 1) * modelState.pageSize + 1;
    const end = Math.min(total, modelState.page * modelState.pageSize);

    container.innerHTML = `
        <div class="text-muted small">Показано ${start}-${end} из ${total}</div>
        <div class="btn-group btn-group-sm" role="group">
            <button type="button" class="btn btn-outline-secondary" id="${containerId}_prev" ${modelState.page <= 1 ? 'disabled' : ''}>Назад</button>
            <button type="button" class="btn btn-outline-secondary disabled">${modelState.page} / ${pages}</button>
            <button type="button" class="btn btn-outline-secondary" id="${containerId}_next" ${modelState.page >= pages ? 'disabled' : ''}>Вперёд</button>
        </div>
    `;

    const prev = document.getElementById(`${containerId}_prev`);
    const next = document.getElementById(`${containerId}_next`);
    prev?.addEventListener('click', () => {
        if (modelState.page > 1) {
            modelState.page -= 1;
            renderVisibleModels();
        }
    });
    next?.addEventListener('click', () => {
        if (modelState.page < pages) {
            modelState.page += 1;
            renderVisibleModels();
        }
    });
}

function applyCheckboxStates() {
    document.querySelectorAll('.reformat-messages-checkbox').forEach((checkbox) => {
        const modelId = checkbox.dataset.modelId;
        const moduleName = checkbox.dataset.moduleName;
        checkbox.checked = !!(reformatSettingsCache[moduleName] && reformatSettingsCache[moduleName][modelId]);
    });
    document.querySelectorAll('.smart-context-zipper-checkbox').forEach((checkbox) => {
        const modelId = checkbox.dataset.modelId;
        const moduleName = checkbox.dataset.moduleName;
        checkbox.checked = !!(smartContextSettingsCache[moduleName] && smartContextSettingsCache[moduleName][modelId]);
    });
}

function renderVisibleModels(errorMessage = '') {
    const modelsContainer = document.getElementById('models_list_container');
    if (!modelsContainer) return;
    modelsContainer.innerHTML = '';

    if (errorMessage) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger';
        errorDiv.role = 'alert';
        errorDiv.innerText = errorMessage;
        modelsContainer.appendChild(errorDiv);
        renderPagination('model_pagination_top');
        renderPagination('model_pagination_bottom');
        syncUrlState();
        return;
    }

    const total = modelState.filteredModels.length;
    const pages = Math.max(1, Math.ceil(total / modelState.pageSize));
    if (modelState.page > pages) modelState.page = pages;
    if (modelState.page < 1) modelState.page = 1;

    const startIdx = (modelState.page - 1) * modelState.pageSize;
    const visible = modelState.filteredModels.slice(startIdx, startIdx + modelState.pageSize);

    if (!visible.length) {
        const infoDiv = document.createElement('div');
        infoDiv.className = 'alert alert-info';
        infoDiv.role = 'alert';
        infoDiv.innerText = 'Нет доступных моделей по текущему фильтру.';
        modelsContainer.appendChild(infoDiv);
        renderPagination('model_pagination_top');
        renderPagination('model_pagination_bottom');
        syncUrlState();
        return;
    }

    const ul = document.createElement('ul');
    ul.className = 'list-group';
    visible.forEach((model) => {
        const safeId = escapeHtml(model.id || 'N/A');
        const safeOwner = escapeHtml(model.owned_by || 'N/A');
        const elementIdPart = String(model.id || 'na').replace(/\//g, '-');
        const li = document.createElement('li');
        li.className = 'list-group-item';
        li.innerHTML = `
            <div class="d-flex w-100 justify-content-between align-items-center">
                <h5 class="mb-1 model-id clickable-model-id" data-model-id="${safeId}" title="Нажмите, чтобы скопировать ID">${safeId}</h5>
                <div class="d-flex align-items-center ms-auto" style="gap: 10px;">
                    <div class="form-check form-switch">
                        <input class="form-check-input reformat-messages-checkbox" type="checkbox" id="reformatSwitch-${elementIdPart}" data-model-id="${safeId}" data-module-name="${safeOwner}">
                        <label class="form-check-label" for="reformatSwitch-${elementIdPart}">Переформировать сообщения в одно</label>
                    </div>
                    <div class="form-check form-switch">
                        <input class="form-check-input smart-context-zipper-checkbox" type="checkbox" id="smartZipperSwitch-${elementIdPart}" data-model-id="${safeId}" data-module-name="${safeOwner}">
                        <label class="form-check-label" for="smartZipperSwitch-${elementIdPart}">Context Zipper(exp)</label>
                    </div>
                </div>
            </div>
            <p class="mb-1 model-owner">Владелец: ${safeOwner}</p>
        `;
        ul.appendChild(li);
    });

    modelsContainer.appendChild(ul);
    renderPagination('model_pagination_top');
    renderPagination('model_pagination_bottom');
    applyCheckboxStates();
    syncUrlState();
}

function setNestedSetting(cache, moduleName, modelId, isEnabled) {
    if (!cache[moduleName]) cache[moduleName] = {};
    if (isEnabled) {
        cache[moduleName][modelId] = true;
    } else {
        delete cache[moduleName][modelId];
        if (Object.keys(cache[moduleName]).length === 0) {
            delete cache[moduleName];
        }
    }
}

async function loadReformatSettings() {
    try {
        const response = await fetch(URLS.ui_api_get_reformat_settings, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
        });
        const result = await response.json();
        if (response.ok && result.status === 'success') {
            reformatSettingsCache = result.settings || {};
            applyCheckboxStates();
        }
    } catch (err) {
        console.error('Network error loading reformat settings:', err);
    }
}

async function loadSmartContextZipperSettings() {
    try {
        const response = await fetch(URLS.ui_api_get_smart_context_zipper_settings, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'same-origin',
        });
        const result = await response.json();
        if (response.ok && result.status === 'success') {
            smartContextSettingsCache = result.settings || {};
            applyCheckboxStates();
        }
    } catch (err) {
        console.error('Network error loading smart context zipper settings:', err);
    }
}

async function refreshModelsFromServer() {
    const response = await fetch(URLS.ui_api_refresh_models, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
    });
    const result = await response.json();
    if (!response.ok || result.status !== 'success') {
        const detailMessage = result.detail || result.error_message || 'Ошибка при обновлении списка моделей.';
        throw new Error(detailMessage);
    }
    return {
        models: Array.isArray(result.models) ? result.models : [],
        errorMessage: result.error_message || '',
    };
}

function setModelsAndRender(models, errorMessage = '', resetPage = true) {
    modelState.allModels = Array.isArray(models) ? models : [];
    if (resetPage) modelState.page = 1;
    applyFilters();
    renderVisibleModels(errorMessage);
}

document.addEventListener('DOMContentLoaded', function () {
    const params = new URLSearchParams(window.location.search);
    let initialQuery = '';
    let initialPageSize = 25;
    let initialPage = 1;

    try {
        const storedQuery = localStorage.getItem(STORAGE_KEYS.query);
        const storedPageSize = localStorage.getItem(STORAGE_KEYS.pageSize);
        if (storedQuery) initialQuery = storedQuery;
        if (storedPageSize) initialPageSize = readPositiveInt(storedPageSize, 25);
    } catch (_e) {}

    if (params.has('q')) initialQuery = params.get('q') || '';
    if (params.has('size')) initialPageSize = readPositiveInt(params.get('size'), initialPageSize);
    if (params.has('page')) initialPage = readPositiveInt(params.get('page'), 1);

    modelState.query = initialQuery;
    modelState.pageSize = initialPageSize;
    modelState.page = initialPage;

    setModelsAndRender(INITIAL_MODELS || [], INITIAL_ERROR || '', false);

    loadReformatSettings();
    loadSmartContextZipperSettings();

    const searchInput = document.getElementById('model_search_input');
    if (searchInput) searchInput.value = modelState.query;
    const debouncedSearch = debounce((value) => {
        modelState.query = value || '';
        modelState.page = 1;
        persistUiState();
        applyFilters();
        renderVisibleModels();
    }, 200);
    searchInput?.addEventListener('input', (event) => {
        debouncedSearch(event.target.value);
    });

    const pageSizeSelect = document.getElementById('model_page_size_select');
    if (pageSizeSelect) pageSizeSelect.value = String(modelState.pageSize);
    pageSizeSelect?.addEventListener('change', (event) => {
        const value = Number(event.target.value);
        modelState.pageSize = Number.isFinite(value) && value > 0 ? value : 25;
        modelState.page = 1;
        persistUiState();
        applyFilters();
        renderVisibleModels();
    });

    const modelsContainer = document.getElementById('models_list_container');
    modelsContainer?.addEventListener('click', function (event) {
        const target = event.target;
        const idElement = target.classList.contains('clickable-model-id')
            ? target
            : target.closest('.clickable-model-id');
        if (!idElement) return;
        const modelIdToCopy = idElement.dataset.modelId;
        if (!modelIdToCopy) return;
        navigator.clipboard.writeText(modelIdToCopy).then(() => {
            showModelNotification(`ID модели "${modelIdToCopy}" скопирован!`);
        }).catch((err) => {
            showModelNotification('Не удалось скопировать ID модели.', 'error');
            console.error('Clipboard copy failed:', err);
        });
    });

    modelsContainer?.addEventListener('change', async function (event) {
        const target = event.target;
        if (!target.classList.contains('reformat-messages-checkbox') && !target.classList.contains('smart-context-zipper-checkbox')) {
            return;
        }

        const modelId = target.dataset.modelId;
        const moduleName = target.dataset.moduleName;
        const isEnabled = target.checked;

        if (target.classList.contains('reformat-messages-checkbox')) {
            showModelNotification(`Сохранение настройки для ${modelId}...`, 'info');
            try {
                const response = await fetch(URLS.ui_api_set_reformat_status, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ model_id: modelId, module_name: moduleName, is_reformat_enabled: isEnabled }),
                    credentials: 'same-origin',
                });
                const result = await response.json();
                if (!response.ok || result.status !== 'success') {
                    target.checked = !isEnabled;
                    showModelNotification(result.detail || `Ошибка при сохранении настройки для ${modelId}.`, 'error');
                    return;
                }
                setNestedSetting(reformatSettingsCache, moduleName, modelId, isEnabled);
                showModelNotification(result.message || `Настройка для ${modelId} успешно сохранена.`);
                return;
            } catch (err) {
                target.checked = !isEnabled;
                showModelNotification(`Сетевая ошибка при сохранении настройки для ${modelId}.`, 'error');
                console.error('Reformat setting save error:', err);
                return;
            }
        }

        showModelNotification(`Сохранение настройки Smart Context Zipper для ${modelId}...`, 'info');
        try {
            const response = await fetch(URLS.ui_api_set_smart_context_zipper_status, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model_id: modelId, module_name: moduleName, is_smart_context_zipper_enabled: isEnabled }),
                credentials: 'same-origin',
            });
            const result = await response.json();
            if (!response.ok || result.status !== 'success') {
                target.checked = !isEnabled;
                showModelNotification(result.detail || `Ошибка при сохранении зиппер-настройки для ${modelId}.`, 'error');
                return;
            }
            setNestedSetting(smartContextSettingsCache, moduleName, modelId, isEnabled);
            showModelNotification(result.message || `Зиппер-настройка для ${modelId} успешно сохранена.`);
        } catch (err) {
            target.checked = !isEnabled;
            showModelNotification(`Сетевая ошибка при сохранении зиппер-настройки для ${modelId}.`, 'error');
            console.error('SmartContextZipper setting save error:', err);
        }
    });

    const refreshForm = document.getElementById('refresh_models_form');
    refreshForm?.addEventListener('submit', async function (event) {
        event.preventDefault();
        showModelNotification('Обновление списка моделей...', 'info');
        try {
            const { models, errorMessage } = await refreshModelsFromServer();
            setModelsAndRender(models, errorMessage, true);
            persistUiState();
            await loadReformatSettings();
            await loadSmartContextZipperSettings();
            showModelNotification('Список моделей успешно обновлен.');
        } catch (err) {
            showModelNotification(err.message || 'Сетевая ошибка при обновлении списка моделей.', 'error');
            setModelsAndRender([], err.message || 'Ошибка при обновлении списка моделей.', true);
        }
    });
});
