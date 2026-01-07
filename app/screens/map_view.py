# app/screens/map_view.py
import tkinter as tk
from tkinter import ttk, messagebox
from screens.base_screen import BaseScreen
from db_utils import get_connection
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import time
import contextily as ctx

class MapViewScreen:
    def __init__(self, root, app, order_id):
        self.root = root  # Это Toplevel
        self.app = app    # Это LogisticsApp
        self.order_id = order_id
        self.create_widgets()

    def create_widgets(self):
        try:
            conn = get_connection()
            cur = conn.cursor()

            # Получаем delivery_id
            cur.execute("SELECT delivery_id FROM deliveries WHERE order_id = %s", (self.order_id,))
            delivery_row = cur.fetchone()
            if not delivery_row:
                messagebox.showerror("Ошибка", "Доставка не найдена")
                self.root.destroy()
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
            """, (self.order_id,))
            coords = cur.fetchone()
            conn.close()

            if not coords:
                messagebox.showerror("Ошибка", "Не найдены координаты маршрута")
                self.root.destroy()
                return

            store_lat = float(coords[0])
            store_lng = float(coords[1])
            client_lat = float(coords[2])
            client_lng = float(coords[3])

            # === Создаём окно ===
            self.root.title(f"Карта доставки — Заказ #{self.order_id}")
            self.root.geometry("800x600")

            # === Создаём фигуру matplotlib ===
            fig, ax = plt.subplots(figsize=(8, 6))
            canvas = FigureCanvasTkAgg(fig, self.root)
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

                ax.set_title(f"Заказ №{self.order_id} — отслеживание в реальном времени")
                ax.set_xlabel("Долгота")
                ax.set_ylabel("Широта")
                ax.legend()
                ax.grid(False)  # фоновая карта = сетка не нужна
                canvas.draw()

            # === ИНИЦИАЛИЗАЦИЯ ===
            current_lat, current_lng = store_lat, store_lng
            self.app.update_courier_position(delivery_id, current_lat, current_lng)
            redraw_map(current_lat, current_lng)

            # === ЦИКЛ СИМУЛЯЦИИ ===
            def simulation_loop():
                nonlocal current_lat, current_lng
                while not stop_simulation.is_set():
                    # Обновляем позицию
                    current_lat += (client_lat - current_lat) * 0.4
                    current_lng += (client_lng - current_lng) * 0.4

                    # Сохраняем в БД
                    self.app.update_courier_position(delivery_id, current_lat, current_lng)

                    # Обновляем график в основном потоке GUI!
                    self.root.after(0, lambda: redraw_map(current_lat, current_lng))

                    time.sleep(10)

                    # Проверка завершения
                    if abs(current_lat - client_lat) < 0.0001 and abs(current_lng - client_lng) < 0.0001:
                        self.app.update_courier_position(delivery_id, client_lat, client_lng)
                        self.app.mark_order_as_delivered(self.order_id)
                        self.root.after(0, lambda: redraw_map(client_lat, client_lng))
                        self.root.after(1000, lambda: messagebox.showinfo("Инфо", "Курьер достиг адреса доставки"))
                        break

            # Запуск в фоне
            threading.Thread(target=simulation_loop, daemon=True).start()

            # Обработка закрытия
            def on_close():
                stop_simulation.set()
                self.root.destroy()

            self.root.protocol("WM_DELETE_WINDOW", on_close)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить карту:\n{e}")
            self.root.destroy()