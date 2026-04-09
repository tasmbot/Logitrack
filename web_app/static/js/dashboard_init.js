// static/js/dashboard_init.js
/**
 * Общие утилиты для дашбордов (MVP-версия)
 * Подключается в конце body через {% block scripts %}
 */

// Глобальная функция для обновления статистики (заглушка)
window.updateDashboardStats = function(stats) {
    // Обновляем элементы по ID, если они есть на странице
    Object.keys(stats).forEach(key => {
        const el = document.getElementById(key);
        if (el && stats[key] !== undefined) {
            el.textContent = stats[key];
        }
    });
};

// HTMX: обработчик успешного ответа для обновления части страницы
document.body.addEventListener('htmx:afterSwap', function(event) {
    // Можно добавить логику пост-обработки, если нужно
    console.log('HTMX обновил:', event.detail.target.id);
});

// Заглушка: загрузка данных для таблиц (реализуем на Этапе 3)
window.loadTableData = async function(endpoint, tableId) {
    try {
        const response = await fetch(endpoint);
        const data = await response.json();
        const table = Tabulator.findTable("#" + tableId)[0];
        if (table) table.replaceData(data);
    } catch (e) {
        console.warn('Не удалось загрузить данные для таблицы:', e);
    }
};