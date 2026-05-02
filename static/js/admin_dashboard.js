let handlersAttached = false;

function normalizeApiErrorMessage(responseData, rawText, statusCode) {
    if (responseData && responseData.detail) {
        if (Array.isArray(responseData.detail)) {
            const first = responseData.detail[0];
            if (first && typeof first === 'object') {
                const pathStr = Array.isArray(first.loc) ? first.loc.join('.') : '';
                return `${pathStr ? pathStr + ': ' : ''}${first.msg || 'Validation error'}`;
            }
            return responseData.detail.map((x) => String(x)).join('; ');
        }
        if (typeof responseData.detail === 'object') {
            return JSON.stringify(responseData.detail);
        }
        return String(responseData.detail);
    }
    if (responseData && responseData.message) {
        return String(responseData.message);
    }
    if (rawText && rawText.trim().length > 0) {
        return rawText;
    }
    return `Ошибка ${statusCode}`;
}

function parseJsonObjectOrThrow(rawValue, fieldLabel) {
    const source = (rawValue || '').trim();
    if (!source) return {};
    let parsed;
    try {
        parsed = JSON.parse(source);
    } catch (_e) {
        throw new Error(`${fieldLabel}: ожидается валидный JSON-объект.`);
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
        throw new Error(`${fieldLabel}: ожидается JSON-объект вида {"alias":"target"}.`);
    }
    return parsed;
}

async function makeApiRequest(url, method = 'GET', body = null) {
    const headers = { 'Content-Type': 'application/json' };
    const config = { 
        method, 
        headers,
        credentials: 'same-origin' // Добавляем эту строку
    };
    if (body) {
        config.body = JSON.stringify(body);
    }
    try {
        const response = await fetch(url, config);
        const rawText = await response.text();
        let responseData = null;
        if (rawText && rawText.trim().length > 0) {
            try {
                responseData = JSON.parse(rawText);
            } catch (_jsonErr) {
                responseData = null;
            }
        }
        if (!response.ok) {
            const detailMessage = normalizeApiErrorMessage(responseData, rawText, response.status);
            throw new Error(detailMessage);
        }
        return responseData || { status: 'success' };
    } catch (error) {
        console.error(`Ошибка API запроса к ${url}:`, error);
        window.showNotification && window.showNotification('notification_area', error.message || 'Сетевая ошибка или ошибка сервера.', 'error');
        throw error;
    }
}

