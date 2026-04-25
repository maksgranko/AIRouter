# Сборка и развёртывание DOCKER

Сборка:

- **Linux/MacOS**
  docker build -t ayrongamesdickovich/airouter:latest . && docker push ayrongamesdickovich/airouter:latest
- **Windows**
  docker build -t ayrongamesdickovich/airouter:latest . ; docker push ayrongamesdickovich/airouter:latest

Выполнение на сервере:

- **Linux/MacOS**
  docker pull ayrongamesdickovich/airouter:latest && docker run -d -p 80:8000 --env-file ./airouter.env ayrongamesdickovich/airouter:latest
- **Windows**
  docker pull ayrongamesdickovich/airouter:latest ; docker run -d -p 80:8000 --env-file ./airouter.env ayrongamesdickovich/airouter:latest

# AI API Роутер

Этот проект представляет собой OpenAI-совместимый API роутер, который позволяет направлять запросы к различным AI-сервисам (модулям), таким как OpenAI и Gemini. Он поддерживает управление API ключами, использование прокси-серверов с ротацией, а также имеет веб-панель администратора для управления конфигурацией. Версия приложения: **1.1.2a**.

## Возможности

- **OpenAI-Совместимость**: Используйте существующие клиенты OpenAI для взаимодействия с этим роутером.
- **Модульная Архитектура**: Легко добавляйте поддержку новых AI-сервисов.
  - Предустановленные модули: OpenAI, Gemini.
- **Управление API Ключами**:
  - Хранение ключей в JSON-файлах (`configs/openai_keys.json`, `configs/gemini_keys.json`, `configs/airouter_api_keys.json`).
  - Автоматическая ротация ключей при ошибках (для OpenAI/Gemini).
  - Управление ключами через веб-панель и JSON API.
  - Поддержка собственных API-ключей для защиты доступа к роутеру.
- **Поддержка Прокси**:
  - Использование HTTP/HTTPS/SOCKS4/SOCKS5 прокси.
  - Список прокси в `configs/proxies.json`.
  - Ротация прокси при ошибках.
  - Настройка использования и режима ротации через переменные окружения, веб-панель или JSON API.
- **Веб-Панель Администратора**:
  - Доступ по адресу `/admin/dashboard` (защищено HTTP Basic Authentication).
  - **Динамическая загрузка данных**: Дашборд загружает конфигурационные данные асинхронно через внутренний API (`/admin/ui/api/dashboard-data`), что делает интерфейс более отзывчивым.
  - Просмотр и управление настройками прокси.
  - Просмотр, добавление и удаление API ключей для AI-сервисов и для самого AIRouter.
  - Просмотр, добавление и удаление прокси-серверов.
  - Включение/выключение модулей AI-сервисов.
  - Управление требованием API-ключа AIRouter для доступа к основным эндпоинтам.
  - Страница со списком моделей (`/admin/models`).
  - Страница справки (`/admin/help`).
  - **API для кастомных дашбордов**: Предоставляет JSON API для интеграции и создания собственных интерфейсов управления (см. раздел "API Админ-панели").
- **Гибкая Конфигурация**:
  - Через переменные окружения (файл `.env`).
  - Через JSON-файлы в папке `configs`.
  - Через веб-панель администратора.
  - Через JSON API админ-панели.
  - Автоматическое создание конфигурационных файлов по умолчанию.

## Установка

1.  **Клонируйте репозиторий (если это репозиторий):**

    ```bash
    # git clone [URL вашего репозитория]
    # cd [название папки проекта]
    ```

    Если у вас просто файлы, перейдите в папку с проектом.

2.  **Создайте и активируйте виртуальное окружение (рекомендуется):**

    ```bash
    python -m venv venv
    # Windows
    venv\Scripts\activate
    # macOS/Linux
    source venv/bin/activate
    ```

3.  **Установите зависимости:**
    Убедитесь, что у вас установлен Python 3.7+ и pip.
    ```bash
    pip install -r requirements.txt
    ```

## Начальная Настройка

