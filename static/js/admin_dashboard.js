// Предполагается, что объект URLS будет доступен глобально из HTML-шаблона
let handlersAttached = false;

function showNotification(message, type = 'success') {
    const notificationArea = document.getElementById('notification_area');
    const notification = document.createElement('div');
    notification.className = `notification ${type}`;
    notification.innerText = message;
    notificationArea.appendChild(notification);
    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 5000);
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
        const responseData = await response.json();
        if (!response.ok) {
            throw new Error(responseData.detail || `Ошибка ${response.status}`);
        }
        return responseData;
    } catch (error) {
        console.error(`Ошибка API запроса к ${url}:`, error);
        showNotification(error.message || 'Сетевая ошибка или ошибка сервера.', 'error');
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
                            <span style="word-break: break-all; margin-right: 10px;">${key}</span>
                            <form class="api-key-remove-form" data-service="${service_name}" data-key="${key}">
                                <button type="submit" class="btn btn-danger btn-sm">Удалить</button>
                            </form>
                        </li>`;
                });
            } else {
                keysHtml += '<li>Нет ключей для этого сервиса.</li>';
            }
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
                            <span style="word-break: break-all; margin-right: 10px;">${key}</span>
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
                                <span style="word-break: break-all; margin-right: 10px;">${key}</span>
                                <button type="button" class="btn btn-danger btn-sm openai-instance-key-remove-btn" data-instance-name="${instance.name}" data-key="${key}">Удалить ключ</button>
                            </li>`;
                    });
                } else {
                    keysHtml += '<li class="list-group-item">Нет API ключей для этого инстанса.</li>';
                }
                keysHtml += '</ul>';

                instanceDiv.innerHTML = `
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h5 class="mb-0">Инстанс: ${instance.name}</h5>
                        <button type="button" class="btn btn-danger btn-sm openai-instance-remove-btn" data-instance-name="${instance.name}">Удалить инстанс</button>
                    </div>
                    <div class="card-body">
                        <p class="card-text"><strong>Base URL:</strong> ${instance.base_url}</p>
                        <h6>API Ключи:</h6>
                        ${keysHtml}
                        <form class="openai-instance-key-add-form mt-2" data-instance-name="${instance.name}">
                            <div class="input-group input-group-sm">
                                <input type="text" name="api_key" class="form-control" placeholder="Новый API ключ" required>
                                <button type="submit" class="btn btn-primary btn-sm">Добавить ключ</button>
                            </div>
                        </form>
                    </div>
                `;
                instancesSection.appendChild(instanceDiv);
            });
        } else {
            instancesSection.innerHTML = '<p>Нет настроенных инстансов OpenAI Compatible.</p>';
        }


        attachFormHandlers(); 
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
                showNotification(result.message || 'Настройка прокси обновлена.');
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
            if (!apiKey) { showNotification('Ключ API не может быть пустым.', 'error'); return; }
            try {
                const url = URLS.addServiceKey.replace('SERVICE_NAME_PLACEHOLDER', serviceName);
                const result = await makeApiRequest(url, 'POST', { api_key: apiKey });
                showNotification(result.message || 'Ключ API добавлен.');
                apiKeyInput.value = ''; // Очистить поле ввода
                loadDashboardData();
            } catch (e) { /* ошибка уже показана */ }
        } else if (form.classList.contains('api-key-remove-form')) {
            if (!confirm('Вы уверены, что хотите удалить этот ключ?')) return;
            const apiKey = form.dataset.key;
            try {
                const url = URLS.deleteServiceKey.replace('SERVICE_NAME_PLACEHOLDER', serviceName);
                const result = await makeApiRequest(url, 'DELETE', { api_key: apiKey });
                showNotification(result.message || 'Ключ API удален.');
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
            if(!urlValue) { showNotification('URL прокси не может быть пустым.', 'error'); return; }
            try {
                const result = await makeApiRequest(URLS.addProxy, 'POST', {type, url: urlValue});
                showNotification(result.message || 'Прокси добавлен.');
                urlInput.value = ''; // Очистить поле
                loadDashboardData();
            } catch (e) {}
        } else if (form.classList.contains('proxy-remove-form')){
            if (!confirm('Вы уверены, что хотите удалить этот прокси?')) return;
            const urlValue = form.dataset.url;
             try {
                const result = await makeApiRequest(URLS.deleteProxy, 'DELETE', {url: urlValue});
                showNotification(result.message || 'Прокси удален.');
                loadDashboardData();
            } catch (e) {}
        } else if (form.id === 'reload_proxies_form'){
             try {
                const result = await makeApiRequest(URLS.reloadProxies, 'POST');
                showNotification(result.message || 'Список прокси перезагружен.');
                loadDashboardData();
            } catch (e) {}
        } else if (form.id === 'shuffle_proxies_form'){
             try {
                const result = await makeApiRequest(URLS.shuffleProxies, 'POST');
                showNotification(result.message || 'Список прокси перемешан.');
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
                showNotification(result.message || `Статус модуля ${moduleName} обновлен.`);
                loadDashboardData();
            } catch (e) {}
        }
    });
    
    // Безопасность AIRouter API
    document.getElementById('form_require_airouter_api_key')?.addEventListener('submit', async function(event){
        event.preventDefault();
        const isActive = document.getElementById('require_airouter_api_key').value === 'true';
        try {
            const result = await makeApiRequest(URLS.updateAirouterSecurity, 'PUT', {require_api_key: isActive});
            showNotification(result.message || 'Настройка безопасности AIRouter API обновлена.');
            loadDashboardData();
        } catch (e) {}
    });

    // Ключи AIRouter
    document.getElementById('form_generate_airouter_key')?.addEventListener('submit', async function(event){
        event.preventDefault();
         try {
            const result = await makeApiRequest(URLS.generateAirouterKey, 'POST');
            showNotification(result.message || 'Новый ключ AIRouter сгенерирован.');
            if(result.new_key) showNotification(`Новый ключ: ${result.new_key}`, 'success'); // Показываем сам ключ
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
                showNotification(result.message || 'Ключ AIRouter удален.');
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
        const apiKeys = apiKeysRaw.split(',').map(k => k.trim()).filter(k => k);

        if (!name || !baseUrl || apiKeys.length === 0) {
            showNotification('Все поля (Название, Base URL, API Ключи) должны быть заполнены.', 'error');
            return;
        }
        try {
            const result = await makeApiRequest(URLS.addOpenAIInstance, 'POST', { name, base_url: baseUrl, api_keys: apiKeys });
            showNotification(result.message || 'Инстанс OpenAI Compatible добавлен.');
            form.reset();
            loadDashboardData();
        } catch (e) { /* ошибка уже показана */ }
    });

    document.getElementById('openai_instances_management_section').addEventListener('click', async function(event) {
        const target = event.target;
        const instanceName = target.dataset.instanceName;

        // Удаление инстанса
        if (target.classList.contains('openai-instance-remove-btn')) {
            if (!confirm(`Вы уверены, что хотите удалить инстанс "${instanceName}"?`)) return;
            try {
                const url = URLS.deleteOpenAIInstance.replace('INSTANCE_NAME_PLACEHOLDER', instanceName);
                const result = await makeApiRequest(url, 'DELETE');
                showNotification(result.message || `Инстанс "${instanceName}" удален.`);
                loadDashboardData();
            } catch (e) { /* ошибка уже показана */ }
        }
        // Удаление ключа инстанса
        if (target.classList.contains('openai-instance-key-remove-btn')) {
            const apiKey = target.dataset.key;
            if (!confirm(`Вы уверены, что хотите удалить ключ ...${apiKey.slice(-4)} для инстанса "${instanceName}"?`)) return;
            try {
                const url = URLS.deleteOpenAIInstanceKey.replace('INSTANCE_NAME_PLACEHOLDER', instanceName);
                const result = await makeApiRequest(url, 'DELETE', { api_key: apiKey });
                showNotification(result.message || 'Ключ API удален.');
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
            if (!apiKey) { showNotification('Ключ API не может быть пустым.', 'error'); return; }
            try {
                const url = URLS.addOpenAIInstanceKey.replace('INSTANCE_NAME_PLACEHOLDER', instanceName);
                const result = await makeApiRequest(url, 'POST', { api_key: apiKey });
                showNotification(result.message || 'Ключ API добавлен к инстансу.');
                apiKeyInput.value = '';
                loadDashboardData();
            } catch (e) { /* ошибка уже показана */ }
        }
    });

    handlersAttached = true;
}

document.addEventListener('DOMContentLoaded', function() {
    loadDashboardData();
});