async function loadDashboardData() {
    try {
        const data = await makeApiRequest(URLS.dashboardData); // Используем глобальный URLS
        
        document.getElementById('app_version_display').innerText = data.app_version;

        // Настройки Прокси
        document.getElementById('use_proxies').value = data.proxy_manager_is_active ? "true" : "false";
        document.getElementById('proxy_manager_active_status_display').innerText = data.proxy_manager_active_status;
        document.getElementById('initial_use_proxies_env_display').innerText = data.initial_use_proxies_env;
        
        document.getElementById('rotation_mode').value = data.current_proxy_rotation_mode;
        document.getElementById('current_proxy_rotation_mode_display').innerText = data.current_proxy_rotation_mode;
        document.getElementById('initial_proxy_rotation_mode_env_display_details').innerHTML = `(<code>once</code>: ..., <code>cycle</code>: ..., <code>failover_cycle</code>: ...). Исходная из PROXY_ROTATION_MODE: ${data.initial_proxy_rotation_mode_env}.`;

        document.getElementById('force_proxy_rotation_after_request').value = data.force_proxy_rotation_after_request ? "true" : "false";
        document.getElementById('force_proxy_rotation_after_request_display').innerText = data.force_proxy_rotation_after_request ? "Включено" : "Выключено";

        document.getElementById('select_random_proxy_each_request').value = data.select_random_proxy_each_request ? "true" : "false";
        document.getElementById('select_random_proxy_each_request_display').innerText = data.select_random_proxy_each_request ? "Случайный" : "Последовательный";

        // Информация о Файлах Конфигурации
        document.getElementById('openai_keys_info').innerText = `${data.openai_keys_file} (Загружено: ${data.openai_keys_count} ключ(ей))`;
        document.getElementById('gemini_keys_info').innerText = `${data.gemini_keys_file} (Загружено: ${data.gemini_keys_count} ключ(ей))`;
        document.getElementById('proxies_info').innerText = `${data.proxies_file} (Загружено: ${data.proxies_count} прокси)`;
        document.getElementById('config_openai_path_display').innerText = data.openai_keys_file;
        document.getElementById('config_gemini_path_display').innerText = data.gemini_keys_file;
        document.getElementById('config_proxies_path_display').innerText = data.proxies_file;
        document.getElementById('openai_instances_file_path_display').innerText = data.openai_instances_file; // Добавлено для нового файла
        
        // Управление API Ключами
        const apiKeysSection = document.getElementById('api_keys_management_section');
        apiKeysSection.innerHTML = ''; 
        for (const service_name in data.service_api_keys) {
            const keys = data.service_api_keys[service_name];
            const serviceDiv = document.createElement('div');
            serviceDiv.className = 'setting';
            let keysHtml = '<ul style="list-style-type: none; padding-left: 0;">';
            if (keys && keys.length > 0) {
                keys.forEach(key => {
                    keysHtml += `
                        <li style="margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center;">
                            <span style="word-break: break-all; margin-right: 10px;">
                                <span class="display-service-key">${key}</span>
                                <span class="edit-service-key-btn" title="Редактировать ключ" style="color: #888; cursor: pointer; margin-left:4px;" data-service-name="${service_name}">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="currentColor" class="bi bi-pencil" viewBox="0 0 16 16">
                                        <path d="M12.146.854a.5.5 0 0 1 .708 0l2.292 2.292a.5.5 0 0 1 0 .708l-10 10A.5.5 0 0 1 4.5 14H2.5a.5.5 0 0 1-.5-.5v-2a.5.5 0 0 1 .146-.354l10-10zM11.207 2L14 4.793 13.5 5.5 10.707 2.707l.5-.5zm1.086 2.121L12.207 4.5 9.5 7.207V8h.793l2.707-2.707zM3 13v1h1l8.293-8.293-1-1L3 13z"/>
                                    </svg>
                                </span>
                            </span>
                            <form class="api-key-remove-form" data-service="${service_name}" data-key="${key}">
                                <button type="submit" class="btn btn-danger btn-sm">Удалить</button>
                            </form>
                        </li>`;
                });
            } else {
                keysHtml += '<li>Нет ключей для этого сервиса.</li>';
            }
        serviceDiv.innerHTML = `
            <h3 style="color: #333;">Ключи для сервиса: ${service_name}</h3>
            ${keysHtml}
            <form class="api-key-add-form" data-service="${service_name}" style="margin-top: 10px;">
                <div class="input-group mb-3">
                    <input type="text" id="new_api_key_${service_name}" name="api_key" class="form-control" placeholder="Новый ключ" required>
                    <button type="submit" class="btn btn-primary">Добавить ключ</button>
                </div>
            </form>
        `;
        apiKeysSection.appendChild(serviceDiv);

        // ----- Кнопка "Редактировать API-ключ" для сервисов -----
        serviceDiv.querySelectorAll('.edit-service-key-btn').forEach((editKeyBtn) => {
            const displayKeySpan = editKeyBtn.previousElementSibling;
            if (!displayKeySpan) return;
            editKeyBtn.addEventListener('click', function () {
                const currentService = editKeyBtn.dataset.serviceName;
                const keyValue = displayKeySpan.textContent;
                const input = document.createElement('input');
                input.type = "text";
                input.value = keyValue;
                input.className = "form-control form-control-sm d-inline-block";
                input.style.width = "200px";
                displayKeySpan.replaceWith(input);
                input.focus();
                input.addEventListener('blur', async function () {
                    const val = input.value.trim();
                    if (val && val !== keyValue) {
                        try {
                            const url = `/api/admin/ui/keys/service/${encodeURIComponent(currentService)}/key`;
                            const payload = { old_api_key: keyValue, new_api_key: val };
                            const res = await makeApiRequest(url, 'PATCH', payload);
                            window.showNotification('notification_area',res.message || 'API-ключ изменён.');
                            loadDashboardData();
                        } catch (e) {}
                    } else {
                        input.replaceWith(displayKeySpan);
                    }
                });
                input.addEventListener('keydown', function (e) {
                    if (e.key === 'Enter') input.blur();
                    if (e.key === 'Escape') { input.replaceWith(displayKeySpan); }
                });
            });
        });
            keysHtml += '</ul>';

            serviceDiv.innerHTML = `
                <h3 style="color: #333;">Ключи для сервиса: ${service_name}</h3>
                ${keysHtml}
                <form class="api-key-add-form" data-service="${service_name}" style="margin-top: 10px;">
                    <div class="input-group mb-3">
                        <input type="text" id="new_api_key_${service_name}" name="api_key" class="form-control" placeholder="Новый ключ" required>
                        <button type="submit" class="btn btn-primary">Добавить ключ</button>
                    </div>
                </form>
            `;
            apiKeysSection.appendChild(serviceDiv);
        }

        // Управление Прокси-серверами
        const proxyManagementContainer = document.getElementById('proxy_management_section_container');
        const proxyManagementContent = document.getElementById('proxy_management_content');
        document.getElementById('proxies_file_path_instruction_display').innerText = data.proxies_file;

        if (data.proxy_manager_is_active) {
            proxyManagementContainer.style.display = '';
            let proxiesHtml = `<h3 style="color: #333;">Список прокси (из файла: ${data.proxies_file})</h3>
                               <ul style="list-style-type: none; padding-left: 0;">`;
            if (data.current_proxies_list && data.current_proxies_list.length > 0) {
                data.current_proxies_list.forEach(proxy_item => {
                    proxiesHtml += `
                        <li style="margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center;">
                            <span style="word-break: break-all; margin-right: 10px;">[${proxy_item.type}] ${proxy_item.url}</span>
                            <form class="proxy-remove-form" data-url="${proxy_item.url}">
                                <button type="submit" class="btn btn-danger btn-sm">Удалить</button>
                            </form>
                        </li>`;
                });
            } else {
                proxiesHtml += '<li>Нет прокси в списке.</li>';
            }
            proxiesHtml += '</ul>';
            proxyManagementContent.innerHTML = `
                ${proxiesHtml}
                <form id="add_proxy_form" style="margin-top: 10px;">
                    <div class="mb-3">
                        <label for="new_proxy_type" class="setting-name form-label">Тип нового прокси:</label>
                        <select name="new_proxy_type" id="new_proxy_type" class="form-select">
                            <option value="http">HTTP</option><option value="https">HTTPS</option><option value="socks4">SOCKS4</option><option value="socks5">SOCKS5</option>
                        </select>
                    </div>
                    <div class="mb-3">
                        <label for="new_proxy_url" class="setting-name form-label">URL нового прокси:</label>
                        <input type="text" id="new_proxy_url" name="new_proxy_url" class="form-control" required>
                    </div>
                    <button type="submit" class="btn btn-primary">Добавить прокси</button>
                </form>
                <div style="margin-top:15px;">
                    <form id="reload_proxies_form" style="display: inline-block; margin-right: 10px;"><button type="submit" class="btn btn-secondary">Перезагрузить</button></form>
                    <form id="shuffle_proxies_form" style="display: inline-block;"><button type="submit" class="btn btn-secondary" onclick="return confirm('Перемешать и сохранить?');">Перемешать</button></form>
                </div>`;
        } else {
             proxyManagementContainer.style.display = 'none';
        }
        
        // Управление Модулями
        const moduleSection = document.getElementById('module_management_section');
        moduleSection.innerHTML = '';
        if (data.module_statuses && Object.keys(data.module_statuses).length > 0) {
            for (const module_name in data.module_statuses) {
                const status = data.module_statuses[module_name];
                const moduleDiv = document.createElement('div');
                moduleDiv.className = 'setting';

                // use_global_proxy чекбокс (только не OAIC)
                let proxySwitchHtml = '';
                if (module_name !== 'OAIC') {
                    const moduleProxyUsage = (data.module_proxy_usage && typeof data.module_proxy_usage[module_name] !== 'undefined')
                        ? data.module_proxy_usage[module_name] : true;
                    // разрешаем только строго true, иначе чекбокс снят
                    const checkedAttr = (moduleProxyUsage === true) ? 'checked' : '';
                    proxySwitchHtml = `
                        <div class="form-check form-switch mb-1">
                            <input class="form-check-input module-proxy-switch" type="checkbox"
                                id="use_global_proxy_switch_${module_name}"
                                data-module-name="${module_name}" ${checkedAttr}>
                            <label class="form-check-label" for="use_global_proxy_switch_${module_name}">Использовать глобальный прокси для этого модуля</label>
                        </div>
                    `;
                }

                moduleDiv.innerHTML = `
                    <form class="module-status-form" data-module-name="${module_name}">
                        <label for="module_status_${module_name}" class="setting-name">Модуль ${module_name}:</label>
                        <select name="module_status" id="module_status_${module_name}" class="form-select d-inline-block w-auto me-2">
                            <option value="true" ${status ? 'selected' : ''}>Включен</option>
                            <option value="false" ${!status ? 'selected' : ''}>Выключен</option>
                        </select>
                        <button type="submit" class="btn btn-primary btn-sm">Применить</button>
                        <small class="ms-2">Текущий статус: <span class="setting-value">${status ? 'Включен' : 'Выключен'}</span></small>
                    </form>
                    ${proxySwitchHtml}
                `;
                moduleSection.appendChild(moduleDiv);
            }
        } else {
            moduleSection.innerHTML = '<p>Нет модулей.</p>';
        }


        // Безопасность AIRouter API
        document.getElementById('require_airouter_api_key').value = data.require_airouter_api_key ? "true" : "false";
        document.getElementById('require_airouter_api_key_status_display').innerText = data.require_airouter_api_key ? "Требуется API-ключ" : "API-ключ не требуется";

        // API-ключи AIRouter
        const airouterKeysContainer = document.getElementById('airouter_api_keys_section_container');
        const airouterKeysListDiv = document.getElementById('airouter_api_keys_list');
        document.getElementById('airouter_keys_file_display').innerText = data.airouter_keys_file;
        document.getElementById('airouter_keys_file_instruction_display').innerText = data.airouter_keys_file;

        if (data.require_airouter_api_key) {
            airouterKeysContainer.style.display = '';
            let airouterKeysHtml = '<ul style="list-style-type: none; padding-left: 0;">';
            if (data.airouter_api_keys && data.airouter_api_keys.length > 0) {
                data.airouter_api_keys.forEach(key => {
                    airouterKeysHtml += `
                        <li style="margin-bottom: 5px; display: flex; justify-content: space-between; align-items: center;">
                            <span style="word-break: break-all; margin-right: 10px;">
                                <span class="display-airouter-key">${key}</span>
                                <span class="edit-airouter-key-btn" title="Редактировать ключ" style="color: #888; cursor: pointer; margin-left:4px;">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="currentColor" class="bi bi-pencil" viewBox="0 0 16 16">
                                        <path d="M12.146.854a.5.5 0 0 1 .708 0l2.292 2.292a.5.5 0 0 1 0 .708l-10 10A.5.5 0 0 1 4.5 14H2.5a.5.5 0 0 1-.5-.5v-2a.5.5 0 0 1 .146-.354l10-10zM11.207 2L14 4.793 13.5 5.5 10.707 2.707l.5-.5zm1.086 2.121L12.207 4.5 9.5 7.207V8h.793l2.707-2.707zM3 13v1h1l8.293-8.293-1-1L3 13z"/>
                                    </svg>
                                </span>
                            </span>
                            <form class="airouter-key-remove-form" data-key="${key}">
                                <button type="submit" class="btn btn-danger btn-sm">Удалить</button>
                            </form>
                        </li>`;
                });
            } else {
                airouterKeysHtml += '<li>Нет API-ключей AIRouter.</li>';
            }
            airouterKeysHtml += '</ul>';
            airouterKeysListDiv.innerHTML = airouterKeysHtml;

            // ----- Кнопка "Редактировать API-ключ" для AIRouter -----
            airouterKeysListDiv.querySelectorAll('.edit-airouter-key-btn').forEach((editKeyBtn) => {
                const displayKeySpan = editKeyBtn.previousElementSibling;
                if (!displayKeySpan) return;
                editKeyBtn.addEventListener('click', function () {
                    const keyValue = displayKeySpan.textContent;
                    const input = document.createElement('input');
                    input.type = "text";
                    input.value = keyValue;
                    input.className = "form-control form-control-sm d-inline-block";
                    input.style.width = "200px";
                    displayKeySpan.replaceWith(input);
                    input.focus();
                    input.addEventListener('blur', async function () {
                        const val = input.value.trim();
                        if (val && val !== keyValue) {
                            try {
                                const url = `/api/admin/ui/keys/airouter/key`;
                                const payload = { old_api_key: keyValue, new_api_key: val };
                                const res = await makeApiRequest(url, 'PATCH', payload);
                                window.showNotification('notification_area',res.message || 'API-ключ изменён.');
                                loadDashboardData();
                            } catch (e) {}
                        } else {
                            input.replaceWith(displayKeySpan);
                        }
                    });
                    input.addEventListener('keydown', function (e) {
                        if (e.key === 'Enter') input.blur();
                        if (e.key === 'Escape') { input.replaceWith(displayKeySpan); }
                    });
                });
            });

            // ----- Кнопка "Редактировать API-ключ" для AIRouter -----
            airouterKeysListDiv.querySelectorAll('.edit-airouter-key-btn').forEach((editKeyBtn) => {
                const displayKeySpan = editKeyBtn.previousElementSibling;
                if (!displayKeySpan) return;
                editKeyBtn.addEventListener('click', function () {
                    const keyValue = displayKeySpan.textContent;
                    const input = document.createElement('input');
                    input.type = "text";
                    input.value = keyValue;
                    input.className = "form-control form-control-sm d-inline-block";
                    input.style.width = "200px";
                    displayKeySpan.replaceWith(input);
                    input.focus();
                    input.addEventListener('blur', async function () {
                        const val = input.value.trim();
                        if (val && val !== keyValue) {
                            try {
                                const url = `/api/admin/ui/keys/airouter/key`;
                                const payload = { old_api_key: keyValue, new_api_key: val };
                                const res = await makeApiRequest(url, 'PATCH', payload);
                                window.showNotification('notification_area',res.message || 'API-ключ изменён.');
                                loadDashboardData();
                            } catch (e) {}
                        } else {
                            input.replaceWith(displayKeySpan);
                        }
                    });
                    input.addEventListener('keydown', function (e) {
                        if (e.key === 'Enter') input.blur();
                        if (e.key === 'Escape') { input.replaceWith(displayKeySpan); }
                    });
                });
            });

        } else {
            airouterKeysContainer.style.display = 'none';
        }
        // Управление Инстансами OpenAI Compatible
        const instancesSection = document.getElementById('openai_instances_management_section');
        instancesSection.innerHTML = ''; // Очищаем предыдущее содержимое
        if (data.openai_instances && data.openai_instances.length > 0) {
            data.openai_instances.forEach(instance => {
                const instanceDiv = document.createElement('div');
                instanceDiv.className = 'card mb-3'; // Обертка для каждого инстанса
                let keysHtml = '<ul class="list-group list-group-flush">';
                if (instance.api_keys && instance.api_keys.length > 0) {
                    instance.api_keys.forEach(key => {
                        keysHtml += `
                            <li class="list-group-item d-flex justify-content-between align-items-center">
                                <span style="word-break: break-all; margin-right: 10px;">
                                    <span class="display-instance-key">${key}</span>
                                    <span class="edit-instance-key-btn" title="Редактировать ключ" style="color: #888; cursor: pointer; margin-left:4px;">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" fill="currentColor" class="bi bi-pencil" viewBox="0 0 16 16">
                                            <path d="M12.146.854a.5.5 0 0 1 .708 0l2.292 2.292a.5.5 0 0 1 0 .708l-10 10A.5.5 0 0 1 4.5 14H2.5a.5.5 0 0 1-.5-.5v-2a.5.5 0 0 1 .146-.354l10-10zM11.207 2L14 4.793 13.5 5.5 10.707 2.707l.5-.5zm1.086 2.121L12.207 4.5 9.5 7.207V8h.793l2.707-2.707zM3 13v1h1l8.293-8.293-1-1L3 13z"/>
                                        </svg>
                                    </span>
                                </span>
                                <button type="button" class="btn btn-danger btn-sm openai-instance-key-remove-btn" data-instance-name="${instance.name}" data-key="${key}">Удалить ключ</button>
                            </li>`;
                    });
                } else {
                    keysHtml += '<li class="list-group-item">Нет API ключей для этого инстанса.</li>';
                }
                keysHtml += '</ul>';

                const useGlobalProxyChecked = instance.use_global_proxy !== false ? 'checked' : '';
                const aliasesJson = JSON.stringify(instance.model_aliases || {}, null, 2);
                const redirectsJson = JSON.stringify(instance.model_redirects || {}, null, 2);

                // === Failsafe ComboBox+list ===
                const allInstanceNames = data.openai_instances.map(i => i.name);
                const failsafeList = instance.failsafe_providers || [];
                // Доступные для добавления: не self и не уже добавленные
                const availableFailsafe = allInstanceNames.filter(n => n !== instance.name && !failsafeList.includes(n));

                let failsafeHtml = `
                  <label class="form-label">Failsafe-провайдеры (по порядку):</label>
                  <ul class="list-group list-group-sm mb-2 openai-failsafe-list" id="failsafe_list_${instance.name}">
                    ${
                      failsafeList.length
                        ? failsafeList.map((prov, i) =>
                            `<li class="list-group-item d-flex justify-content-between align-items-center py-1 openai-failsafe-draggable" draggable="true" data-prov="${prov}">
                               <span>${prov}</span>
                               <button type="button" class="btn btn-outline-danger btn-sm px-2 py-0 openai-failsafe-remove-btn" data-instance-name="${instance.name}" data-prov="${prov}" title="Удалить">&times;</button>
                             </li>`
                          ).join('')
                        : `<li class="list-group-item text-muted py-1">Нет резервных провайдеров</li>`
                    }
                  </ul>
                  <div class="input-group input-group-sm mb-1">
                    <select class="form-select openai-failsafe-combo" id="failsafe_combo_${instance.name}" data-instance-name="${instance.name}">
                      <option value="" disabled selected>Выберите провайдера</option>
                      ${availableFailsafe.map(pv => `<option value="${pv}">${pv}</option>`).join('')}
                    </select>
                    <button type="button" class="btn btn-primary openai-failsafe-add-btn" data-instance-name="${instance.name}">Добавить</button>
                  </div>
                  <small class="form-text text-muted">Если этот инстанс выдаёт ошибку — пробуем выбранных выше по порядку.</small>
                `;

                instanceDiv.innerHTML = `
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <div class="d-flex align-items-center">
                            <button type="button" class="btn btn-sm me-2 openai-instance-enabled-toggle-btn"
                                data-instance-name="${instance.name}"
                                data-enabled="${instance.enabled}"
                                title="${instance.enabled ? 'Выключить инстанс' : 'Включить инстанс'}"
                                style="background-color: #fff; border: 2px solid ${instance.enabled ? '#19c232' : '#dc3545'}; border-radius: 5px; padding: 2px 5px;">
                                ${
                                  instance.enabled
                                    ? `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="#19c232" viewBox="0 0 16 16">
                                          <path d="M12.736 3.97a.75.75 0 0 1 1.061 1.06l-6.363 6.364-3.182-3.182a.75.75 0 1 1 1.061-1.06l2.121 2.12 5.303-5.302z"/>
                                       </svg>`
                                    : `<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" fill="none" stroke="#dc3545" stroke-width="2" class="bi bi-x-lg" viewBox="0 0 16 16">
                                          <line x1="4" y1="4" x2="12" y2="12" />
                                          <line x1="12" y1="4" x2="4" y2="12" />
                                       </svg>`
                                }
                            </button>
                            <h5 class="mb-0 d-inline-block editable-instance-name" style="cursor:pointer;" data-instance-name="${instance.name}">
                                <span class="display-instance-name">${instance.name}</span>
                                <span class="edit-instance-name-btn" title="Редактировать название" style="color: #888; cursor: pointer;">
                                    <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" fill="currentColor" class="bi bi-pencil" viewBox="0 0 16 16">
                                        <path d="M12.146.854a.5.5 0 0 1 .708 0l2.292 2.292a.5.5 0 0 1 0 .708l-10 10A.5.5 0 0 1 4.5 14H2.5a.5.5 0 0 1-.5-.5v-2a.5.5 0 0 1 .146-.354l10-10zM11.207 2L14 4.793 13.5 5.5 10.707 2.707l.5-.5zm1.086 2.121L12.207 4.5 9.5 7.207V8h.793l2.707-2.707zM3 13v1h1l8.293-8.293-1-1L3 13z"/>
                                    </svg>
                                </span>
                            </h5>
                        </div>
                        <button type="button" class="btn btn-danger btn-sm openai-instance-remove-btn" data-instance-name="${instance.name}">Удалить инстанс</button>
                    </div>
                    <div class="card-body">
                        <p class="card-text editable-instance-base-url" style="cursor:pointer;">
                            <strong>Base URL:</strong>
                            <span class="display-instance-base-url">${instance.base_url}</span>
                            <span class="edit-instance-base-url-btn" title="Редактировать Base URL" style="color: #888; cursor: pointer;">
                                <svg xmlns="http://www.w3.org/2000/svg" width="17" height="17" fill="currentColor" class="bi bi-pencil" viewBox="0 0 16 16">
                                    <path d="M12.146.854a.5.5 0 0 1 .708 0l2.292 2.292a.5.5 0 0 1 0 .708l-10 10A.5.5 0 0 1 4.5 14H2.5a.5.5 0 0 1-.5-.5v-2a.5.5 0 0 1 .146-.354l10-10zM11.207 2L14 4.793 13.5 5.5 10.707 2.707l.5-.5zm1.086 2.121L12.207 4.5 9.5 7.207V8h.793l2.707-2.707zM3 13v1h1l8.293-8.293-1-1L3 13z"/>
                                </svg>
                            </span>
                        </p>
                        <div class="form-check form-switch mb-2">
                            <input class="form-check-input openai-instance-proxy-switch" type="checkbox" id="use_global_proxy_switch_${instance.name}" data-instance-name="${instance.name}" ${useGlobalProxyChecked}>
                            <label class="form-check-label" for="use_global_proxy_switch_${instance.name}">
                                Использовать глобальный прокси для этого инстанса
                            </label>
                        </div>
                        <div class="form-check form-switch mb-2">
                            <input class="form-check-input openai-instance-custom-tokenizer-switch" type="checkbox" id="use_custom_tokenizer_switch_${instance.name}" data-instance-name="${instance.name}" ${instance.use_custom_tokenizer ? "checked" : ""}>
                            <label class="form-check-label" for="use_custom_tokenizer_switch_${instance.name}">
                                Применить кастомный подсчёт токенов
                            </label>
                        </div>
                        <h6>API Ключи:</h6>
                        ${keysHtml}
                        <form class="openai-instance-key-add-form mt-2" data-instance-name="${instance.name}">
                            <div class="input-group input-group-sm">
                                <input type="text" name="api_key" class="form-control" placeholder="Новый API ключ" required>
                                <button type="submit" class="btn btn-primary btn-sm">Добавить ключ</button>
                            </div>
                        </form>

                        <div class="mt-3 mb-1">
                          ${failsafeHtml}
                        </div>
                        <div class="mt-3">
                          <label class="form-label">Model aliases (JSON)</label>
                          <textarea class="form-control form-control-sm openai-instance-aliases-json" rows="4" data-instance-name="${instance.name}">${aliasesJson}</textarea>
                          <label class="form-label mt-2">Model redirects (JSON)</label>
                          <textarea class="form-control form-control-sm openai-instance-redirects-json" rows="4" data-instance-name="${instance.name}">${redirectsJson}</textarea>
                          <button type="button" class="btn btn-outline-primary btn-sm mt-2 openai-instance-save-mappings-btn" data-instance-name="${instance.name}">Сохранить aliases/redirects</button>
                        </div>
                    </div>
                `;
                instancesSection.appendChild(instanceDiv);

                // ----- Кнопка "Редактировать API-ключ" -----
                instanceDiv.querySelectorAll('.edit-instance-key-btn').forEach((editKeyBtn, idx) => {
                    const displayKeySpan = editKeyBtn.previousElementSibling;
                    if (!displayKeySpan) return;
                    editKeyBtn.addEventListener('click', function () {
                        keyValue = displayKeySpan.textContent;
                        const input = document.createElement('input');
                        input.type = "text";
                        input.value = keyValue;
                        input.className = "form-control form-control-sm d-inline-block";
                        input.style.width = "220px";
                        displayKeySpan.replaceWith(input);
                        input.focus();
                        input.addEventListener('blur', async function () {
                            const val = input.value.trim();
                            if (val && val !== keyValue) {
                                try {
                                    const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instance.name)}/keys`;
                                    const payload = { old_api_key: keyValue, new_api_key: val };
                                    const res = await makeApiRequest(url, 'PATCH', payload);
                                    window.showNotification('notification_area',res.message || 'API-ключ изменён.');
                                    loadDashboardData();
                                } catch (e) {}
                            } else {
                                input.replaceWith(displayKeySpan);
                            }
                // attach failsafe (add/remove) handlers after dom insert
                // REMOVE handler as ранее — останется на каждом блоке
                instanceDiv.querySelectorAll('.openai-failsafe-remove-btn').forEach(btn => {
                  btn.addEventListener('click', async function() {
                    const provToRemove = btn.dataset.prov;
                    const instName = btn.dataset.instanceName;
                    const newFailsafe = failsafeList.filter(p => p !== provToRemove);
                    try {
                      const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instName)}/meta`;
                      const res = await makeApiRequest(url, 'PATCH', { failsafe_providers: newFailsafe });
                      window.showNotification('notification_area', res.message || 'Failsafe-провайдер удалён');
                      loadDashboardData();
                    } catch (e) {}
                  });
                });
                // ADD handler — через делегирование
                // Удаляем addEventListener и setTimeout на каждую кнопку, вместо этого — один общий делегат ниже

            });
                        input.addEventListener('keydown', function (e) {
                            if (e.key === 'Enter') input.blur();
                            if (e.key === 'Escape') { input.replaceWith(displayKeySpan); }
                        });
                    });
                });

                // Inline editor instance name
                const editNameBtn = instanceDiv.querySelector('.edit-instance-name-btn');
                const displayNameSpan = instanceDiv.querySelector('.display-instance-name');
                editNameBtn?.addEventListener('click', function () {
                    const input = document.createElement('input');
                    input.type = "text";
                    input.value = instance.name;
                    input.className = "form-control form-control-sm d-inline-block";
                    input.style.width = "120px";
                    displayNameSpan.replaceWith(input);
                    input.focus();
                    input.addEventListener('blur', async function () {
                        const val = input.value.trim();
                        if (val && val !== instance.name) {
                            // PATCH запрос, имя и старое имя
                            try {
                                const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instance.name)}/meta`;
                                const res = await makeApiRequest(url, 'PATCH', { name: val });
                                window.showNotification('notification_area',res.message || 'Название инстанса изменено.');
                                loadDashboardData();
                            } catch (e) {}
                        } else {
                            input.replaceWith(displayNameSpan);
                        }
                    });
                    input.addEventListener('keydown', function(e){
                        if (e.key === 'Enter') input.blur();
                        if (e.key === 'Escape') {input.replaceWith(displayNameSpan);}
                    });
                });

                // Inline editor base_url
                const editBaseBtn = instanceDiv.querySelector('.edit-instance-base-url-btn');
                const displayBaseUrlSpan = instanceDiv.querySelector('.display-instance-base-url');
                editBaseBtn?.addEventListener('click', function () {
                    const input = document.createElement('input');
                    input.type = "url";
                    input.value = instance.base_url;
                    input.className = "form-control form-control-sm d-inline-block";
                    input.style.width = "280px";
                    displayBaseUrlSpan.replaceWith(input);
                    input.focus();
                    input.addEventListener('blur', async function () {
                        const val = input.value.trim();
                        if (val && val !== instance.base_url) {
                            try {
                                const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instance.name)}/meta`;
                                const res = await makeApiRequest(url, 'PATCH', { base_url: val });
                                window.showNotification('notification_area',res.message || 'Base URL изменён.');
                                loadDashboardData();
                            } catch (e) {}
                        } else {
                            input.replaceWith(displayBaseUrlSpan);
                        }
                    });
                    input.addEventListener('keydown', function(e){
                        if (e.key === 'Enter') input.blur();
                        if (e.key === 'Escape') {input.replaceWith(displayBaseUrlSpan);}
                    });
                });

            });
        } else {
            instancesSection.innerHTML = '<p>Нет настроенных инстансов OpenAI Compatible.</p>';
        }


        attachFormHandlers(); 
        // чекаем чекбоксы для прокси у модулей
        document.querySelectorAll('.module-proxy-switch').forEach(switchElem => {
            switchElem.addEventListener('change', async function(e) {
                const checked = switchElem.checked;
                const moduleName = switchElem.dataset.moduleName;
                try {
                    const url = `/api/admin/ui/settings/module/${encodeURIComponent(moduleName)}/proxy-settings`;
                    const res = await makeApiRequest(url, 'PUT', { use_global_proxy: checked });
                    window.showNotification('notification_area',res.message || `Настройка прокси для модуля "${moduleName}" обновлена.`);
                    loadDashboardData();
                } catch (err) { /* ошибка обработается глобально */ }
            });
        });
        // После динамического рендера добавляем обработчик свитчеров proxy
        document.querySelectorAll('.openai-instance-proxy-switch').forEach(switchElem => {
            switchElem.addEventListener('change', async function(e) {
                const checked = switchElem.checked;
                const instanceName = switchElem.dataset.instanceName;
                try {
                    const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instanceName)}/meta`;
                    const res = await makeApiRequest(url, 'PATCH', { use_global_proxy: checked });
                    window.showNotification('notification_area', res.message || `Настройка прокси для инстанса "${instanceName}" обновлена.`);
                    loadDashboardData();
                } catch (err) { /* ошибка обработается глобально */ }
            });
        });
        // Обработка чекбокса кастомного токенайзера
        document.querySelectorAll('.openai-instance-custom-tokenizer-switch').forEach(switchElem => {
            switchElem.addEventListener('change', async function(e) {
                const checked = switchElem.checked;
                const instanceName = switchElem.dataset.instanceName;
                try {
                    const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instanceName)}/meta`;
                    const res = await makeApiRequest(url, 'PATCH', { use_custom_tokenizer: checked });
                    window.showNotification('notification_area', res.message || `Настройка кастомного токенайзера для инстанса "${instanceName}" обновлена.`);
                    loadDashboardData();
                } catch (err) { /* ошибка обработается глобально */ }
            });
        });
    } catch (error) {
        // Ошибка уже обработана в makeApiRequest
    }
}