1.  **Создайте файл `.env`:**
    Скопируйте файл `configs/.env.example` (если он там) или создайте `.env` вручную в корне проекта.

    Содержимое `.env` файла:

    ```env
    ADMIN_USERNAME=admin
    ADMIN_PASSWORD=supersecret # ОБЯЗАТЕЛЬНО ИЗМЕНИТЕ ЭТОТ ПАРОЛЬ!

    # Настройки прокси (по умолчанию)
    # USE_PROXIES=true
    # PROXY_ROTATION_MODE=once # once, cycle, failover_cycle
    # SELECT_RANDOM_PROXY_EACH_REQUEST=false # true или false
    # FORCE_PROXY_ROTATION_AFTER_REQUEST=false # true или false
    ```

    Откройте файл `.env` в текстовом редакторе и настройте переменные:

    - `ADMIN_USERNAME`: Логин для панели администратора.
    - `ADMIN_PASSWORD`: **Обязательно измените** пароль для панели администратора на надежный.
    - Остальные переменные (для прокси) можно оставить закомментированными, если вас устраивают значения по умолчанию, управляемые через `configs/settings.json` и UI/API.

2.  **Конфигурационные файлы в папке `configs`:**
    При первом запуске приложения, если папка `configs` или файлы в ней отсутствуют, они будут созданы автоматически с содержимым по умолчанию.

    - `configs/settings.json`: Основной файл настроек. Управляет использованием прокси, режимами ротации, статусами модулей и требованием API-ключа AIRouter. Может быть изменен через UI или API.
    - `configs/openai_keys.json`: Список OpenAI API ключей. Пример: `["sk-xxxxxxxxx", "sk-yyyyyyyyy"]`
    - `configs/gemini_keys.json`: Список Gemini API ключей. Пример: `["ai-xxxxxxxxx", "ai-yyyyyyyyy"]`
    - `configs/airouter_api_keys.json`: Список API-ключей для доступа к самому AIRouter (если включено требование ключа). Пример: `["air_xxxxxxxxx", "air_yyyyyyyyy"]`
    - `configs/proxies.json`: Список прокси-серверов. Пример: `[{"type": "http", "url": "http://user:pass@host:port"}]`

    Вы можете заполнить `*_keys.json` и `proxies.json` вручную или через панель администратора/API.

## Запуск Приложения

Используйте Uvicorn для запуска FastAPI приложения:

```bash
uvicorn main:app --reload
# или же
python -m uvicorn main:app --reload
```

После запуска сервер будет доступен по адресу `http://127.0.0.1:8000`.

## HTTPS (Let's Encrypt)

Для production-развёртывания по HTTPS используйте отдельный reverse proxy.

- Пошаговая инструкция: `docs/DEPLOY_HTTPS.md`
- Быстрый скрипт Nginx + certbot: `scripts/setup_https_nginx_certbot.sh`

## Использование

### API Роутера (для AI-запросов)

- **Адрес API**: `http://127.0.0.1:8000/v1/...`
- **Эндпоинты**:
  - `/v1/chat/completions` (POST)
  - `/v1/completions` (POST)
  - `/v1/embeddings` (POST)
  - `/v1/models` (GET)
  - `/v1/models/{model_id}` (GET)
  - `/v1/moderations` (POST)
  - `/v1/images/generations` (POST)
  - `/v1/audio/transcriptions` (POST, `multipart/form-data`)
  - `/v1/audio/translations` (POST, `multipart/form-data`)
  - (и другие, если модуль их поддерживает, например, специфичные для OpenAI или Gemini эндпоинты, не покрытые стандартным API)
- **Выбор модуля/модели**: В теле JSON-запроса указывайте параметр `"model"`.
  - Пример для OpenAI: `{ "model": "openai/gpt-3.5-turbo", "messages": [...] }`
  - Пример для Gemini: `{ "model": "gemini/gemini-pro", "messages": [...] }`
