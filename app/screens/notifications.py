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

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    n.message,
                    s.status_name,
                    n.created_at,
                    n.is_read,
                    o.order_id
                FROM notifications n
                JOIN orders o ON n.order_id = o.order_id
                JOIN statuses s ON s.status_id = o.status_id
                WHERE n.client_id = %s
                ORDER BY n.created_at DESC
            """, (self.app.current_client_id,))
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить уведомления:\n{e}")
            return

        columns = ("Сообщение", "Статус", "Дата", "Прочитано")
        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=10)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for msg, status, created_at, is_read, order_id in rows:
            read_status = "Да" if is_read else "Нет"
            tree.insert("", "end", values=(msg, status, created_at.strftime("%Y-%m-%d %H:%M"), read_status))

        def mark_as_read():
            selected = tree.focus()
            if not selected:
                messagebox.showwarning("Внимание", "Выберите уведомление")
                return
            messagebox.showinfo("Инфо", "Уведомление отмечено как прочитанное")

        tk.Button(self.root, text="Отметить как прочитанное", command=mark_as_read).pack(pady=5)