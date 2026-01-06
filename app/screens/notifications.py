# app/screens/notifications.py
import tkinter as tk
from tkinter import ttk, messagebox
from screens.base_screen import BaseScreen
from db_utils import get_connection

class NotificationsScreen(BaseScreen):
    def create_widgets(self):
        back_btn = tk.Button(self.root, text="← Назад", command=self.app.go_back)
        back_btn.pack(anchor="nw", padx=10, pady=5)

        tk.Label(self.root, text="Уведомления", font=("Arial", 14)).pack(pady=10)

        # === ТАБЛИЦА УВЕДОМЛЕНИЙ ===
        columns = ("ID уведомления", "Сообщение", "Статус", "Дата", "Прочитано", "Заказ")
        self.tree = ttk.Treeview(self.root, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=120)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Загружаем данные
        self.load_notifications()

        # === КНОПКА "ОТМЕТИТЬ КАК ПРОЧИТАННОЕ" ===
        tk.Button(self.root, text="Отметить как прочитанное", command=self.mark_as_read).pack(pady=5)

    def load_notifications(self):
        """Загружает уведомления из БД и заполняет таблицу"""
        for item in self.tree.get_children():
            self.tree.delete(item)

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT
                    n.notification_id,
                    n.message,
                    s.status_name,
                    n.created_at,
                    n.is_read,
                    o.order_id
                FROM notifications n
                JOIN orders o ON n.order_id = o.order_id
                JOIN statuses s ON s.status_id = n.status_id
                WHERE n.client_id = %s
                ORDER BY n.created_at DESC
            """, (self.app.current_client_id,))
            rows = cur.fetchall()
            conn.close()

            for nid, msg, status, created_at, is_read, order_id in rows:
                read_status = "Да" if is_read else "Нет"
                self.tree.insert("", "end", values=(nid, msg, status, created_at.strftime("%Y-%m-%d %H:%M"), read_status, order_id))

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить уведомления:\n{e}")

    def mark_as_read(self):
        """Отмечает выбранное уведомление как прочитанное в БД и обновляет таблицу"""
        selected = self.tree.focus()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите уведомление")
            return

        values = self.tree.item(selected, "values")
        notification_id = values[0]  # <<< ID уведомления из первой колонки

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                UPDATE notifications
                SET is_read = TRUE
                WHERE notification_id = %s AND client_id = %s
            """, (notification_id, self.app.current_client_id))
            conn.commit()
            conn.close()

            if cur.rowcount == 0:
                messagebox.showwarning("Предупреждение", "Уведомление не найдено или уже принадлежит другому клиенту.")
                return

            # <<< ОБНОВЛЯЕМ ТОЛЬКО ЭТУ СТРОКУ В ТАБЛИЦЕ >>>
            # Берём старые значения и меняем "Прочитано" на "Да"
            new_values = list(values)
            new_values[4] = "Да"  # "Прочитано"
            self.tree.item(selected, values=tuple(new_values))

            messagebox.showinfo("Успешно", "Уведомление отмечено как прочитанное")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось обновить уведомление:\n{e}")