- **Аутентификация API**:
  - Если в `configs/settings.json` (или через UI/API) установлено `"require_airouter_api_key": true`, то все запросы к `/v1/...` эндпоинтам должны содержать заголовок `Authorization: Bearer <ваш_airouter_api_ключ>`. Ключи управляются в `configs/airouter_api_keys.json` или через UI/API.
  - Если `"require_airouter_api_key": false`, то аутентификация для доступа к роутеру не требуется. Роутер использует ключи из `configs/*_keys.json` для аутентификации на стороне AI-сервисов.

### Панель Администратора (Веб-интерфейс)

- **Адрес**: `http://127.0.0.1:8000/admin/dashboard`
- **Аутентификация**: Используйте логин и пароль, заданные в переменных окружения `ADMIN_USERNAME` и `ADMIN_PASSWORD`.
- **Возможности**:
  - **Дашборд (`/admin/dashboard`)**: Отображает общую информацию и настройки. Данные загружаются асинхронно с использованием внутреннего JSON API.
  - **Настройки прокси**: Включение/выключение, режим ротации, принудительная ротация, случайный выбор.
  - **Управление API ключами**: Для OpenAI, Gemini и ключей AIRouter.
  - **Управление Прокси-серверами**: Добавление, удаление, перезагрузка из файла, перемешивание.
  - **Управление Модулями**: Включение/выключение модулей OpenAI, Gemini.
  - **Безопасность AIRouter**: Включение/выключение требования API-ключа AIRouter.
  - **Список Моделей (`/admin/models`)**: Просмотр моделей, доступных через активные модули.
  - **Справка (`/admin/help`)**: Подробная информация о конфигурации и использовании.

### API Админ-панели (JSON API для управления)

Роутер предоставляет внутренний JSON API для управления и получения данных конфигурации. Этот API используется стандартной веб-панелью администратора и может быть использован для создания собственных дашбордов или для автоматизации управления.

- **Префикс API**: `/api/admin/ui/` (обратите внимание, что полный путь к эндпоинтам будет, например, `/api/admin/ui/dashboard-data`, `/api/admin/ui/settings/proxy` и т.д.)
- **Аутентификация**: Все эндпоинты в `/api/admin/ui/` требуют той же HTTP Basic Authentication, что и остальная часть админ-панели (используйте `ADMIN_USERNAME` и `ADMIN_PASSWORD` из вашего `.env` файла).
- **Формат данных**: Все запросы с телом и ответы используют формат `application/json`.

**Пример вызова API с аутентификацией (используя `curl`):**

Для вызова эндпоинтов API админ-панели, вам необходимо передать данные Basic Authentication. Замените `your_admin_user` и `your_admin_password` на ваши актуальные учетные данные.

```bash
curl -u "your_admin_user:your_admin_password" -X GET http://127.0.0.1:8000/api/admin/ui/dashboard-data
```

Для эндпоинтов, принимающих JSON тело (например, PUT или POST):

```bash
curl -u "your_admin_user:your_admin_password" -X PUT \
  -H "Content-Type: application/json" \
  -d '{"setting_name": "use_proxies", "value": false}' \
  http://127.0.0.1:8000/api/admin/ui/settings/proxy
```

**Доступные эндпоинты:**
(Все пути указаны относительно префикса `/api/admin/ui/`)

1.  **Получение данных для дашборда (`/dashboard-data`):**

    - **`GET /api/admin/ui/dashboard-data`**
      - **Описание**: Возвращает все данные, необходимые для отображения основной страницы дашборда.
      - **Ответ (JSON)**: Структура, содержащая информацию о статусе прокси, режимах ротации, файлах конфигурации, списках ключей (OpenAI, Gemini, AIRouter), списках прокси, статусах модулей и версии приложения.
      - **Пример ответа (сокращенный)**:
        ```json
        {
          "proxy_manager_is_active": true,
          "proxy_manager_active_status": "Включено",
          // ... другие поля ...
          "app_version": "1.0.1"
        }
        ```