function attachFormHandlers() {
    if (handlersAttached) {
        return;
    }
    // Настройки прокси
    ['form_use_proxies', 'form_rotation_mode', 'form_force_proxy_rotation', 'form_select_random_proxy'].forEach(formId => {
        const form = document.getElementById(formId);
        if(form) form.addEventListener('submit', async function(event) {
            event.preventDefault();
            const select = form.querySelector('select');
            const settingName = select.name;
            let value = select.value;
            if (settingName === 'use_proxies' || settingName === 'force_proxy_rotation_after_request' || settingName === 'select_random_proxy_each_request') {
                value = (value === 'true');
            }
            try {
                const result = await makeApiRequest(URLS.updateProxySettings, 'PUT', { setting_name: settingName, value: value });
                window.showNotification('notification_area',result.message || 'Настройка прокси обновлена.');
                loadDashboardData();
            } catch (e) { /* ошибка уже показана */ }
        });
    });

    // Управление API ключами сервисов
    document.getElementById('api_keys_management_section').addEventListener('submit', async function(event) {
        event.preventDefault();
        const form = event.target;
        if (!form.classList.contains('api-key-add-form') && !form.classList.contains('api-key-remove-form')) return;

        const serviceName = form.dataset.service;

        if (form.classList.contains('api-key-add-form')) {
            const apiKeyInput = form.querySelector('input[name="api_key"]');
            const apiKey = apiKeyInput.value;
            if (!apiKey) { window.showNotification('notification_area','Ключ API не может быть пустым.', 'error'); return; }
            try {
                const url = URLS.addServiceKey.replace('SERVICE_NAME_PLACEHOLDER', serviceName);
                const result = await makeApiRequest(url, 'POST', { api_key: apiKey });
                window.showNotification && window.showNotification('notification_area', result.message || 'Ключ API добавлен.');
                apiKeyInput.value = ''; // Очистить поле ввода
                loadDashboardData();
            } catch (e) { /* ошибка уже показана */ }
        } else if (form.classList.contains('api-key-remove-form')) {
            if (!confirm('Вы уверены, что хотите удалить этот ключ?')) return;
            const apiKey = form.dataset.key;
            try {
                const url = URLS.deleteServiceKey.replace('SERVICE_NAME_PLACEHOLDER', serviceName);
                const result = await makeApiRequest(url, 'DELETE', { api_key: apiKey });
                window.showNotification && window.showNotification('notification_area', result.message || 'Ключ API удален.');
                loadDashboardData();
            } catch (e) { /* ошибка уже показана */ }
        }
    });
    
    // Управление Прокси
    const proxyManagementSection = document.getElementById('proxy_management_section_container');
    if(proxyManagementSection) proxyManagementSection.addEventListener('submit', async function(event){
        event.preventDefault();
        const form = event.target;
        if(form.id === 'add_proxy_form'){
            const typeInput = form.querySelector('#new_proxy_type');
            const urlInput = form.querySelector('#new_proxy_url');
            const type = typeInput.value;
            const urlValue = urlInput.value;
            if(!urlValue) { window.showNotification('notification_area','URL прокси не может быть пустым.', 'error'); return; }
            try {
                const result = await makeApiRequest(URLS.addProxy, 'POST', {type, url: urlValue});
                window.showNotification('notification_area',result.message || 'Прокси добавлен.');
                urlInput.value = ''; // Очистить поле
                loadDashboardData();
            } catch (e) {}
        } else if (form.classList.contains('proxy-remove-form')){
            if (!confirm('Вы уверены, что хотите удалить этот прокси?')) return;
            const urlValue = form.dataset.url;
             try {
                const result = await makeApiRequest(URLS.deleteProxy, 'DELETE', {url: urlValue});
                window.showNotification('notification_area',result.message || 'Прокси удален.');
                loadDashboardData();
            } catch (e) {}
        } else if (form.id === 'reload_proxies_form'){
             try {
                const result = await makeApiRequest(URLS.reloadProxies, 'POST');
                window.showNotification('notification_area',result.message || 'Список прокси перезагружен.');
                loadDashboardData();
            } catch (e) {}
        } else if (form.id === 'shuffle_proxies_form'){
             try {
                const result = await makeApiRequest(URLS.shuffleProxies, 'POST');
                window.showNotification('notification_area',result.message || 'Список прокси перемешан.');
                loadDashboardData();
            } catch (e) {}
        }
    });

    // Управление модулями
    document.getElementById('module_management_section').addEventListener('submit', async function(event){
        event.preventDefault();
        const form = event.target;
        if(form.classList.contains('module-status-form')){
            const moduleName = form.dataset.moduleName;
            const isActive = form.querySelector('select[name="module_status"]').value === 'true';
            try {
                const url = URLS.updateModuleStatus.replace('MODULE_NAME_PLACEHOLDER', moduleName);
                const result = await makeApiRequest(url, 'PUT', {active: isActive});
                window.showNotification && window.showNotification('notification_area', result.message || `Статус модуля ${moduleName} обновлен.`);
                loadDashboardData();
            } catch (e) {}
        }
    });

    document.getElementById('reload_modules_form')?.addEventListener('submit', async function(event) {
        event.preventDefault();
        try {
            const result = await makeApiRequest(URLS.reloadModules, 'POST');
            window.showNotification('notification_area', result.message || 'Модули перезагружены.');
            loadDashboardData();
        } catch (e) {}
    });

    document.getElementById('reload_https_form')?.addEventListener('submit', async function(event) {
        event.preventDefault();
        try {
            const result = await makeApiRequest(URLS.renewHttps, 'POST', { force_renewal: false });
            window.showNotification('notification_area', result.message || 'HTTPS сертификаты обновлены.');
        } catch (e) {}
    });
    
    // Безопасность AIRouter API
    document.getElementById('form_require_airouter_api_key')?.addEventListener('submit', async function(event){
        event.preventDefault();
        const isActive = document.getElementById('require_airouter_api_key').value === 'true';
        try {
            const result = await makeApiRequest(URLS.updateAirouterSecurity, 'PUT', {require_api_key: isActive});
            window.showNotification('notification_area',result.message || 'Настройка безопасности AIRouter API обновлена.');
            loadDashboardData();
        } catch (e) {}
    });

    // Ключи AIRouter
    document.getElementById('form_generate_airouter_key')?.addEventListener('submit', async function(event){
        event.preventDefault();
         try {
            const result = await makeApiRequest(URLS.generateAirouterKey, 'POST');
            window.showNotification('notification_area',result.message || 'Новый ключ AIRouter сгенерирован.');
            if(result.new_key) window.showNotification('notification_area',`Новый ключ: ${result.new_key}`); // Показываем сам ключ
            loadDashboardData();
        } catch (e) {}
    });
    document.getElementById('airouter_api_keys_list')?.addEventListener('submit', async function(event){
         event.preventDefault();
         const form = event.target;
         if(form.classList.contains('airouter-key-remove-form')){
            if (!confirm('Вы уверены, что хотите удалить этот API-ключ AIRouter?')) return;
            const apiKey = form.dataset.key;
            try {
                const result = await makeApiRequest(URLS.deleteAirouterKey, 'DELETE', {api_key: apiKey});
                window.showNotification('notification_area',result.message || 'Ключ AIRouter удален.');
                loadDashboardData();
            } catch (e) {}
         }
    });

    // Управление инстансами OpenAI Compatible
    document.getElementById('form_add_openai_instance')?.addEventListener('submit', async function(event) {
        event.preventDefault();
        const form = event.target;
        const name = form.elements['name'].value;
        const baseUrl = form.elements['base_url'].value;
        const apiKeysRaw = form.elements['api_keys'].value;
        const aliasesRaw = form.elements['model_aliases']?.value || '{}';
        const redirectsRaw = form.elements['model_redirects']?.value || '{}';
        const apiKeys = apiKeysRaw.split(',').map(k => k.trim()).filter(k => k);

        if (!name || !baseUrl) {
            window.showNotification('notification_area','Поля Название и Base URL обязательны.', 'error');
            return;
        }
        try {
            const modelAliases = parseJsonObjectOrThrow(aliasesRaw, 'Model aliases');
            const modelRedirects = parseJsonObjectOrThrow(redirectsRaw, 'Model redirects');
            const result = await makeApiRequest(URLS.addOpenAIInstance, 'POST', {
                name,
                base_url: baseUrl,
                api_keys: apiKeys,
                model_aliases: modelAliases,
                model_redirects: modelRedirects,
            });
            window.showNotification('notification_area', result.message || 'Инстанс OpenAI Compatible добавлен.');
            form.reset();
            loadDashboardData();
        } catch (e) { /* ошибка уже показана */ }
    });

    document.getElementById('openai_instances_management_section').addEventListener('click', async function(event) {
        const target = event.target;
        const instanceName = target.dataset.instanceName || target.closest('.openai-instance-enabled-toggle-btn')?.dataset.instanceName;

        // Вкл/выкл инстанс
        if (target.classList.contains('openai-instance-enabled-toggle-btn') ||
            target.closest('.openai-instance-enabled-toggle-btn')) {
            const btn = target.classList.contains('openai-instance-enabled-toggle-btn')
                ? target
                : target.closest('.openai-instance-enabled-toggle-btn');
            const enabledNow = btn.dataset.enabled === 'true';
            try {
                const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instanceName)}/enabled`;
                const result = await makeApiRequest(url, 'PATCH', { enabled: !enabledNow });
                window.showNotification('notification_area', result.message || (!enabledNow ? 'Инстанс включён.' : 'Инстанс отключён.'));
                loadDashboardData();
            } catch (e) {}
            return;
        }

        if (target.classList.contains('openai-instance-save-mappings-btn')) {
            try {
                const card = target.closest('.card');
                const aliasesRaw = card.querySelector('.openai-instance-aliases-json')?.value || '{}';
                const redirectsRaw = card.querySelector('.openai-instance-redirects-json')?.value || '{}';
                const modelAliases = parseJsonObjectOrThrow(aliasesRaw, 'Model aliases');
                const modelRedirects = parseJsonObjectOrThrow(redirectsRaw, 'Model redirects');
                const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instanceName)}/meta`;
                const result = await makeApiRequest(url, 'PATCH', {
                    model_aliases: modelAliases,
                    model_redirects: modelRedirects,
                });
                window.showNotification('notification_area', result.message || 'Mappings сохранены.');
                loadDashboardData();
            } catch (e) {}
            return;
        }

        // Удаление инстанса
        if (target.classList.contains('openai-instance-remove-btn')) {
            if (!confirm(`Вы уверены, что хотите удалить инстанс "${instanceName}"?`)) return;
            try {
                const url = URLS.deleteOpenAIInstance.replace('INSTANCE_NAME_PLACEHOLDER', encodeURIComponent(instanceName));
                const result = await makeApiRequest(url, 'DELETE');
                window.showNotification('notification_area', result.message || `Инстанс "${instanceName}" удален.`);
                loadDashboardData();
            } catch (e) { 
                window.showNotification('notification_area', `Инстанс "${instanceName}" не был удален. Подробнее: ${e.message}`, 'error', 4000);}
        }
        // Удаление ключа инстанса
        if (target.classList.contains('openai-instance-key-remove-btn')) {
            const apiKey = target.dataset.key;
            if (!confirm(`Вы уверены, что хотите удалить ключ ...${apiKey.slice(-4)} для инстанса "${instanceName}"?`)) return;
            try {
                const url = URLS.deleteOpenAIInstanceKey.replace('INSTANCE_NAME_PLACEHOLDER', encodeURIComponent(instanceName));
                const result = await makeApiRequest(url, 'DELETE', { api_key: apiKey });
                window.showNotification('notification_area',result.message || 'Ключ API удален.');
                loadDashboardData();
            } catch (e) { /* ошибка уже показана */ }
        }
    });
    
    document.getElementById('openai_instances_management_section').addEventListener('submit', async function(event) {
        event.preventDefault();
        const form = event.target;
        // Добавление ключа к инстансу
        if (form.classList.contains('openai-instance-key-add-form')) {
            const instanceName = form.dataset.instanceName;
            const apiKeyInput = form.querySelector('input[name="api_key"]');
            const apiKey = apiKeyInput.value;
            if (!apiKey) { window.showNotification('notification_area','Ключ API не может быть пустым.', 'error'); return; }
            try {
                const url = URLS.addOpenAIInstanceKey.replace('INSTANCE_NAME_PLACEHOLDER', encodeURIComponent(instanceName));
                const result = await makeApiRequest(url, 'POST', { api_key: apiKey });
                window.showNotification('notification_area',result.message || 'Ключ API добавлен к инстансу.');
                apiKeyInput.value = '';
                loadDashboardData();
            } catch (e) { /* ошибка уже показана */ }
        }
    });

    // Делегирование для кнопки добавления/удаления и drag&drop failsafe-провайдера
    const instancesSection = document.getElementById('openai_instances_management_section');
    instancesSection.addEventListener('click', async function(event) {
      // ADD handler
      if (event.target.classList.contains('openai-failsafe-add-btn')) {
        const addBtn = event.target;
        const instName = addBtn.dataset.instanceName;
        const instanceCard = addBtn.closest('.card');
        // Получаем select в пределах текущей карточки
        const combo = instanceCard.querySelector('.openai-failsafe-combo');
        const val = combo && combo.value ? combo.value : null;
        if (!val) {
          window.showNotification && window.showNotification('notification_area', 'Выберите резервного провайдера для добавления.', 'error');
          return;
        }
        // Собираем текущий список из DOM
        const failsListUl = instanceCard.querySelector('.openai-failsafe-list');
        const liElements = failsListUl ? Array.from(failsListUl.querySelectorAll('li')) : [];
        let currentList = liElements.map(li => li.querySelector('.openai-failsafe-remove-btn')?.dataset.prov).filter(Boolean);
        if (currentList.includes(val)) return;
        currentList = currentList.concat([val]);
        try {
          const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instName)}/meta`;
          const res = await makeApiRequest(url, 'PATCH', { failsafe_providers: currentList });
          window.showNotification('notification_area', res.message || 'Failsafe-провайдер добавлен');
          combo.selectedIndex = 0;
          loadDashboardData();
        } catch (e) {}
      }
      // REMOVE handler
      if (event.target.classList.contains('openai-failsafe-remove-btn')) {
        const removeBtn = event.target;
        const instName = removeBtn.dataset.instanceName;
        const provToRemove = removeBtn.dataset.prov;
        const instanceCard = removeBtn.closest('.card');
        // Собрать оставшиеся кроме удаляемого
        const failsListUl = instanceCard.querySelector('.openai-failsafe-list');
        const liElements = failsListUl ? Array.from(failsListUl.querySelectorAll('li')) : [];
        let currentList = liElements
          .map(li => li.querySelector('.openai-failsafe-remove-btn')?.dataset.prov)
          .filter(p => p && p !== provToRemove);
        try {
          const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instName)}/meta`;
          const res = await makeApiRequest(url, 'PATCH', { failsafe_providers: currentList });
          window.showNotification('notification_area', res.message || 'Failsafe-провайдер удалён');
          loadDashboardData();
        } catch (e) {}
      }
    });


    // Drag & drop для failsafe-провайдеров
    let dragSrcEl = null;
    instancesSection.addEventListener('dragstart', function(event) {
      const li = event.target.closest('.openai-failsafe-draggable');
      if (!li) return;
      dragSrcEl = li;
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('text/plain', li.dataset.prov);
      setTimeout(() => li.classList.add('dragging'), 0);
    });

    instancesSection.addEventListener('dragover', function(event) {
      const li = event.target.closest('.openai-failsafe-draggable');
      if (!li) return;
      event.preventDefault();
      li.classList.add('dragover');
    });

    instancesSection.addEventListener('dragleave', function(event) {
      const li = event.target.closest('.openai-failsafe-draggable');
      if (li) li.classList.remove('dragover');
    });

    instancesSection.addEventListener('drop', async function(event) {
      const li = event.target.closest('.openai-failsafe-draggable');
      if (!li || !dragSrcEl || li === dragSrcEl) return;
      event.preventDefault();
      li.classList.remove('dragover');
      // Перемещаем элемент
      const ul = li.parentNode;
      ul.insertBefore(dragSrcEl, li.nextSibling === dragSrcEl ? li : li.nextSibling);
      // Собираем новый порядок
      const provs = Array.from(ul.querySelectorAll('.openai-failsafe-draggable')).map(node => node.dataset.prov);
      // Получаем инстанс
      const instanceCard = ul.closest('.card');
      const instName = instanceCard.querySelector('.openai-failsafe-add-btn').dataset.instanceName;
      try {
        const url = `/api/admin/ui/settings/openai-instances/${encodeURIComponent(instName)}/meta`;
        const res = await makeApiRequest(url, 'PATCH', { failsafe_providers: provs });
        window.showNotification('notification_area', res.message || 'Порядок failsafe-провайдеров обновлён');
        loadDashboardData();
      } catch (e) {}
    });

    instancesSection.addEventListener('dragend', function(event) {
      const li = event.target.closest('.openai-failsafe-draggable');
      if (li) li.classList.remove('dragging');
      dragSrcEl = null;
      // после drop/even if not dropped - снимаем выделение со всех
      instancesSection.querySelectorAll('.openai-failsafe-draggable').forEach(el => el.classList.remove('dragover'));
    });

    handlersAttached = true;
}

