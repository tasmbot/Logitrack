# app/screens/map_view.py
import tkinter as tk
from tkinter import ttk, messagebox
from screens.base_screen import BaseScreen
from db_utils import get_connection
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import time

class MapViewScreen(BaseScreen):
    def create_widgets(self):
        back_btn = tk.Button(self.root, text="← Назад", command=self.app.go_back)
        back_btn.pack(anchor="nw", padx=10, pady=5)

        self.order_id = self.app.current_order_id

        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute("SELECT delivery_id FROM deliveries WHERE order_id = %s", (self.order_id,))
            delivery_row = cur.fetchone()
            if not delivery_row:
                messagebox.showerror("Ошибка", "Доставка не найдена")
                self.app.go_back()
                return
            delivery_id = delivery_row[0]

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
                self.app.go_back()
                return

            store_lat = float(coords[0])
            store_lng = float(coords[1])
            client_lat = float(coords[2])
            client_lng = float(coords[3])

            map_win = tk.Toplevel(self.root)
            map_win.title(f"Карта доставки — Заказ #{self.order_id}")
            map_win.geometry("800x600")

            fig, ax = plt.subplots(figsize=(8, 6))
            canvas = FigureCanvasTkAgg(fig, map_win)
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

            stop_simulation = threading.Event()

            def redraw_map(courier_lat, courier_lng):
                ax.clear()
                if courier_lat is not None and courier_lng is not None:
                    ax.scatter(courier_lng, courier_lat, color='blue', s=150, label='Курьер', marker='o')
                    ax.scatter(client_lng, client_lat, color='red', s=200, label='Адрес доставки', marker='X')
                    ax.plot([courier_lng, client_lng], [courier_lat, client_lat], 'k--', alpha=0.5, label='Маршрут')
                else:
                    ax.scatter(client_lng, client_lat, color='red', s=200, label='Адрес доставки', marker='X')
                
                ax.set_title(f"Заказ #{self.order_id} — отслеживание в реальном времени")
                ax.set_xlabel("Longitude")
                ax.set_ylabel("Latitude")
                ax.legend()
                ax.grid(True)
                ax.set_aspect('equal', adjustable='box')
                canvas.draw()

            current_lat, current_lng = store_lat, store_lng
            self.app.update_courier_position(delivery_id, current_lat, current_lng)
            redraw_map(current_lat, current_lng)

            def simulation_loop():
                nonlocal current_lat, current_lng
                while not stop_simulation.is_set():
                    current_lat += (client_lat - current_lat) * 0.2
                    current_lng += (client_lng - current_lng) * 0.2
                    self.app.update_courier_position(delivery_id, current_lat, current_lng)
                    map_win.after(0, lambda: redraw_map(current_lat, current_lng))
                    time.sleep(10)
                    if abs(current_lat - client_lat) < 0.0001 and abs(current_lng - client_lng) < 0.0001:
                        self.app.update_courier_position(delivery_id, client_lat, client_lng)
                        map_win.after(0, lambda: redraw_map(client_lat, client_lng))
                        map_win.after(1000, lambda: messagebox.showinfo("Инфо", "Курьер достиг адреса доставки"))
                        break

            threading.Thread(target=simulation_loop, daemon=True).start()

            def on_close():
                stop_simulation.set()
                map_win.destroy()

            map_win.protocol("WM_DELETE_WINDOW", on_close)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить карту:\n{e}")
            self.app.go_back()