2.  **Управление настройками прокси (`/settings/proxy`):**

    - **`PUT /api/admin/ui/settings/proxy`**
      - **Описание**: Обновляет одну из настроек прокси.
      - **Тело запроса (JSON)**:
        ```json
        {
          "setting_name": "use_proxies", // или "rotation_mode", "force_proxy_rotation_after_request", "select_random_proxy_each_request"
          "value": true // или "cycle", false и т.д. в зависимости от setting_name
        }
        ```
      - **Ответ (JSON)**: `{"status": "success", "message": "Proxy setting '...' updated.", "updated_setting": {"...": ...}}`

3.  **Управление статусом модуля (`/settings/module/{module_name}`):**

    - **`PUT /api/admin/ui/settings/module/{module_name}`**
      - **Описание**: Включает или выключает указанный модуль.
      - **Параметр пути**: `{module_name}` - имя модуля (например, `openai`, `gemini`).
      - **Тело запроса (JSON)**:
        ```json
        {
          "active": true // или false
        }
        ```
      - **Ответ (JSON)**: `{"status": "success", "message": "Module '...' status updated to ..."}`

4.  **Управление API ключами сервисов (`/keys/service/...`):**

    - **`POST /api/admin/ui/keys/service/{service_name}`** (Status Code: 201 Created)
      - **Описание**: Добавляет новый API ключ для указанного сервиса.
      - **Параметр пути**: `{service_name}` - имя сервиса.
      - **Тело запроса (JSON)**:
        ```json
        {
          "api_key": "new_api_key_value"
        }
        ```
      - **Ответ (JSON)**: `{"status": "success", "message": "API key added for service '...'."}`
    - **`DELETE /api/admin/ui/keys/service/{service_name}`**
      - **Описание**: Удаляет API ключ для указанного сервиса.
      - **Параметр пути**: `{service_name}` - имя сервиса.
      - **Тело запроса (JSON)**:
        ```json
        {
          "api_key": "api_key_to_delete"
        }
        ```
      - **Ответ (JSON)**: `{"status": "success", "message": "API key removed for service '...'."}`

5.  **Управление API ключами AIRouter (`/keys/airouter`):**

    - **`POST /api/admin/ui/keys/airouter`** (Status Code: 201 Created)
      - **Описание**: Генерирует и добавляет новый API-ключ для AIRouter.
      - **Ответ (JSON)**: `{"status": "success", "message": "New AIRouter API key generated and added.", "new_key": "generated_key_value"}`
    - **`DELETE /api/admin/ui/keys/airouter`**
      - **Описание**: Удаляет указанный API-ключ AIRouter.
      - **Тело запроса (JSON)**:
        ```json
        {
          "api_key": "airouter_key_to_delete"
        }
        ```
      - **Ответ (JSON)**: `{"status": "success", "message": "AIRouter API key '...' removed."}`

6.  **Управление настройками безопасности AIRouter (`/settings/airouter-security`):**

    - **`PUT /api/admin/ui/settings/airouter-security`**
      - **Описание**: Включает или выключает требование API-ключа AIRouter для доступа к основным эндпоинтам.
      - **Тело запроса (JSON)**:
        ```json
        {
          "require_api_key": true // или false
        }
        ```
      - **Ответ (JSON)**: `{"status": "success", "message": "AIRouter API key requirement set to ..."}`

7.  **Управление списком прокси-серверов (`/proxies/...`):**

    - **`POST /api/admin/ui/proxies`** (Status Code: 201 Created)
      - **Описание**: Добавляет новый прокси-сервер в список.
      - **Тело запроса (JSON)**:
        ```json
        {
          "type": "http", // "http", "socks4", "socks5"
          "url": "http://user:pass@host:port"
        }
        ```
      - **Ответ (JSON)**: `{"status": "success", "message": "Proxy '...' added."}`
    - **`DELETE /api/admin/ui/proxies`**
      - **Описание**: Удаляет прокси-сервер из списка по его URL.
      - **Тело запроса (JSON)**:
        ```json
        {
          "url": "http://user:pass@host:port"
        }
        ```
      - **Ответ (JSON)**: `{"status": "success", "message": "Proxy '...' removed."}`
    - **`POST /api/admin/ui/proxies/reload`**
      - **Описание**: Перезагружает список прокси из файла `configs/proxies.json`.
      - **Ответ (JSON)**: `{"status": "success", "message": "Proxy list reloaded from file."}`
    - **`POST /api/admin/ui/proxies/shuffle`**
      - **Описание**: Перемешивает текущий список прокси в памяти и сохраняет измененный порядок в файл `configs/proxies.json`.
      - **Ответ (JSON)**: `{"status": "success", "message": "Proxy list shuffled and saved."}`

