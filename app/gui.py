import tkinter as tk
from tkinter import ttk, messagebox
import psycopg2
from psycopg2 import sql
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import time
import pandas as pd
import contextily as ctx

from app.config import DB_CONFIG
from app.db_utils import get_connection, set_user_id_in_session 

class LogisticsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Logistics System")
        self.root.geometry("1000x600")
        self.current_user_id = None
        self.current_client_id = None
        self.role_id = None
        self.history = []  # Стек экранов
        self.setup_login()

    def setup_login(self):
        self.clear_window()
        self.history = []  # Сброс истории при входе
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
            messagebox.showerror("Ошибка", "Заполните все поля")
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
                self.current_user_id = user[0]
                self.role_id = user[1]
                self.current_client_id = user[2]

                # <<< УСТАНОВКА user_id ДЛЯ АУДИТА >>>
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SET myapp.user_id = %s;", (self.current_user_id,))
                conn.close()

                self.show_main_screen()
            else:
                messagebox.showerror("Ошибка", "Неверный логин или пароль")
        except Exception as e:
            messagebox.showerror("Ошибка БД", str(e))

    def show_main_screen(self):
        self.clear_window()
        self.history.append(self.show_main_screen)  # Запоминаем текущий экран

        role_names = {1: "Администратор", 2: "Оператор", 4: "Клиент"}
        role_name = role_names.get(self.role_id, "Неизвестная роль")
        tk.Label(self.root, text=f"Добро пожаловать, {role_name}!", font=("Arial", 14)).pack(pady=10)

        if self.role_id == 1:
            tk.Button(self.root, text="Заказы", command=self.show_orders).pack(pady=5)
            tk.Button(self.root, text="Аналитика", command=self.show_analytics).pack(pady=5)

        elif self.role_id == 2:
            tk.Button(self.root, text="Заказы", command=self.show_orders).pack(pady=5)
        elif self.role_id == 4:
            if self.current_client_id:
                tk.Button(self.root, text="Мои заказы", command=self.show_client_orders).pack(pady=5)
                tk.Button(self.root, text="Создать заказ", command=self.create_order).pack(pady=5)
            else:
                messagebox.showerror("Ошибка", "Клиент не найден")
                self.setup_login()
                return

        tk.Button(self.root, text="Выйти", command=self.setup_login).pack(pady=20)

    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()  # Убираем текущий экран
            prev_screen = self.history[-1]
            prev_screen()       # Показываем предыдущий
        else:
            self.show_main_screen()

    def show_with_back_button(self, content_func):
        """Обёртка для экранов с кнопкой 'Назад'"""
        self.clear_window()
        self.history.append(content_func)

        # Кнопка "Назад" в верхнем левом углу
        back_btn = tk.Button(self.root, text="← Назад", command=self.go_back)
        back_btn.pack(anchor="nw", padx=10, pady=5)

        # Выполняем основной контент
        content_func()

    # === Экраны ===
    def show_orders(self):
        self.show_with_back_button(self._orders_content)

    def show_analytics_charts(self):
        """Отображает аналитические графики для оператора"""
        self.show_with_back_button(self._analytics_charts_content)

    def _analytics_charts_content(self):
        tk.Label(self.root, text="Аналитика", font=("Arial", 14)).pack(pady=10)

        try:
            conn = get_connection()

            # 1. Загрузка курьеров
            df_couriers = pd.read_sql("""
                SELECT 
                    u.full_name AS courier_name,
                    COUNT(d.delivery_id) AS active_deliveries
                FROM couriers c
                JOIN users u ON c.user_id = u.user_id
                LEFT JOIN deliveries d ON c.courier_id = d.courier_id
                LEFT JOIN orders o ON d.order_id = o.order_id
                LEFT JOIN statuses s ON o.status_id = s.status_id
                WHERE s.status_name IN ('created', 'in_transit')
                GROUP BY u.full_name
                ORDER BY active_deliveries DESC
                LIMIT 7;
            """, conn)

            # 2. Динамика заказов
            df_orders = pd.read_sql("""
                SELECT order_date, total_orders
                FROM daily_order_stats
                ORDER BY order_date;
            """, conn)

            # 3. Топ клиентов
            df_clients = pd.read_sql("""
                SELECT 
                    u.full_name AS client_name,
                    COUNT(o.order_id) AS total_orders
                FROM clients cl
                JOIN users u ON cl.user_id = u.user_id
                JOIN orders o ON cl.client_id = o.client_id
                GROUP BY u.full_name
                ORDER BY total_orders DESC
                LIMIT 10;
            """, conn)

            conn.close()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить аналитику:\n{e}")
            return

        # Создаём прокручиваемый фрейм для горизонтального размещения
        canvas_frame = tk.Frame(self.root)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        canvas = tk.Canvas(canvas_frame, height=350)
        scrollbar = ttk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(xscrollcommand=scrollbar.set)

        # === Горизонтальное размещение графиков ===
        chart_frame = tk.Frame(scrollable_frame)
        chart_frame.pack()

        # Функция для добавления графика
        def add_chart(fig):
            chart_canvas = FigureCanvasTkAgg(fig, chart_frame)
            chart_canvas.get_tk_widget().pack(side=tk.LEFT, padx=10, pady=10)

        # График 1: Загрузка курьеров
        if not df_couriers.empty:
            fig1, ax1 = plt.subplots(figsize=(5, 3))  # уменьшенный размер
            ax1.barh(df_couriers['courier_name'], df_couriers['active_deliveries'], color='skyblue')
            ax1.set_xlabel("Активные заказы")
            ax1.set_ylabel("Курьер")
            ax1.set_title("Загрузка транспорта")
            fig1.tight_layout()
            add_chart(fig1)

        # График 2: Динамика заказов
        if not df_orders.empty:
            fig2, ax2 = plt.subplots(figsize=(5, 3))
            ax2.plot(pd.to_datetime(df_orders['order_date'], format='%d-%m'), df_orders['total_orders'], marker='o', color='green')
            ax2.set_xlabel("Дата")
            ax2.set_ylabel("Заказы")
            ax2.set_title("Динамика заказов")
            ax2.grid(True)
            fig2.tight_layout()
            add_chart(fig2)

        # График 3: Топ клиентов
        if not df_clients.empty:
            fig3, ax3 = plt.subplots(figsize=(5, 3))
            ax3.bar(df_clients['client_name'], df_clients['total_orders'], color='salmon')
            ax3.set_xlabel("Клиент")
            ax3.set_ylabel("Заказы")
            ax3.set_title("Топ-10 клиентов")
            ax3.tick_params(axis='x', rotation=45)
            fig3.tight_layout()
            add_chart(fig3)

        # Упаковка с прокруткой по горизонтали
        canvas.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="bottom", fill="x")

    def _orders_content(self):
        tk.Label(self.root, text="Все заказы", font=("Arial", 14)).pack(pady=10)
        self._show_orders_common("""SELECT  
                    order_id
                    ,client_name
                    ,client_phone
                    ,delivery_location
                    ,latitude
                    ,longitude
                    ,item_name
                    ,ordered_quantity
                    ,total_price
                    ,status_name
                    ,created_at FROM order_summary ORDER BY created_at DESC LIMIT 100""")

    def show_client_orders(self):
        self.show_with_back_button(self._client_orders_content)

    """def _client_orders_content(self):
        if not self.current_client_id:
            self.go_back()
            return
        tk.Label(self.root, text="Мои заказы", font=("Arial", 14)).pack(pady=10)
        query = "SELECT * FROM get_client_orders(%s)"
        self._show_orders_common(query, (self.current_client_id,))"""
    
    def _client_orders_content(self):
        if not self.current_client_id:
            self.go_back()
            return

        tk.Label(self.root, text="Мои заказы", font=("Arial", 14)).pack(pady=10)

        # Загружаем данные
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM get_client_orders(%s)", (self.current_client_id,))
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить заказы:\n{e}")
            return

        # Таблица
        columns = ("order_id", "delivery_location", "item_name", "ordered_quantity", "total_price", "status_name")
        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=10)
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
            tree.column(col, width=120)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for row in rows:
            tree.insert("", "end", values=row)

        # Кнопка "Карта доставки"
        def open_map():
            selected = tree.focus()
            if not selected:
                messagebox.showwarning("Внимание", "Выберите заказ")
                return
            order_id = tree.item(selected, "values")[0]
            self.show_delivery_map(order_id)

        btn_frame = tk.Frame(self.root)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text="Карта доставки", command=open_map, bg="#4CAF50", fg="white").pack()

    def _mark_order_as_delivered(self, order_id):
        """Меняет статус заказа на 'delivered'"""
        try:
            conn = get_connection()
            cur = conn.cursor()
            # Получаем status_id для 'delivered'
            cur.execute("SELECT status_id FROM statuses WHERE status_name = 'delivered'")
            status_id = cur.fetchone()[0]
            # Обновляем заказ
            cur.execute("UPDATE orders SET status_id = %s WHERE order_id = %s", (status_id, order_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Ошибка обновления статуса: {e}")

    def show_delivery_map(self, order_id):
        """Отображает карту с автоматическим обновлением каждые 10 секунд"""
        try:
            conn = get_connection()
            cur = conn.cursor()

            # Получаем delivery_id
            cur.execute("SELECT delivery_id FROM deliveries WHERE order_id = %s", (order_id,))
            delivery_row = cur.fetchone()
            if not delivery_row:
                messagebox.showerror("Ошибка", "Доставка не найдена")
                return
            delivery_id = delivery_row[0]

            # Получаем координаты магазина и клиента
            cur.execute("""
                SELECT
                    store_loc.latitude AS store_lat,
                    store_loc.longitude AS store_lng,
                    client_loc.latitude AS client_lat,
                    client_loc.longitude AS client_lng
                FROM deliveries d
                JOIN routes r ON d.route_id = r.route_id
                JOIN route_points rp_store ON r.route_id = rp_store.route_id AND rp_store.sequence_num = 1
                JOIN locations store_loc ON rp_store.location_id = store_loc.location_id
                JOIN locations client_loc ON d.location_id = client_loc.location_id
                WHERE d.order_id = %s;
            """, (order_id,))
            coords = cur.fetchone()
            conn.close()

            if not coords:
                messagebox.showerror("Ошибка", "Не найдены координаты маршрута")
                return

            store_lat = float(coords[0])
            store_lng = float(coords[1])
            client_lat = float(coords[2])
            client_lng = float(coords[3])

            # Создаём окно
            map_win = tk.Toplevel(self.root)
            map_win.title(f"Карта доставки — Заказ #{order_id}")
            map_win.geometry("800x600")

            # Создаём фигуру matplotlib
            fig, ax = plt.subplots(figsize=(8, 6))
            canvas = FigureCanvasTkAgg(fig, map_win)
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            # Флаг остановки
            stop_simulation = threading.Event()

            # === ФУНКЦИЯ ОБНОВЛЕНИЯ ГРАФИКА ===

            def redraw_map(courier_lat, courier_lng):
                ax.clear()
                if courier_lat is not None and courier_lng is not None:
                    ax.scatter(courier_lng, courier_lat, color='blue', s=150, label='Курьер', marker='o')
                    ax.scatter(client_lng, client_lat, color='red', s=200, label='Адрес доставки', marker='X')
                    ax.plot([courier_lng, client_lng], [courier_lat, client_lat], 'k--', alpha=0.5, label='Маршрут')
                else:
                    ax.scatter(client_lng, client_lat, color='red', s=200, label='Адрес доставки', marker='X')

                # <<< ДОБАВЛЕНО: фоновая карта >>>
                try:
                    # Устанавливаем границы (немного шире, чем точки)
                    margin = 0.01
                    minx = min(courier_lng, client_lng) - margin if courier_lng else client_lng - margin
                    maxx = max(courier_lng, client_lng) + margin if courier_lng else client_lng + margin
                    miny = min(courier_lat, client_lat) - margin if courier_lat else client_lat - margin
                    maxy = max(courier_lat, client_lat) + margin if courier_lat else client_lat + margin

                    ax.set_xlim(minx, maxx)
                    ax.set_ylim(miny, maxy)
                    ctx.add_basemap(ax, crs=4326, source=ctx.providers.OpenStreetMap.Mapnik)
                except Exception as e:
                    print(f"Не удалось загрузить карту: {e}")
                    ax.set_xlim(min(client_lng, courier_lng or client_lng) - 0.02, max(client_lng, courier_lng or client_lng) + 0.02)
                    ax.set_ylim(min(client_lat, courier_lat or client_lat) - 0.02, max(client_lat, courier_lat or client_lat) + 0.02)

                ax.set_title(f"Заказ №{order_id} — отслеживание в реальном времени")
                ax.set_xlabel("Долгота")
                ax.set_ylabel("Широта")
                ax.legend()
                ax.grid(False)  # фоновая карта = сетка не нужна
                canvas.draw()
            """def redraw_map(courier_lat, courier_lng):
                ax.clear()
                if courier_lat is not None and courier_lng is not None:
                    # Маркер курьера
                    ax.scatter(courier_lng, courier_lat, color='blue', s=150, label='Курьер', marker='o')
                    # Маркер доставки — ИСПРАВЛЕНО: (client_lng, client_lat)
                    ax.scatter(client_lng, client_lat, color='red', s=200, label='Адрес доставки', marker='X')
                    # Линия от курьера к клиенту
                    ax.plot([courier_lng, client_lng], [courier_lat, client_lat], 'k--', alpha=0.5, label='Маршрут')
                else:
                    # Только точка доставки
                    ax.scatter(client_lng, client_lat, color='red', s=200, label='Адрес доставки', marker='X')
                
                ax.set_title(f"Заказ #{order_id} — отслеживание в реальном времени")
                ax.set_xlabel("Долгота")
                ax.set_ylabel("Широта")
                ax.legend()
                ax.grid(True)
                ax.set_aspect('equal', adjustable='box')
                canvas.draw()"""

            # === ИНИЦИАЛИЗАЦИЯ ===
            current_lat, current_lng = store_lat, store_lng
            self._update_courier_position(delivery_id, current_lat, current_lng)
            redraw_map(current_lat, current_lng)

            # === ЦИКЛ СИМУЛЯЦИИ ===
            def simulation_loop():
                nonlocal current_lat, current_lng
                while not stop_simulation.is_set():
                    # Обновляем позицию
                    current_lat += (client_lat - current_lat) * 0.4
                    current_lng += (client_lng - current_lng) * 0.4

                    # Сохраняем в БД
                    self._update_courier_position(delivery_id, current_lat, current_lng)

                    # Обновляем график в основном потоке GUI!
                    map_win.after(0, lambda: redraw_map(current_lat, current_lng))

                    time.sleep(10)

                    # Проверка завершения
                    if abs(current_lat - client_lat) < 0.0001 and abs(current_lng - client_lng) < 0.0001:
                        self._update_courier_position(delivery_id, client_lat, client_lng)
                        self._mark_order_as_delivered(order_id)
                        map_win.after(0, lambda: redraw_map(client_lat, client_lng))
                        map_win.after(1000, lambda: messagebox.showinfo("Инфо", "Курьер достиг адреса доставки"))
                        break

            # Запуск в фоне
            threading.Thread(target=simulation_loop, daemon=True).start()

            # Обработка закрытия
            def on_close():
                stop_simulation.set()
                map_win.destroy()

            map_win.protocol("WM_DELETE_WINDOW", on_close)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить карту:\n{e}")

    def _update_courier_position(self, delivery_id, lat, lng):
        """Обновляет или вставляет запись в delivery_coordinates"""
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO delivery_coordinates (delivery_id, latitude, longitude)
                VALUES (%s, %s, %s)
                ON CONFLICT (delivery_id)
                DO UPDATE SET latitude = %s, longitude = %s, updated_at = CURRENT_TIMESTAMP;
            """, (delivery_id, lat, lng, lat, lng))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Ошибка обновления координат: {e}")

    def _draw_map(self, parent, courier_lat, courier_lng, client_lat, client_lng, order_id):
        """Отрисовывает текущее состояние карты"""
        fig, ax = plt.subplots(figsize=(8, 6))

        if courier_lat is not None and courier_lng is not None:
            ax.scatter(courier_lng, courier_lat, color='blue', s=150, label='Курьер', marker='o')
            ax.scatter(client_lng, client_lat, color='red', s=200, label='Адрес доставки', marker='X')
            ax.plot([courier_lng, client_lng], [courier_lat, client_lat], 'k--', alpha=0.5, label='Маршрут')
        else:
            ax.scatter(client_lng, client_lat, color='red', s=200, label='Адрес доставки', marker='X')

        ax.set_title(f"Заказ #{order_id} — отслеживание в реальном времени")
        ax.set_xlabel("Долгота")
        ax.set_ylabel("Широта")
        ax.legend()
        ax.grid(True)
        ax.set_aspect('equal', adjustable='box')

        canvas = FigureCanvasTkAgg(fig, parent)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def show_analytics(self):
        self.show_with_back_button(self._analytics_content)

    def _analytics_content(self):
        tk.Label(self.root, text="Аналитика по дням", font=("Arial", 14)).pack(pady=10)

        columns = ("order_date", "total_orders", "total_revenue", "avg_weight")
        tree = ttk.Treeview(self.root, columns=columns, show="headings")
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
            tree.column(col, width=150)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT * FROM daily_order_stats ORDER BY order_date DESC")
            rows = cur.fetchall()
            conn.close()

            for row in rows:
                tree.insert("", "end", values=row)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить аналитику:\n{e}")

    def create_order(self):
        self.show_with_back_button(self._create_order_content)

    def _create_order_content(self):
        if not self.current_client_id:
            self.go_back()
            return

        # === Этап 0: Подготовка данных ===
        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute("SET myapp.user_id = %s;", (self.current_user_id,))

            # 0.1. Получаем адрес клиента
            cur.execute("SELECT address FROM clients WHERE client_id = %s", (self.current_client_id,))
            client_addr = cur.fetchone()
            if not client_addr or not client_addr[0]:
                messagebox.showerror("Ошибка", "У вас не указан адрес. Обновите профиль.")
                self.go_back()
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
                # Создаём, если нет
                import random
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

            # 0.3. Находим ближайший магазин к точке доставки
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
                self.go_back()
                return

            # Получаем координаты точки доставки
            cur.execute("SELECT latitude, longitude FROM locations WHERE location_id = %s", (delivery_location_id,))
            delivery_coords = cur.fetchone()
            if not delivery_coords:
                messagebox.showerror("Ошибка", "Не найдены координаты доставки")
                self.go_back()
                return

            dlat = float(delivery_coords[0])  # Преобразуем Decimal → float
            dlon = float(delivery_coords[1])

            # Находим ближайший магазин
            nearest_store_id = None
            min_distance = float('inf')

            for store_id, lat, lon in stores:
                if lat is None or lon is None:
                    continue
                # Преобразуем координаты магазина в float
                store_lat = float(lat)
                store_lon = float(lon)
                # Евклидово расстояние в градусах
                dist = ((store_lat - dlat) ** 2 + (store_lon - dlon) ** 2) ** 0.5
                if dist < min_distance:
                    min_distance = dist
                    nearest_store_id = store_id

            if nearest_store_id is None:
                messagebox.showerror("Ошибка", "Нет магазинов с координатами")
                self.go_back()
                return

            store_location_id = nearest_store_id

            # 0.4. Создаём маршрут: магазин → клиент
            # Сначала вставляем без имени 
            cur.execute("INSERT INTO routes (name) VALUES (%s) RETURNING route_id", ("",))
            route_id = cur.fetchone()[0]

            # Затем обновляем имя
            cur.execute("UPDATE routes SET name = %s WHERE route_id = %s", (f"Route_{route_id}_{self.current_client_id}", route_id))

            cur.execute("""
                INSERT INTO route_points (route_id, sequence_num, location_id)
                VALUES (%s, 1, %s), (%s, 2, %s)
            """, (route_id, store_location_id, route_id, delivery_location_id))

            # 0.5. Загружаем товары
            cur.execute("SELECT item_id, item_name FROM items ORDER BY item_name")
            items = cur.fetchall()
            item_dict = {name: id for id, name in items}

            conn.commit()
            conn.close()

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось подготовить данные:\n{e}")
            self.go_back()
            return


        # === Интерфейс ===
        tk.Label(self.root, text="Создать заказ", font=("Arial", 14)).pack(pady=10)

        # Список выбранных товаров
        cart = []  # [(item_id, item_name, quantity), ...]

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

        # Кнопка "Добавить в заказ"
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
                cur.execute("SET myapp.user_id = %s;", (self.current_user_id,))

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
                """, (self.current_client_id, comment or None))
                order_id = cur.fetchone()[0]

                # Добавляем позиции
                for item_id, _, qty in cart:
                    cur.execute("""
                        INSERT INTO order_items (order_id, item_id, ordered_quantity)
                        VALUES (%s, %s, %s)
                    """, (order_id, item_id, qty))


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
                self.show_client_orders()

            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось оформить заказ:\n{e}")

        tk.Button(self.root, text="Оформить заказ", command=place_order, bg="green", fg="white").pack(pady=10)

    def delete_order(self, tree):
        """Удаляет выбранный заказ (только для оператора/админа)"""
        selected = tree.focus()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите заказ для удаления")
            return

        values = tree.item(selected, "values")
        order_id = values[0]

        # Подтверждение
        if not messagebox.askyesno("Подтверждение", f"Удалить заказ №{order_id}? Это действие нельзя отменить."):
            return

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SET myapp.user_id = %s;", (self.current_user_id,))

            # Удаляем заказ (каскадно удалятся order_items, deliveries и т.д.)
            cur.execute("DELETE FROM orders WHERE order_id = %s", (order_id,))

            conn.commit()
            conn.close()

            messagebox.showinfo("Успех", f"Заказ №{order_id} удалён")
            self.show_orders()  # обновить список

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось удалить заказ:\n{e}")

    def _show_orders_common(self, query, params=None):
        # Определяем колонки в зависимости от запроса
        if "get_client_orders" in query:
            columns = ("order_id", "delivery_location", "item_name", "ordered_quantity", "total_price", "status_name", "created_at")
        else:
            columns = ("order_id"
                        ,"client_name"
                        ,"client_phone"
                        ,"delivery_location"
                        ,"latitude"
                        ,"longitude"
                        ,"item_name"
                        ,"ordered_quantity"
                        ,"total_price"
                        ,"status_name"
                        ,"created_at")

        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=15)
        for col in columns:
            tree.heading(col, text=col.replace("_", " ").title())
            tree.column(col, width=120)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        try:
            conn = get_connection()
            cur = conn.cursor()
            if params:
                cur.execute(query, params)
            else:
                cur.execute(query)
            rows = cur.fetchall()
            conn.close()

            for row in rows:
                tree.insert("", "end", values=row)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить заказы:\n{e}")
            return

        # Только админ и оператор могут менять статус
        if self.role_id in (1, 2):
            btn_frame = tk.Frame(self.root)
            btn_frame.pack(pady=10)
            tk.Button(btn_frame, text="Изменить статус", command=lambda: self.change_status(tree)).pack()
            tk.Button(btn_frame, text="Удалить заказ", command=lambda: self.delete_order(tree), bg="red", fg="white").pack(side=tk.LEFT, padx=5)

    def change_status(self, tree):
        selected = tree.focus()
        if not selected:
            messagebox.showwarning("Внимание", "Выберите заказ")
            return

        values = tree.item(selected, "values")
        order_id = values[0]

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SET myapp.user_id = %s;", (self.current_user_id,))
            cur.execute("SELECT status_id, status_name FROM statuses")
            statuses = cur.fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить статусы:\n{e}")
            return

        status_win = tk.Toplevel(self.root)
        status_win.title("Изменить статус")
        status_win.geometry("300x150")
        tk.Label(status_win, text=f"Заказ: {order_id}").pack(pady=5)
        tk.Label(status_win, text="Новый статус:").pack()

        status_var = tk.StringVar()
        status_combo = ttk.Combobox(status_win, textvariable=status_var, state="readonly")
        status_combo['values'] = [name for _, name in statuses]
        status_combo.pack(pady=5)
        status_combo.current(0)

        def save_status():
            selected_name = status_var.get()
            status_id = next(id for id, name in statuses if name == selected_name)
            try:
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SET myapp.user_id = %s;", (self.current_user_id,))
                cur.execute("UPDATE orders SET status_id = %s WHERE order_id = %s", (status_id, order_id))
                conn.commit()
                conn.close()
                messagebox.showinfo("Успех", "Статус обновлён")
                status_win.destroy()
                # Обновляем текущий экран
                if "get_client_orders" in tree.cget("columns")[0]:
                    self.show_client_orders()
                else:
                    self.show_orders()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось обновить статус:\n{e}")

        tk.Button(status_win, text="Сохранить", command=save_status).pack(pady=10)

    def show_notifications(self):
        self.show_with_back_button(self._notifications_content)

    def _notifications_content(self):
        if not self.current_client_id:
            self.go_back()
            return

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
                JOIN statuses s ON s.status_id = n.status_id
                WHERE n.client_id = %s
                ORDER BY n.created_at DESC
            """, (self.current_client_id,))
            rows = cur.fetchall()
            conn.close()
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить уведомления:\n{e}")
            return

        # Таблица уведомлений
        columns = ("Сообщение", "Статус", "Дата", "Прочитано")
        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=10)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=150)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for msg, status, created_at, is_read, order_id in rows:
            read_status = "Да" if is_read else "Нет"
            tree.insert("", "end", values=(msg, status, created_at.strftime("%Y-%m-%d %H:%M"), read_status))

        # Кнопка "Отметить как прочитанное"
        def mark_as_read():
            selected = tree.focus()
            if not selected:
                messagebox.showwarning("Внимание", "Выберите уведомление")
                return
            # Здесь можно добавить SQL-запрос для обновления is_read = TRUE
            messagebox.showinfo("Инфо", "Уведомление отмечено как прочитанное.")

        tk.Button(self.root, text="Отметить как прочитанное", command=mark_as_read).pack(pady=5)

    def show_main_screen(self):
        self.clear_window()
        self.history.append(self.show_main_screen)

        role_names = {1: "Администратор", 2: "Оператор", 4: "Клиент"}
        role_name = role_names.get(self.role_id, "Неизвестная роль")
        tk.Label(self.root, text=f"Добро пожаловать, {role_name}!", font=("Arial", 14)).pack(pady=10)

        if self.role_id == 1:
            tk.Button(self.root, text="Заказы", command=self.show_orders).pack(pady=5)
            tk.Button(self.root, text="Аналитика", command=self.show_analytics).pack(pady=5)
            tk.Button(self.root, text="Журнал действий", command=self.show_audit_log).pack(pady=5)  # <<< НОВАЯ КНОПКА
        elif self.role_id == 2:
            tk.Button(self.root, text="Заказы", command=self.show_orders).pack(pady=5)
            tk.Button(self.root, text="Аналитика", command=self.show_analytics_charts).pack(pady=5)  # <<< НОВАЯ КНОПКА
            tk.Button(self.root, text="Журнал действий", command=self.show_audit_log).pack(pady=5)  # <<< НОВАЯ КНОПКА
        elif self.role_id == 4:
            if self.current_client_id:
                tk.Button(self.root, text="Мои заказы", command=self.show_client_orders).pack(pady=5)
                tk.Button(self.root, text="Создать заказ", command=self.create_order).pack(pady=5)
                tk.Button(self.root, text="Уведомления", command=self.show_notifications).pack(pady=5)  # <<< НОВАЯ КНОПКА
                tk.Button(self.root, text="Обо мне", command=self.show_profile).pack(pady=5)  # НОВАЯ КНОПКА
            else:
                messagebox.showerror("Ошибка", "Клиент не найден")
                self.setup_login()
                return

        tk.Button(self.root, text="Выйти", command=self.setup_login).pack(pady=20)

    def show_audit_log(self):
        self.show_with_back_button(self._audit_log_content)

    def _audit_log_content(self):
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
                    a.new_values->>'status_id' AS new_status,
                    a.old_values->>'status_id' AS old_status
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

        # Таблица
        columns = ("Время", "Пользователь", "Таблица", "ID записи", "Действие", "Новый статус", "Старый статус")
        tree = ttk.Treeview(self.root, columns=columns, show="headings", height=15)
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120)
        tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        for row in rows:
            tree.insert("", "end", values=row)

    # === НОВЫЙ МЕТОД: Профиль клиента ===
    def show_profile(self):
        self.show_with_back_button(self._profile_content)

    def _profile_content(self):
        if not self.current_client_id:
            self.go_back()
            return

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT c.address, c.date_of_birth, c.sex, u.full_name, u.phone
                FROM clients c
                JOIN users u ON c.user_id = u.user_id
                WHERE c.client_id = %s
            """, (self.current_client_id,))
            profile = cur.fetchone()
            conn.close()

            if not profile:
                messagebox.showerror("Ошибка", "Профиль не найден")
                self.go_back()
                return

            address, dob, sex, full_name, phone = profile

            tk.Label(self.root, text="Обо мне", font=("Arial", 14)).pack(pady=10)

            # Имя и телефон (только для чтения)
            tk.Label(self.root, text=f"Имя: {full_name}").pack()
            tk.Label(self.root, text=f"Телефон: {phone}").pack()

            # Адрес
            tk.Label(self.root, text="Адрес:").pack(pady=(10, 0))
            addr_var = tk.StringVar(value=address or "")
            addr_entry = tk.Entry(self.root, textvariable=addr_var, width=50)
            addr_entry.pack()

            # Дата рождения
            tk.Label(self.root, text="Дата рождения (ГГГГ-ММ-ДД):").pack(pady=(10, 0))
            dob_var = tk.StringVar(value=dob.strftime("%Y-%m-%d") if dob else "")
            dob_entry = tk.Entry(self.root, textvariable=dob_var, width=20)
            dob_entry.pack()

            # Пол
            tk.Label(self.root, text="Пол:").pack(pady=(10, 0))
            sex_var = tk.StringVar(value=sex or "male")
            sex_combo = ttk.Combobox(self.root, textvariable=sex_var, state="readonly", values=["male", "female"])
            sex_combo.pack()

            def save_profile():
                new_address = addr_var.get().strip()
                new_dob = dob_var.get().strip()
                new_sex = sex_var.get()

                # Валидация даты
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

                    # 1. Проверяем, существует ли такой адрес в locations (тип 'client')
                    cur.execute("""
                        SELECT location_id FROM locations l
                        JOIN location_types lt ON l.location_type_id = lt.location_type_id
                        WHERE l.address = %s AND lt.location_type = 'delivery_point'
                    """, (new_address,))

                    loc = cur.fetchone()
                    location_id = None

                    if loc:
                        location_id = loc[0]
                    else:
                        # 2. Создаём новую локацию
                        import random
                        latitude = round(random.uniform(40.0, 60.0), 6)
                        longitude = round(random.uniform(30.0, 50.0), 6)

                        # Получаем ID типа 'client'
                        cur.execute("SELECT location_type_id FROM location_types WHERE location_type = 'delivery_point'")
                        type_id = cur.fetchone()[0]

                        cur.execute("""
                            INSERT INTO locations (location_type_id, address, latitude, longitude)
                            VALUES (%s, %s, %s, %s)
                            RETURNING location_id
                        """, (type_id, new_address, latitude, longitude))
                        location_id = cur.fetchone()[0]

                    # 3. Обновляем clients
                    cur.execute("""
                        UPDATE clients
                        SET address = %s, date_of_birth = %s, sex = %s
                        WHERE client_id = %s
                    """, (new_address, new_dob or None, new_sex, self.current_client_id))

                    conn.commit()
                    conn.close()
                    messagebox.showinfo("Успех", "Профиль обновлён!")
                    self._profile_content()  # Обновить экран

                except Exception as e:
                    messagebox.showerror("Ошибка", f"Не удалось обновить профиль:\n{e}")

            tk.Button(self.root, text="Сохранить", command=save_profile).pack(pady=20)
        except Exception:
            pass

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()
