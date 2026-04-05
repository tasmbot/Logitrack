# app/screens/audit_log.py
import tkinter as tk
from tkinter import ttk, messagebox
from screens.base_screen import BaseScreen
from db_utils import get_connection

class AuditLogScreen(BaseScreen):
    def create_widgets(self):
        back_btn = tk.Button(self.root, text="← Назад", command=self.app.go_back)
        back_btn.pack(anchor="nw", padx=10, pady=5)
        tk.Label(self.root, text="Журнал действий пользователей", font=("Arial", 14)).pack(pady=10)

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    a.changed_at,
                    u.full_name AS user_name,
                    a.table_name,
                    a.record_id,
                    a.action,
                    a.new_values->>'status_name' AS new_status,
                    a.old_values->>'status_name' AS old_status
                FROM audit_log a
                LEFT JOIN users u ON a.user_id = u.user_id
                ORDER BY a.changed_at DESC
                LIMIT 100;
            """)
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить журнал:\n{e}")
            return

        columns = ("Время", "Пользователь", "Таблица", "ID записи", "Действие", "Новый статус", "Старый статус")
        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=15)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for row in rows:
            tree.insert("", "end", values=row)