# app/screens/orders.py
import tkinter as tk
from tkinter import ttk, messagebox
from screens.base_screen import BaseScreen
from db_utils import get_connection

class OrdersScreen(BaseScreen):
    def create_widgets(self):
        back_btn = tk.Button(self.root, text="← Назад", command=self.app.go_back)
        back_btn.pack(anchor="nw", padx=10, pady=5)
        tk.Label(self.root, text="Все заказы", font=("Arial", 14)).pack(pady=10)

        columns = ("order_id", "client/location", "phone/address", "item", "qty", "status")
        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=15)
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
            tree.column(col, width=120)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT order_id, client_name, client_phone, delivery_location, item_name, ordered_quantity, status_name FROM order_summary ORDER BY created_at DESC LIMIT 100")
            rows = cur.fetchall()
            conn.close()

            for row in rows:
                tree.insert("", "end", values=row)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить заказы:\n{e}")
            return

        if self.app.role_id in (1, 2):
            btn_frame = tk.Frame(self.root)
            btn_frame.pack(pady=10)
            tk.Button(btn_frame, text="Изменить статус", command=lambda: self.change_status(tree)).pack(side=tk.LEFT, padx=5)
            tk.Button(btn_frame, text="Удалить заказ", command=lambda: self.delete_order(tree), bg="red", fg="white").pack(side=tk.LEFT, padx=5)

    def change_status(self, tree):
        from tkinter import simpledialog
        selected = tree.focus()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите заказ")
            return

        values = tree.item(selected, "values")
        order_id = values[0]

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT status_id, status_name FROM statuses")
            statuses = cur.fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить статусы:\n{e}")
            return

        status_names = [name for _, name in statuses]
        selected_name = simpledialog.askstring("Статус", "Выберите новый статус:", initialvalue=status_names[0], parent=self.root)
        if selected_name and selected_name in status_names:
            status_id = next(id for id, name in statuses if name == selected_name)
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("UPDATE orders SET status_id = %s WHERE order_id = %s", (status_id, order_id))
                conn.commit()
                conn.close()
                messagebox.showinfo("Успех", "Статус обновлён")
                self.app.show_orders()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось обновить статус:\n{e}")

    def delete_order(self, tree):
        selected = tree.focus()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите заказ для удаления")
            return

        values = tree.item(selected, "values")
        order_id = values[0]

        if not messagebox.askyesno("Подтверждение", f"Удалить заказ №{order_id}? Это действие нельзя отменить."):
            return

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("DELETE FROM orders WHERE order_id = %s", (order_id,))
            conn.commit()
            conn.close()
            messagebox.showinfo("Успех", f"Заказ №{order_id} удалён")
            self.app.show_orders()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить заказ:\n{e}")