8.  **Обновление кэша списка моделей (`/models/refresh`):**
    - **`POST /api/admin/ui/models/refresh`**
      - **Описание**: Принудительно обновляет внутренний кэш списка моделей, запрашивая их у всех активных модулей.
      - **Ответ (JSON)**: `{"status": "success", "message": "Model list cache refreshed.", "models": [...], "error_message": "..."}` (поле `models` будет содержать список моделей или `[]`, `error_message` будет содержать текст ошибки или `null`)

## Структура Проекта

```
.
├── api/
│   ├── admin/                # JSON API эндпоинты для UI админ-панели (/api/admin/ui/...)
│   │   ├── __init__.py
│   │   ├── dashboard_api.py
│   │   ├── settings_api.py
│   │   ├── keys_api.py
│   │   ├── models_api.py
│   │   └── proxies_api.py
│   └── airouter/             # OpenAI-совместимые API эндпоинты (/v1/...)
│       └── openai_compatible.py
├── configs/                  # Папка для JSON конфигураций
│   ├── .env.example          # Пример .env файла (может быть в корне)
│   ├── openai_keys.json
│   ├── gemini_keys.json
│   ├── airouter_api_keys.json # Ключи для доступа к самому роутеру
│   ├── proxies.json
│   └── settings.json         # Настройки UI и общие настройки
├── modules/                  # Модули для различных AI сервисов
│   ├── __init__.py
│   ├── base_module.py        # Базовый класс для всех модулей
│   ├── openai_module.py
│   └── gemini_module.py
├── templates/                # HTML шаблоны для админ-панели
│   ├── admin_dashboard.html
│   ├── admin_help.html
│   └── admin_models.html
├── .env                      # Файл переменных окружения (создается пользователем)
├── .gitignore                # Файл для Git, указывающий игнорируемые файлы
├── admin_router.py           # Роуты для веб-страниц админ-панели (/admin/...) и общие функции/модели для API
├── api_key_manager.py        # Логика управления API ключами AI-сервисов
├── airouter_key_manager.py   # Логика управления API ключами AIRouter
├── main.py                   # Основной файл приложения FastAPI
├── proxy_manager.py          # Логика управления прокси-серверами
├── README.md                 # Этот файл
├── registry.py               # Реестр модулей
└── requirements.txt          # Список зависимостей Python
```

## Устранение Неполадок

- **Ошибки 404 при доступе к панели администратора**: Убедитесь, что вы используете правильные URL: `/admin/dashboard`, `/admin/help`, `/admin/models`.
- **Проблемы с аутентификацией в панели или API админки**: Проверьте правильность `ADMIN_USERNAME` и `ADMIN_PASSWORD` в вашем `.env` файле.
- **Модуль не работает / не отображается**:
  - Убедитесь, что для модуля есть соответствующий файл ключей в папке `configs` и он содержит хотя бы один валидный ключ.
  - Проверьте статус модуля в панели администратора – он должен быть "Включен".
- **Прокси не используются**:
  - Проверьте настройку "Использование прокси" в `configs/settings.json` или через панель администратора/API.
  - Убедитесь, что в `configs/proxies.json` есть хотя бы один прокси.
- **Проблемы с API-ключами AIRouter**:
  - Если включено `require_airouter_api_key`, убедитесь, что вы передаете корректный `Authorization: Bearer <ключ>` заголовок.
  - Проверьте наличие и правильность ключей в `configs/airouter_api_keys.json`.
- **Логи**: При возникновении проблем смотрите в консоль, где запущен Uvicorn – там будут выводиться логи приложения, которые могут помочь диагностировать проблему.

---

Приятного использования!
