# app/screens/client_orders.py
import tkinter as tk
from tkinter import ttk, messagebox
from screens.base_screen import BaseScreen
from db_utils import get_connection

class ClientOrdersScreen(BaseScreen):
    def create_widgets(self):
        back_btn = tk.Button(self.root, text="← Назад", command=self.app.go_back)
        back_btn.pack(anchor="nw", padx=10, pady=5)
        tk.Label(self.root, text="Мои заказы", font=("Arial", 14)).pack(pady=10)

        columns = ("order_id", "delivery_location", "item_name", "ordered_quantity", "total_price", "status_name")
        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=10)
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
            tree.column(col, width=120)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM get_client_orders(%s)", (self.app.current_client_id,))
            rows = cur.fetchall()
            conn.close()

            for row in rows:
                tree.insert("", "end", values=row)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить заказы:\n{e}")
            return

        # Кнопка "Карта доставки"
        def open_map():
            selected = tree.focus()
            if not selected:
                messagebox.showwarning("Внимание", "Выберите заказ")
                return
            order_id = tree.item(selected, "values")[0]
            self.app.show_delivery_map(order_id)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Карта доставки", command=open_map, bg="#4CAF50", fg="white").pack()

        # Двойной клик
        tree.bind("<Double-1>", lambda e: open_map())