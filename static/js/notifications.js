// notifications.js — универсальный модуль для управления уведомлениями в админке

(function () {
    /**
     * Добавить уведомление в указанный контейнер.
     * @param {string|HTMLElement} containerId - id-контейнера (например, 'notification_area' или 'model_notification_area') или HTMLElement.
     * @param {string} message - Текст уведомления (разрешён HTML).
     * @param {string} type - 'success' | 'error'.
     * @param {number} timeout - Время (мс), через сколько скрыть сообщение (0 — не убирать автоматически).
     */
    function showNotification(containerId, message, type = 'success', timeout = 4000) {
        let container = typeof containerId === 'string' ? document.getElementById(containerId) : containerId;
        if (!container) return;

        const notification = document.createElement('div');
        notification.className = `notification ${type}`;
        notification.innerHTML = message;

        notification.style.cursor = 'pointer';
        notification.title = 'Нажмите, чтобы закрыть уведомление';
        notification.addEventListener('click', function () {
            removeNotification(notification);
        });

        container.appendChild(notification);

        if (timeout > 0) {
            setTimeout(() => removeNotification(notification), timeout);
        }
    }

    function removeNotification(notificationNode) {
        if (!notificationNode) return;
        notificationNode.style.opacity = 0;
        setTimeout(() => {
            if (notificationNode.parentNode) {
                notificationNode.parentNode.removeChild(notificationNode);
            }
        }, 300);
    }

    // На случай, если в верстке уже что-то есть (например, серверное уведомление)
    document.addEventListener('DOMContentLoaded', () => {
        const containers = document.querySelectorAll('[id$="_notification_area"]');
        containers.forEach(container => {
            container.querySelectorAll('.notification').forEach(notification => {
                notification.style.cursor = 'pointer';
                notification.title = 'Нажмите, чтобы закрыть уведомление';
                notification.addEventListener('click', function () {
                    removeNotification(notification);
                });
                setTimeout(() => removeNotification(notification), 4000);
            });
        });
    });

    // Экспортируем функцию в глобальный scope
    window.showNotification = showNotification;
    window.removeNotification = removeNotification;
})();
