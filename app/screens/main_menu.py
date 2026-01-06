# app/screens/main_menu.py
import tkinter as tk
from screens.base_screen import BaseScreen

class MainMenuScreen(BaseScreen):
    def create_widgets(self):
        role_names = {1: "Администратор", 2: "Оператор", 4: "Клиент"}
        role_name = role_names.get(self.app.role_id, "Неизвестная роль")
        tk.Label(self.root, text=f"Добро пожаловать, {role_name}!", font=("Arial", 14)).pack(pady=10)

        if self.app.role_id == 1:
            tk.Button(self.root, text="Заказы", command=self.app.show_orders).pack(pady=5)
            tk.Button(self.root, text="Аналитика", command=self.app.show_analytics).pack(pady=5)
            tk.Button(self.root, text="Журнал действий", command=self.app.show_audit_log).pack(pady=5)
        elif self.app.role_id == 2:
            tk.Button(self.root, text="Заказы", command=self.app.show_orders).pack(pady=5)
            tk.Button(self.root, text="Аналитика", command=self.app.show_analytics_charts).pack(pady=5)
            tk.Button(self.root, text="Журнал действий", command=self.app.show_audit_log).pack(pady=5)
        elif self.app.role_id == 4:
            if self.app.current_client_id:
                tk.Button(self.root, text="Мои заказы", command=self.app.show_client_orders).pack(pady=5)
                tk.Button(self.root, text="Создать заказ", command=self.app.create_order).pack(pady=5)
                tk.Button(self.root, text="Уведомления", command=self.app.show_notifications).pack(pady=5)
                tk.Button(self.root, text="Обо мне", command=self.app.show_profile).pack(pady=5)
            else:
                tk.messagebox.showerror("Ошибка", "Клиент не найден")
                self.app.show_login()
                return
        tk.Button(self.root, text="Выйти", command=self.app.show_login).pack(pady=20)