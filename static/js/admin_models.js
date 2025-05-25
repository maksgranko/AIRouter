function showModelNotification(message, type = 'success') {
    if (typeof window.showNotification === 'function') {
        window.showNotification('model_notification_area', message, type, 4000);
    }
}

function renderModelsList(models, errorMessage) {
    const modelsContainer = document.getElementById('models_list_container');
    if (!modelsContainer) {
        console.error("Container 'models_list_container' not found for rendering models.");
        return;
    }
    modelsContainer.innerHTML = '';

    if (errorMessage) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-danger';
        errorDiv.role = 'alert';
        errorDiv.innerText = errorMessage;
        modelsContainer.appendChild(errorDiv);
    }

    if (models && models.length > 0) {
        const ul = document.createElement('ul');
        ul.className = 'list-group';
        models.forEach(model => {
            const li = document.createElement('li');
            li.className = 'list-group-item';
            li.innerHTML = `
                <div class="d-flex w-100 justify-content-between align-items-center">
                    <h5 class="mb-1 model-id clickable-model-id" data-model-id="${model.id}" title="Нажмите, чтобы скопировать ID">${model.id}</h5>
                    <div class="form-check form-switch">
                        <input class="form-check-input reformat-messages-checkbox" type="checkbox" id="reformatSwitch-${model.id.replace(/\//g, '-')}" data-model-id="${model.id}" data-module-name="${model.owned_by || 'N/A'}">
                        <label class="form-check-label" for="reformatSwitch-${model.id.replace(/\//g, '-')}">Переформировать сообщения в одно</label>
                    </div>
                </div>
                <p class="mb-1 model-owner">Владелец: ${model.owned_by || 'N/A'}</p>
            `;
            ul.appendChild(li);
        });
        modelsContainer.appendChild(ul);

        // Делаем id кликабельным (copy to clipboard).
        modelsContainer.addEventListener('click', function(event) {
            const target = event.target;
            if (target.classList.contains('clickable-model-id') || target.closest('.clickable-model-id')) {
                const modelIdElement = target.classList.contains('clickable-model-id') ? target : target.closest('.clickable-model-id');
                const modelIdToCopy = modelIdElement.dataset.modelId;
                if (modelIdToCopy) {
                    navigator.clipboard.writeText(modelIdToCopy).then(() => {
                        showModelNotification(`ID модели "${modelIdToCopy}" скопирован!`);
                    }).catch(err => {
                        showModelNotification('Не удалось скопировать ID модели.', 'error');
                        console.error('Clipboard copy failed: ', err);
                    });
                }
            }
        });

    } else if (!errorMessage) {
        const infoDiv = document.createElement('div');
        infoDiv.className = 'alert alert-info';
        infoDiv.role = 'alert';
        infoDiv.innerText = 'Нет доступных моделей или не удалось их получить.';
        modelsContainer.appendChild(infoDiv);
    }
}

async function loadReformatSettings() {
    try {
        if (typeof URLS === 'undefined' || typeof URLS.ui_api_get_reformat_settings === 'undefined') {
            console.error("URLS.ui_api_get_reformat_settings is not defined.");
            return;
        }
        const response = await fetch(URLS.ui_api_get_reformat_settings, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            },
            credentials: 'same-origin'
        });
        const result = await response.json();
        if (response.ok && result.status === 'success') {
            const settings = result.settings; // Ожидаем объект { module_name: { model_id: bool } }
            document.querySelectorAll('.reformat-messages-checkbox').forEach(checkbox => {
                const modelId = checkbox.dataset.modelId;
                const moduleName = checkbox.dataset.moduleName;
                if (settings[moduleName] && settings[moduleName][modelId] !== undefined) {
                    checkbox.checked = settings[moduleName][modelId];
                } else {
                    checkbox.checked = false; // По умолчанию выключено, если нет в конфиге
                }
            });
        } else {
            console.error("Failed to load reformat settings:", result.detail || "Unknown error");
        }
    } catch (err) {
        console.error("Network error loading reformat settings:", err);
    }
}


