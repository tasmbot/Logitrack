# app/screens/analytics.py
import tkinter as tk
from tkinter import ttk, messagebox
from screens.base_screen import BaseScreen
from db_utils import get_connection
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

class AnalyticsChartsScreen(BaseScreen):
    def create_widgets(self):
        back_btn = tk.Button(self.root, text="← Назад", command=self.app.go_back)
        back_btn.pack(anchor="nw", padx=10, pady=5)
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
                ORDER BY active_deliveries DESC;
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

        # Прокручиваемый фрейм для горизонтального размещения
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

        # Горизонтальное размещение графиков
        chart_frame = tk.Frame(scrollable_frame)
        chart_frame.pack()

        def add_chart(fig):
            chart_canvas = FigureCanvasTkAgg(fig, chart_frame)
            chart_canvas.get_tk_widget().pack(side=tk.LEFT, padx=10, pady=10)

        # График 1: Загрузка курьеров
        if not df_couriers.empty:
            fig1, ax1 = plt.subplots(figsize=(5, 3))
            ax1.barh(df_couriers['courier_name'], df_couriers['active_deliveries'], color='skyblue')
            ax1.set_xlabel("Активные заказы")
            ax1.set_ylabel("Курьер")
            ax1.set_title("Загрузка транспорта")
            fig1.tight_layout()
            add_chart(fig1)

        # График 2: Динамика заказов
        if not df_orders.empty:
            fig2, ax2 = plt.subplots(figsize=(5, 3))
            ax2.plot(df_orders['order_date'], df_orders['total_orders'], marker='o', color='green')
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

        canvas.pack(side="top", fill="both", expand=True)
        scrollbar.pack(side="bottom", fill="x")