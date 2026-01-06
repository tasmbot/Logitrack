# app/app_core.py
import tkinter as tk
from db_utils import get_connection, set_user_id_in_session

class LogisticsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Logistics System")
        self.root.geometry("1000x600")
        self.current_user_id = None
        self.current_client_id = None
        self.role_id = None
        self.history = []
        self.show_login()

    def show_login(self):
        from screens.login import LoginScreen
        self.clear_window()
        self.history = []
        LoginScreen(self.root, self)

    def show_main_menu(self):
        from screens.main_menu import MainMenuScreen
        self.clear_window()
        self.history.append(self.show_main_menu)
        MainMenuScreen(self.root, self)

    # --- Экраны для админа/оператора ---
    def show_orders(self):
        from screens.orders import OrdersScreen
        self.clear_window()
        self.history.append(self.show_orders)
        OrdersScreen(self.root, self)

    def show_analytics(self):
        from screens.analytics import AnalyticsScreen  # для админа
        self.clear_window()
        self.history.append(self.show_analytics)
        AnalyticsScreen(self.root, self)

    def show_analytics_charts(self):
        from screens.analytics import AnalyticsChartsScreen  # для оператора
        self.clear_window()
        self.history.append(self.show_analytics_charts)
        AnalyticsChartsScreen(self.root, self)

    def show_audit_log(self):
        from screens.audit_log import AuditLogScreen
        self.clear_window()
        self.history.append(self.show_audit_log)
        AuditLogScreen(self.root, self)

    # --- Экраны для клиента ---
    def show_client_orders(self):
        from screens.client_orders import ClientOrdersScreen
        self.clear_window()
        self.history.append(self.show_client_orders)
        ClientOrdersScreen(self.root, self)

    def create_order(self):
        from screens.create_order import CreateOrderScreen
        self.clear_window()
        self.history.append(self.create_order)
        CreateOrderScreen(self.root, self)

    def show_notifications(self):
        from screens.notifications import NotificationsScreen
        self.clear_window()
        self.history.append(self.show_notifications)
        NotificationsScreen(self.root, self)

    def show_profile(self):
        from screens.profile import ProfileScreen
        self.clear_window()
        self.history.append(self.show_profile)
        ProfileScreen(self.root, self)

    # --- Вспомогательные методы ---
    def go_back(self):
        if len(self.history) > 1:
            self.history.pop()
            self.history[-1]()
        else:
            self.show_main_menu()

    def clear_window(self):
        for widget in self.root.winfo_children():
            widget.destroy()

    # --- Методы для карты ---
    def show_delivery_map(self, order_id):
        from screens.map_view import MapViewScreen
        # Временно передаём order_id через атрибут
        self.current_order_id = order_id
        # Создаём окно карты как отдельный экран
        map_root = tk.Toplevel(self.root)
        map_root.title(f"Карта доставки — Заказ #{order_id}")
        map_root.geometry("800x600")
        MapViewScreen(map_root, self)

    def update_courier_position(self, delivery_id, lat, lng):
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