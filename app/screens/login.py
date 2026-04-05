# app/screens/login.py
import tkinter as tk
from screens.base_screen import BaseScreen
from db_utils import get_connection, set_user_id_in_session

class LoginScreen(BaseScreen):
    def create_widgets(self):
        tk.Label(self.root, text="Авторизация", font=("Arial", 16)).pack(pady=20)
        tk.Label(self.root, text="Email:").pack()
        self.email_entry = tk.Entry(self.root, width=30)
        self.email_entry.pack()
        tk.Label(self.root, text="Пароль:").pack()
        self.password_entry = tk.Entry(self.root, show="*", width=30)
        self.password_entry.pack()
        tk.Button(self.root, text="Войти", command=self.login).pack(pady=10)

    def login(self):
        email = self.email_entry.get()
        password = self.password_entry.get()
        if not email or not password:
            tk.messagebox.showerror("Ошибка", "Заполните все поля")
            return
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT u.user_id, u.role_id, c.client_id
                FROM users u
                LEFT JOIN clients c ON u.user_id = c.user_id
                WHERE u.email = %s AND u.password_hash = %s
            """, (email, password))
            user = cur.fetchone()
            conn.close()
            if user:
                self.app.current_user_id = user[0]
                self.app.role_id = user[1]
                self.app.current_client_id = user[2]
                conn = get_connection()
                set_user_id_in_session(conn, self.app.current_user_id)
                conn.close()
                self.app.show_main_menu()
            else:
                tk.messagebox.showerror("Ошибка", "Неверный логин или пароль")
        except Exception as e:
            tk.messagebox.showerror("Ошибка БД", str(e))