document.addEventListener('DOMContentLoaded', function() {
    const modelsContainer = document.getElementById('models_list_container');
    
    // Обработчик клика для копирования ID модели
    if (modelsContainer) {
        modelsContainer.addEventListener('click', function(event) {
            const target = event.target;
            if (target.classList.contains('clickable-model-id') || target.closest('.clickable-model-id')) {
                const modelIdElement = target.classList.contains('clickable-model-id') ? target : target.closest('.clickable-model-id');
                const modelIdToCopy = modelIdElement.dataset.modelId;
                if (modelIdToCopy) {
                    navigator.clipboard.writeText(modelIdToCopy).then(() => {
                        showModelNotification(`ID модели "${modelIdToCopy}" скопирован!`);
                    }).catch(err => {
                        showModelNotification('Не удалось скопировать ID модели.', 'error');
                        console.error('Clipboard copy failed: ', err);
                    });
                }
            }
        });

        // Добавляем обработчик для чекбоксов reformat-messages-checkbox
        // Этот обработчик должен быть здесь, чтобы он работал для элементов,
        // которые рендерятся Jinja2 при первой загрузке страницы,
        // а также для тех, которые динамически добавляются renderModelsList.
        modelsContainer.addEventListener('change', async function(event) {
            const target = event.target;
            if (target.classList.contains('reformat-messages-checkbox')) {
                const modelId = target.dataset.modelId;
                const moduleName = target.dataset.moduleName;
                const isEnabled = target.checked;

                showModelNotification(`Сохранение настройки для ${modelId}...`, 'info');
                try {
                    const response = await fetch(URLS.ui_api_set_reformat_status, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ model_id: modelId, module_name: moduleName, is_reformat_enabled: isEnabled }),
                        credentials: 'same-origin'
                    });
                    const result = await response.json();
                    if (response.ok && result.status === 'success') {
                        showModelNotification(result.message || `Настройка для ${modelId} успешно сохранена.`);
                    } else {
                        showModelNotification(result.detail || `Ошибка при сохранении настройки для ${modelId}.`, 'error');
                        target.checked = !isEnabled; // Откатываем состояние чекбокса при ошибке
                    }
                } catch (err) {
                    showModelNotification(`Сетевая ошибка при сохранении настройки для ${modelId}.`, 'error');
                    console.error("Reformat setting save error:", err);
                    target.checked = !isEnabled; // Откатываем состояние чекбокса при ошибке
                }
            }
        });
    }

    // Загрузка списка моделей по запросу (ручное обновление из UI).
    const refreshForm = document.getElementById('refresh_models_form');
    if (refreshForm) {
        refreshForm.addEventListener('submit', async function(event) {
            event.preventDefault();
            showModelNotification('Обновление списка моделей...', 'info');
            try {
                if (typeof URLS === 'undefined' || typeof URLS.ui_api_refresh_models === 'undefined') {
                    showModelNotification('Ошибка: URL для обновления моделей не определен.', 'error');
                    console.error("URLS.ui_api_refresh_models is not defined.");
                    return;
                }
                const response = await fetch(URLS.ui_api_refresh_models, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    credentials: 'same-origin'
                });
                const result = await response.json();
                if (response.ok && result.status === 'success') {
                    showModelNotification(result.message || 'Список моделей успешно обновлен.');
                    renderModelsList(result.models, result.error_message);
                    // После обновления списка, снова загружаем и применяем состояния чекбоксов
                    loadReformatSettings(); 
                } else {
                    const detailMessage = result.detail || (result.error_message || 'Ошибка при обновлении списка моделей.');
                    showModelNotification(detailMessage, 'error');
                    renderModelsList(null, detailMessage);
                }
            } catch (err) {
                showModelNotification('Сетевая ошибка при обновлении списка моделей.', 'error');
                console.error("Model refresh error:", err);
            }
        });
    }

    // Загружаем и применяем состояния чекбоксов при загрузке страницы
    loadReformatSettings();
});
