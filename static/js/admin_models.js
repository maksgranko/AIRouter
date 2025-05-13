function showModelNotification(message, type = 'success') {
    const notificationArea = document.getElementById('model_notification_area');
    if (!notificationArea) {
        console.warn("Notification area 'model_notification_area' not found.");
        alert(message);
        return;
    }
    const notification = document.createElement('div');
    notification.className = `alert alert-${type === 'success' ? 'success' : 'danger'} mt-2`;
    notification.role = 'alert';
    notification.innerText = message;

    notificationArea.innerHTML = '';
    notificationArea.appendChild(notification);
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
                <div class="d-flex w-100 justify-content-between">
                    <h5 class="mb-1 model-id clickable-model-id" data-model-id="${model.id}" title="Нажмите, чтобы скопировать ID">${model.id}</h5>
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
                        showModelNotification(`ID модели "${modelIdToCopy}" скопирован!`, 'success');
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

document.addEventListener('DOMContentLoaded', function() {
    const modelsContainer = document.getElementById('models_list_container');
    if (modelsContainer) {
        modelsContainer.addEventListener('click', function(event) {
            const target = event.target;
            if (target.classList.contains('clickable-model-id') || target.closest('.clickable-model-id')) {
                const modelIdElement = target.classList.contains('clickable-model-id') ? target : target.closest('.clickable-model-id');
                const modelIdToCopy = modelIdElement.dataset.modelId;
                if (modelIdToCopy) {
                    navigator.clipboard.writeText(modelIdToCopy).then(() => {
                        showModelNotification(`ID модели "${modelIdToCopy}" скопирован!`, 'success');
                    }).catch(err => {
                        showModelNotification('Не удалось скопировать ID модели.', 'error');
                        console.error('Clipboard copy failed: ', err);
                    });
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
                    showModelNotification(result.message || 'Список моделей успешно обновлен.', 'success');
                    renderModelsList(result.models, result.error_message);
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
});
