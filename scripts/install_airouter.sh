#!/bin/bash

# Скрипт для установки и настройки автозапуска AIRouter на Ubuntu 22.04

# --- Конфигурация ---
APP_NAME="AIRouter"
APP_DIR_NAME="AIRouter" # Имя директории, куда будет скопировано приложение
INSTALL_BASE_DIR="/opt"
INSTALL_DIR="${INSTALL_BASE_DIR}/${APP_DIR_NAME}"
PYTHON_VERSION="3.12"
SERVICE_NAME="airouter"
# Определяем директорию, из которой запущен скрипт
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Предполагаем, что проект AIRouter находится на один уровень выше директории scripts
PROJECT_SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# --- Функции ---

# Функция для вывода сообщений
log_info() {
    echo "[INFO] $1"
}

log_error() {
    echo "[ERROR] $1" >&2
}

# Проверка прав суперпользователя
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        log_error "Этот скрипт должен быть запущен с правами суперпользователя (root или через sudo)."
        exit 1
    fi
    log_info "Права суперпользователя подтверждены."
}

# Функция для удаления предыдущей установки
uninstall_previous_version() {
    log_info "Проверка наличия предыдущей установки $APP_NAME..."

    # Проверка и остановка службы
    if systemctl is-active --quiet "$SERVICE_NAME.service"; then
        log_info "Остановка службы $SERVICE_NAME..."
        systemctl stop "$SERVICE_NAME.service"
        if [ $? -ne 0 ]; then
            log_warning "Не удалось остановить службу $SERVICE_NAME. Продолжаем..."
        else
            log_info "Служба $SERVICE_NAME успешно остановлена."
        fi
    fi

    # Проверка и отключение службы
    if systemctl is-enabled --quiet "$SERVICE_NAME.service"; then
        log_info "Отключение службы $SERVICE_NAME из автозапуска..."
        systemctl disable "$SERVICE_NAME.service"
        if [ $? -ne 0 ]; then
            log_warning "Не удалось отключить службу $SERVICE_NAME. Продолжаем..."
        else
            log_info "Служба $SERVICE_NAME успешно отключена."
        fi
    fi

    # Удаление файла службы
    SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME.service"
    if [ -f "$SERVICE_FILE_PATH" ]; then
        log_info "Удаление файла службы $SERVICE_FILE_PATH..."
        rm -f "$SERVICE_FILE_PATH"
        if [ $? -ne 0 ]; then
            log_warning "Не удалось удалить файл службы $SERVICE_FILE_PATH. Продолжаем..."
        else
            log_info "Файл службы $SERVICE_FILE_PATH успешно удален."
            log_info "Перезагрузка конфигурации systemd после удаления службы..."
            systemctl daemon-reload
        fi
    fi

    # Удаление директории установки
    if [ -d "$INSTALL_DIR" ]; then
        log_info "Удаление предыдущей директории установки $INSTALL_DIR..."
        rm -rf "$INSTALL_DIR"
        if [ $? -ne 0 ]; then
            log_error "Не удалось удалить директорию $INSTALL_DIR. Проверьте права и попробуйте снова."
            # Решаем, стоит ли прерывать скрипт, если не удалось удалить директорию
            # exit 1 
        else
            log_info "Директория $INSTALL_DIR успешно удалена."
        fi
    else
        log_info "Предыдущая директория установки $INSTALL_DIR не найдена."
    fi
}

# Функция для вывода предупреждений (новая)
log_warning() {
    echo "[WARNING] $1" >&2
}


