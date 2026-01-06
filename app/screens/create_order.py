# app/screens/create_order.py
import tkinter as tk
from tkinter import ttk, messagebox
from screens.base_screen import BaseScreen
from db_utils import get_connection
import random

class CreateOrderScreen(BaseScreen):
    def create_widgets(self):
        back_btn = tk.Button(self.root, text="← Назад", command=self.app.go_back)
        back_btn.pack(anchor="nw", padx=10, pady=5)
        tk.Label(self.root, text="Создать заказ", font=("Arial", 14)).pack(pady=10)

        # Загрузка товаров
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT item_id, item_name FROM items ORDER BY item_name")
            items = cur.fetchall()
            item_dict = {name: id for id, name in items}
            conn.close()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить товары:\n{e}")
            self.app.go_back()
            return

        # Список выбранных товаров
        cart = []

        def update_cart_display():
            cart_text.config(state="normal")
            cart_text.delete(1.0, tk.END)
            if cart:
                for item_id, name, qty in cart:
                    cart_text.insert(tk.END, f"{name} — {qty} шт.\n")
            else:
                cart_text.insert(tk.END, "Корзина пуста")
            cart_text.config(state="disabled")

        # Выбор товара
        tk.Label(self.root, text="Товар:").pack(pady=5)
        item_var = tk.StringVar()
        item_combo = ttk.Combobox(self.root, textvariable=item_var, state="readonly")
        item_combo['values'] = [name for _, name in items]
        item_combo.pack(pady=5)
        item_combo.current(0)

        tk.Label(self.root, text="Количество:").pack(pady=5)
        qty_entry = tk.Entry(self.root)
        qty_entry.pack(pady=5)
        qty_entry.insert(0, "1")

        def add_to_cart():
            item_name = item_var.get()
            qty = qty_entry.get()
            if not qty.isdigit() or int(qty) <= 0:
                messagebox.showerror("Ошибка", "Количество должно быть положительным числом")
                return
            item_id = item_dict[item_name]
            cart.append((item_id, item_name, int(qty)))
            update_cart_display()
            qty_entry.delete(0, tk.END)
            qty_entry.insert(0, "1")

        tk.Button(self.root, text="Добавить в заказ", command=add_to_cart).pack(pady=5)

        # Отображение корзины
        cart_text = tk.Text(self.root, height=6, width=50, state="disabled")
        cart_text.pack(pady=10)
        update_cart_display()

        # Комментарий
        tk.Label(self.root, text="Комментарий:").pack(pady=5)
        comment_entry = tk.Entry(self.root, width=50)
        comment_entry.pack(pady=5)

        # Кнопка "Оформить заказ"
        def place_order():
            if not cart:
                messagebox.showwarning("Внимание", "Корзина пуста")
                return

            comment = comment_entry.get().strip()

            try:
                conn = get_connection()
                cur = conn.cursor()

                # 0.1. Получаем адрес клиента
                cur.execute("SELECT address FROM clients WHERE client_id = %s", (self.app.current_client_id,))
                client_addr = cur.fetchone()
                if not client_addr or not client_addr[0]:
                    messagebox.showerror("Ошибка", "У вас не указан адрес. Обновите профиль.")
                    self.app.go_back()
                    return
                address = client_addr[0]

                # 0.2. Получаем location_id для доставки (тип 'delivery_point')
                cur.execute("""
                    SELECT location_id FROM locations l
                    JOIN location_types lt ON l.location_type_id = lt.location_type_id
                    WHERE l.address = %s AND lt.location_type = 'delivery_point'
                """, (address,))
                delivery_loc = cur.fetchone()
                if not delivery_loc:
                    lat = round(random.uniform(40.0, 60.0), 6)
                    lng = round(random.uniform(30.0, 50.0), 6)
                    cur.execute("SELECT location_type_id FROM location_types WHERE location_type = 'delivery_point'")
                    type_id = cur.fetchone()[0]
                    cur.execute("""
                        INSERT INTO locations (location_type_id, address, latitude, longitude)
                        VALUES (%s, %s, %s, %s) RETURNING location_id
                    """, (type_id, address, lat, lng))
                    delivery_location_id = cur.fetchone()[0]
                else:
                    delivery_location_id = delivery_loc[0]

                # 0.3. Находим ближайший магазин
                cur.execute("""
                    SELECT 
                        store_loc.location_id,
                        store_loc.latitude,
                        store_loc.longitude
                    FROM locations store_loc
                    JOIN location_types lt ON store_loc.location_type_id = lt.location_type_id
                    WHERE lt.location_type = 'store'
                """)
                stores = cur.fetchall()
                if not stores:
                    messagebox.showerror("Ошибка", "Нет доступных магазинов")
                    self.app.go_back()
                    return

                cur.execute("SELECT latitude, longitude FROM locations WHERE location_id = %s", (delivery_location_id,))
                delivery_coords = cur.fetchone()
                if not delivery_coords:
                    messagebox.showerror("Ошибка", "Не найдены координаты доставки")
                    self.app.go_back()
                    return

                dlat, dlon = float(delivery_coords[0]), float(delivery_coords[1])
                nearest_store_id = None
                min_distance = float('inf')

                for store_id, lat, lon in stores:
                    if lat is None or lon is None:
                        continue
                    dist = ((float(lat) - dlat) ** 2 + (float(lon) - dlon) ** 2) ** 0.5
                    if dist < min_distance:
                        min_distance = dist
                        nearest_store_id = store_id

                if nearest_store_id is None:
                    messagebox.showerror("Ошибка", "Нет магазинов с координатами")
                    self.app.go_back()
                    return

                store_location_id = nearest_store_id

                # 0.4. Создаём маршрут: магазин → клиент
                cur.execute("INSERT INTO routes (name) VALUES (%s) RETURNING route_id", (f"Route for client {self.app.current_client_id}",))
                route_id = cur.fetchone()[0]

                cur.execute("""
                    INSERT INTO route_points (route_id, sequence_num, location_id)
                    VALUES (%s, 1, %s), (%s, 2, %s)
                """, (route_id, store_location_id, route_id, delivery_location_id))

                # Проверка наличия каждого товара в выбранном магазине
                for item_id, _, qty in cart:
                    cur.execute("""
                        SELECT quantity FROM store_stock
                        WHERE location_id = %s AND item_id = %s
                    """, (store_location_id, item_id))
                    stock = cur.fetchone()
                    available = stock[0] if stock else 0
                    if available < qty:
                        messagebox.showerror("Ошибка", f"Недостаточно товара '{item_dict[item_id]}' в магазине. Доступно: {available}")
                        conn.close()
                        return

                # Создаём заказ
                cur.execute("""
                    INSERT INTO orders (client_id, status_id, comments)
                    VALUES (%s, 1, %s) RETURNING order_id
                """, (self.app.current_client_id, comment or None))
                order_id = cur.fetchone()[0]

                # Добавляем позиции
                for item_id, _, qty in cart:
                    cur.execute("""
                        INSERT INTO order_items (order_id, item_id, ordered_quantity)
                        VALUES (%s, %s, %s)
                    """, (order_id, item_id, qty))

                # Списываем товар
                for item_id, _, qty in cart:
                    cur.execute("""
                        UPDATE store_stock
                        SET quantity = quantity - %s, updated_at = CURRENT_TIMESTAMP
                        WHERE location_id = %s AND item_id = %s
                    """, (qty, store_location_id, item_id))

                # Создаём доставку
                cur.execute("SELECT courier_id FROM couriers ORDER BY RANDOM() LIMIT 1")
                courier_id = cur.fetchone()[0]

                cur.execute("""
                    INSERT INTO deliveries (order_id, courier_id, route_id, location_id)
                    VALUES (%s, %s, %s, %s)
                """, (order_id, courier_id, route_id, delivery_location_id))

                conn.commit()
                conn.close()
                messagebox.showinfo("Успех", f"Заказ #{order_id} оформлен!")
                self.app.show_client_orders()

            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось оформить заказ:\n{e}")

        tk.Button(self.root, text="Оформить заказ", command=place_order, bg="green", fg="white").pack(pady=10)