# app/screens/profile.py
import tkinter as tk
from tkinter import ttk, messagebox
from screens.base_screen import BaseScreen
from db_utils import get_connection
import random

class ProfileScreen(BaseScreen):
    def create_widgets(self):
        back_btn = tk.Button(self.root, text="← Назад", command=self.app.go_back)
        back_btn.pack(anchor="nw", padx=10, pady=5)
        tk.Label(self.root, text="Обо мне", font=("Arial", 14)).pack(pady=10)

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT c.address, c.date_of_birth, c.sex, u.full_name, u.phone
                FROM clients c
                JOIN users u ON c.user_id = u.user_id
                WHERE c.client_id = %s
            """, (self.app.current_client_id,))
            profile = cur.fetchone()
            conn.close()

            if not profile:
                messagebox.showerror("Ошибка", "Профиль не найден")
                self.app.go_back()
                return

            address, dob, sex, full_name, phone = profile

            tk.Label(self.root, text=f"Имя: {full_name}").pack()
            tk.Label(self.root, text=f"Телефон: {phone}").pack()

            tk.Label(self.root, text="Адрес:").pack(pady=(10, 0))
            addr_var = tk.StringVar(value=address or "")
            addr_entry = tk.Entry(self.root, textvariable=addr_var, width=50)
            addr_entry.pack()

            tk.Label(self.root, text="Дата рождения (ГГГГ-ММ-ДД):").pack(pady=(10, 0))
            dob_var = tk.StringVar(value=dob.strftime("%Y-%m-%d") if dob else "")
            dob_entry = tk.Entry(self.root, textvariable=dob_var, width=20)
            dob_entry.pack()

            tk.Label(self.root, text="Пол:").pack(pady=(10, 0))
            sex_var = tk.StringVar(value=sex or "male")
            sex_combo = ttk.Combobox(self.root, textvariable=sex_var, state="readonly", values=["male", "female"])
            sex_combo.pack()

            def save_profile():
                new_address = addr_var.get().strip()
                new_dob = dob_var.get().strip()
                new_sex = sex_var.get()

                if new_dob:
                    try:
                        from datetime import datetime
                        datetime.strptime(new_dob, "%Y-%m-%d")
                    except ValueError:
                        messagebox.showerror("Ошибка", "Неверный формат даты (ожидается ГГГГ-ММ-ДД)")
                        return

                try:
                    conn = get_connection()
                    cur = conn.cursor()

                    cur.execute("""
                        SELECT location_id FROM locations l
                        JOIN location_types lt ON l.location_type_id = lt.location_type_id
                        WHERE l.address = %s AND lt.location_type = 'client'
                    """, (new_address,))

                    loc = cur.fetchone()
                    location_id = None

                    if loc:
                        location_id = loc[0]
                    else:
                        latitude = round(random.uniform(40.0, 60.0), 6)
                        longitude = round(random.uniform(30.0, 50.0), 6)
                        cur.execute("SELECT location_type_id FROM location_types WHERE location_type = 'client'")
                        type_id = cur.fetchone()[0]
                        cur.execute("""
                            INSERT INTO locations (location_type_id, address, latitude, longitude)
                            VALUES (%s, %s, %s, %s)
                            RETURNING location_id
                        """, (type_id, new_address, latitude, longitude))
                        location_id = cur.fetchone()[0]

                    cur.execute("""
                        UPDATE clients
                        SET address = %s, date_of_birth = %s, sex = %s
                        WHERE client_id = %s
                    """, (new_address, new_dob or None, new_sex, self.app.current_client_id))

                    conn.commit()
                    conn.close()
                    messagebox.showinfo("Успех", "Профиль обновлён!")
                    self.app.show_profile()

                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось обновить профиль:\n{e}")

            tk.Button(self.root, text="Сохранить", command=save_profile).pack(pady=20)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить профиль:\n{e}")
            self.app.go_back()