function setupAdminCategoryTabs() {
    const tabsRoot = document.getElementById('admin_category_tabs');
    if (!tabsRoot) return;
    tabsRoot.addEventListener('click', (event) => {
        const btn = event.target.closest('button[data-category]');
        if (!btn) return;
        const category = btn.dataset.category;
        tabsRoot.querySelectorAll('.nav-link').forEach((n) => n.classList.remove('active'));
        btn.classList.add('active');
        document.querySelectorAll('.admin-category-card').forEach((card) => {
            const own = String(card.dataset.category || '');
            if (category === 'all' || own.split(/\s+/).includes(category)) {
                card.style.display = '';
            } else {
                card.style.display = 'none';
            }
        });
    });
}

async function loadMcpData() {
    const section = document.getElementById('mcp_management_section');
    if (!section) return;
    try {
        const [servers, toolsResponse] = await Promise.all([
            makeApiRequest(URLS.getMcpServers),
            makeApiRequest(URLS.listMcpTools),
        ]);
        const tools = Array.isArray(toolsResponse.tools) ? toolsResponse.tools : [];
        const grouped = {};
        tools.forEach((t) => {
            const server = t.mcp_server || 'unknown';
            if (!grouped[server]) grouped[server] = [];
            grouped[server].push(t.name || 'unknown_tool');
        });
        if (!Array.isArray(servers) || servers.length === 0) {
            section.innerHTML = '<p>Нет MCP серверов. Добавьте подключение ниже.</p>';
            return;
        }
        section.innerHTML = servers.map((s) => {
            const name = s.name;
            const statusText = s.enabled ? 'Enabled' : 'Disabled';
            const toolList = (grouped[name] || []).slice(0, 8).join(', ');
            return `
                <div class="card mb-3">
                    <div class="card-body">
                        <div class="d-flex justify-content-between align-items-start gap-2">
                            <div>
                                <h5 class="mb-1">${name}</h5>
                                <div class="small text-muted">${s.base_url}${s.jsonrpc_path || '/mcp'}</div>
                                <div class="small">Policy: <code>${s.expose_policy || 'internal_only'}</code> | ${statusText}</div>
                                <div class="small text-muted">Tools: ${toolList || 'none discovered'}</div>
                            </div>
                            <div class="d-flex gap-2">
                                <button type="button" class="btn btn-outline-primary btn-sm mcp-test-btn" data-server="${name}">Test</button>
                                <button type="button" class="btn btn-outline-danger btn-sm mcp-delete-btn" data-server="${name}">Delete</button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');
    } catch (_e) {
        section.innerHTML = '<p class="text-danger">Не удалось загрузить MCP данные.</p>';
    }
}

function attachMcpHandlers() {
    const form = document.getElementById('form_add_mcp_server');
    if (form) {
        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const payload = {
                name: document.getElementById('mcp_name').value.trim(),
                base_url: document.getElementById('mcp_base_url').value.trim(),
                jsonrpc_path: document.getElementById('mcp_jsonrpc_path').value.trim() || '/mcp',
                auth_token: document.getElementById('mcp_auth_token').value.trim(),
                timeout_seconds: 20,
                enabled: true,
                expose_policy: 'internal_only',
            };
            try {
                const res = await makeApiRequest(URLS.addMcpServer, 'POST', payload);
                window.showNotification('notification_area', res.message || 'MCP сервер добавлен');
                form.reset();
                document.getElementById('mcp_jsonrpc_path').value = '/mcp';
                await loadMcpData();
            } catch (_e) {}
        });
    }
    const section = document.getElementById('mcp_management_section');
    if (!section) return;
    section.addEventListener('click', async (event) => {
        const testBtn = event.target.closest('.mcp-test-btn');
        if (testBtn) {
            const name = testBtn.dataset.server;
            const url = URLS.testMcpServer.replace('SERVER_NAME_PLACEHOLDER', encodeURIComponent(name));
            try {
                const res = await makeApiRequest(url, 'POST', {});
                window.showNotification('notification_area', res.ok ? `MCP ${name}: ok (${res.tools_count} tools)` : `MCP ${name}: ${res.error || 'error'}`, res.ok ? 'success' : 'error');
            } catch (_e) {}
            return;
        }
        const delBtn = event.target.closest('.mcp-delete-btn');
        if (delBtn) {
            const name = delBtn.dataset.server;
            if (!window.confirm(`Удалить MCP сервер ${name}?`)) return;
            const url = URLS.deleteMcpServer.replace('SERVER_NAME_PLACEHOLDER', encodeURIComponent(name));
            try {
                const res = await makeApiRequest(url, 'DELETE');
                window.showNotification('notification_area', res.message || 'MCP сервер удален');
                await loadMcpData();
            } catch (_e) {}
        }
    });
}

document.addEventListener('DOMContentLoaded', function() {
    setupAdminCategoryTabs();
    attachMcpHandlers();
    loadDashboardData();
    loadMcpData();
});