# Создание директории установки
create_install_dir() {
    if [ -d "$INSTALL_DIR" ]; then
        log_info "Директория установки $INSTALL_DIR уже существует. Содержимое будет перезаписано."
        # Можно добавить запрос на подтверждение перезаписи, если нужно
        # read -p "Директория $INSTALL_DIR уже существует. Перезаписать? (y/N): " confirm
        # if [[ "$confirm" != [yY] && "$confirm" != [дД] ]]; then
        #     log_info "Установка отменена пользователем."
        #     exit 0
        # fi
        rm -rf "${INSTALL_DIR:?}"/* # Очищаем содержимое, если директория существует
    else
        log_info "Создание директории установки: $INSTALL_DIR"
        mkdir -p "$INSTALL_DIR"
        if [ $? -ne 0 ]; then
            log_error "Не удалось создать директорию $INSTALL_DIR."
            exit 1
        fi
    fi
}

# Копирование файлов приложения
copy_app_files() {
    log_info "Копирование файлов приложения из $PROJECT_SOURCE_DIR в $INSTALL_DIR..."
    # Копируем все, кроме самой папки scripts, чтобы избежать рекурсии или ненужных файлов
    # Используем rsync для лучшего контроля и возможности исключений
    rsync -av --exclude 'scripts/' --exclude '.git/' --exclude '.idea/' --exclude '__pycache__/' "$PROJECT_SOURCE_DIR/" "$INSTALL_DIR/"
    if [ $? -ne 0 ]; then
        log_error "Не удалось скопировать файлы приложения."
        exit 1
    fi
    log_info "Файлы приложения успешно скопированы."
}

# Установка Python и pip
install_python() {
    log_info "Проверка и установка Python $PYTHON_VERSION..."
    if command -v python$PYTHON_VERSION &> /dev/null; then
        log_info "Python $PYTHON_VERSION уже установлен."
    else
        log_info "Установка Python $PYTHON_VERSION..."
        apt-get update -y
        # PPA для свежих версий Python
        log_info "Добавление PPA deadsnakes для Python..."
        apt-get install -y software-properties-common
        add-apt-repository ppa:deadsnakes/ppa -y
        apt-get update -y
        apt-get install -y python$PYTHON_VERSION python$PYTHON_VERSION-venv python3-pip
        if [ $? -ne 0 ]; then
            log_error "Не удалось установить Python $PYTHON_VERSION."
            exit 1
        fi
        log_info "Python $PYTHON_VERSION успешно установлен."
    fi

    # Убедимся, что pip обновлен
    log_info "Обновление pip..."
    python$PYTHON_VERSION -m pip install --upgrade pip
}

# Создание виртуального окружения и установка зависимостей
setup_venv_and_dependencies() {
    log_info "Создание виртуального окружения в $INSTALL_DIR/venv..."
    python$PYTHON_VERSION -m venv "$INSTALL_DIR/venv"
    if [ $? -ne 0 ]; then
        log_error "Не удалось создать виртуальное окружение."
        exit 1
    fi

    log_info "Активация виртуального окружения и установка зависимостей из requirements.txt..."
    # shellcheck source=/dev/null
    source "$INSTALL_DIR/venv/bin/activate"
    if [ -f "$INSTALL_DIR/requirements.txt" ]; then
        pip install -r "$INSTALL_DIR/requirements.txt"
        if [ $? -ne 0 ]; then
            log_error "Не удалось установить зависимости из requirements.txt."
            deactivate
            exit 1
        fi
        log_info "Зависимости успешно установлены."
    else
        log_info "Файл requirements.txt не найден в $INSTALL_DIR. Пропускаем установку зависимостей."
    fi
    deactivate
}

# Запрос пользователя для службы
prompt_for_service_user() {
    DEFAULT_USER="airouter" # Пользователь по умолчанию, если не указан другой
    read -r -p "От имени какого пользователя Linux должен запускаться сервис $APP_NAME (например, www-data, nobody(не рекомендуется, могут быть проблемы с конфигами), или ваш обычный пользователь)? [${DEFAULT_USER}]: " SERVICE_USER
    SERVICE_USER=${SERVICE_USER:-$DEFAULT_USER} # Если ввод пустой, используем значение по умолчанию

    if ! id "$SERVICE_USER" &>/dev/null; then
        log_info "Пользователь '$SERVICE_USER' не найден. Попытка создать системного пользователя..."
        # Создаем системного пользователя без домашней директории и без возможности входа
        useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
        if [ $? -ne 0 ]; then
            log_error "Не удалось создать пользователя '$SERVICE_USER'. Пожалуйста, создайте его вручную или выберите существующего."
            exit 1
        else
            log_info "Системный пользователь '$SERVICE_USER' успешно создан."
        fi
    else
        log_info "Сервис будет запускаться от имени пользователя: $SERVICE_USER"
    fi
}


# Настройка службы systemd
setup_systemd_service() {
    log_info "Настройка службы systemd ($SERVICE_NAME.service)..."
    SERVICE_FILE_PATH="/etc/systemd/system/$SERVICE_NAME.service"

    # Команда для запуска приложения.
    # Используем абсолютный путь к python из venv.
    # Добавляем --host 0.0.0.0, чтобы приложение было доступно извне.
    EXEC_START="$INSTALL_DIR/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --reload"

    cat > "$SERVICE_FILE_PATH" << EOF
[Unit]
Description=$APP_NAME Service
After=network.target

[Service]
User=$SERVICE_USER
Group=$(id -gn "$SERVICE_USER")
WorkingDirectory=$INSTALL_DIR
ExecStart=$EXEC_START
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF

    if [ $? -ne 0 ]; then
        log_error "Не удалось создать файл службы systemd $SERVICE_FILE_PATH."
        exit 1
    fi

    log_info "Файл службы $SERVICE_FILE_PATH успешно создан."
    log_info "Перезагрузка конфигурации systemd..."
    systemctl daemon-reload
    log_info "Включение службы $SERVICE_NAME для автозапуска..."
    systemctl enable "$SERVICE_NAME.service"
    log_info "Запуск службы $SERVICE_NAME..."
    systemctl start "$SERVICE_NAME.service"

    if systemctl is-active --quiet "$SERVICE_NAME.service"; then
        log_info "Служба $SERVICE_NAME успешно запущена и активна."
    else
        log_error "Служба $SERVICE_NAME не смогла запуститься. Проверьте логи:"
        log_error "sudo journalctl -u $SERVICE_NAME -n 50 --no-pager"
        log_error "sudo systemctl status $SERVICE_NAME"
        exit 1
    fi
}

# --- Основная часть скрипта ---
main() {
    log_info "Запуск установки $APP_NAME..."

    check_root
    uninstall_previous_version # <--- Вызов новой функции
    create_install_dir
    copy_app_files
    install_python
    setup_venv_and_dependencies
    prompt_for_service_user

    # Изменение владельца директории установки на пользователя службы
    log_info "Изменение владельца $INSTALL_DIR на $SERVICE_USER..."
    chown -R "$SERVICE_USER":"$(id -gn "$SERVICE_USER")" "$INSTALL_DIR"
    if [ $? -ne 0 ]; then
        log_error "Не удалось изменить владельца $INSTALL_DIR на $SERVICE_USER."
        # Можно добавить выход из скрипта, если это критично
        # exit 1
    else
        log_info "Владелец $INSTALL_DIR успешно изменен на $SERVICE_USER."
    fi

    setup_systemd_service

    log_info ""
    log_info "$APP_NAME успешно установлен и настроен для автозапуска!"
    log_info "Для проверки статуса службы используйте: sudo systemctl status $SERVICE_NAME"
    log_info "Для просмотра логов службы используйте: sudo journalctl -u $SERVICE_NAME"
    log_info "Если вы изменяли файлы приложения в $INSTALL_DIR, перезапустите службу: sudo systemctl restart $SERVICE_NAME"
}

# Запуск основной функции
main

exit 0
