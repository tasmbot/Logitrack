# core/context.py
"""Менеджер состояний пользователей (Flow Manager)."""
from typing import TypedDict, Optional, Literal, List
from telegram.ext import ContextTypes


class UserFlowState(TypedDict, total=False):
    """Типизированное состояние пользователя."""
    # Авторизация
    auth: bool
    
    # Текущий шаг потока
    flow: Optional[Literal[
        "login_email", "login_pass",
        "reg_email", "reg_firstname", "reg_phone", "reg_pass",
        "write_data", "auth_failed"
    ]]
    
    # Временные данные регистрации
    temp_email: str
    temp_first_name: str
    temp_phone: str
    
    # Данные для записи в БД
    target_table: str
    target_cols: List[str]
    
    # Для записи курьерских координат
    selected_delivery_id: Optional[int]
    tracking_active: bool
    courier_id: Optional[int]
    user_role_id: Optional[int]
    


class FlowManager:
    """
    Централизованное управление состоянием пользователя.
    
    Все методы статические для удобства вызова из любого модуля.
    """
    
    _STATE_KEY = "flow_state"
    
    @staticmethod
    def get(context: ContextTypes.DEFAULT_TYPE) -> UserFlowState:
        """Получение состояния пользователя или создание нового."""
        return context.user_data.setdefault(FlowManager._STATE_KEY, UserFlowState(auth=False))
    
    @staticmethod
    def set_flow(context: ContextTypes.DEFAULT_TYPE, flow: Optional[str]):
        """Установка текущего шага потока."""
        state = FlowManager.get(context)
        state["flow"] = flow  # type: ignore
    
    @staticmethod
    def get_flow(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        """Получение текущего шага потока."""
        return FlowManager.get(context).get("flow")
    
    @staticmethod
    def is_authenticated(context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Проверка статуса авторизации."""
        return FlowManager.get(context).get("auth", False)
    
    @staticmethod
    def set_authenticated(context: ContextTypes.DEFAULT_TYPE, value: bool):
        """Установка статуса авторизации."""
        state = FlowManager.get(context)
        state["auth"] = value
    
    @staticmethod
    def set_temp_value(context: ContextTypes.DEFAULT_TYPE, key: str, value: str):
        """Установка временного значения (email, phone и т.д.)."""
        state = FlowManager.get(context)
        state[key] = value  # type: ignore
    
    @staticmethod
    def get_temp_value(context: ContextTypes.DEFAULT_TYPE, key: str) -> Optional[str]:
        """Получение временного значения."""
        return FlowManager.get(context).get(key)  # type: ignore
    
    @staticmethod
    def set_target_table(context: ContextTypes.DEFAULT_TYPE, table: str, cols: List[str]):
        """Установка целевой таблицы и колонок для записи."""
        state = FlowManager.get(context)
        state["target_table"] = table  # type: ignore
        state["target_cols"] = cols  # type: ignore
    
    @staticmethod
    def get_target_table(context: ContextTypes.DEFAULT_TYPE) -> tuple[Optional[str], Optional[List[str]]]:
        """Получение целевой таблицы и колонок."""
        state = FlowManager.get(context)
        return state.get("target_table"), state.get("target_cols")  # type: ignore
    
    @staticmethod
    def clear_temp_data(context: ContextTypes.DEFAULT_TYPE):
        """Очистка временных данных после завершения потока."""
        state = FlowManager.get(context)
        for key in ("temp_email", "temp_first_name", "temp_last_name", "temp_phone", "target_table", "target_cols"):
            state.pop(key, None)  # type: ignore
    
    @staticmethod
    def reset(context: ContextTypes.DEFAULT_TYPE):
        """Полный сброс состояния пользователя."""
        context.user_data[FlowManager._STATE_KEY] = UserFlowState(auth=False)
    
    @staticmethod
    def logout(context: ContextTypes.DEFAULT_TYPE):
        """Выход из аккаунта с сохранением структуры состояния."""
        FlowManager.reset(context)

    @staticmethod
    def set_delivery(context: ContextTypes.DEFAULT_TYPE, delivery_id: int):
        state = FlowManager.get(context)
        state["selected_delivery_id"] = delivery_id  # type: ignore
        state["location_shared"] = False  # type: ignore
        state["tracking_active"] = False  # type: ignore

    @staticmethod
    def get_delivery(context) -> Optional[int]:
        return FlowManager.get(context).get("selected_delivery_id")  # type: ignore

    @staticmethod
    def set_location_shared(context, value: bool):
        state = FlowManager.get(context)
        state["location_shared"] = value  # type: ignore

    @staticmethod
    def is_location_shared(context) -> bool:
        return FlowManager.get(context).get("location_shared", False)  # type: ignore

    @staticmethod
    def set_tracking_active(context, value: bool):
        state = FlowManager.get(context)
        state["tracking_active"] = value  # type: ignore

    @staticmethod
    def is_tracking_active(context) -> bool:
        return FlowManager.get(context).get("tracking_active", False)  # type: ignore
    
    @staticmethod
    def set_courier_data(context: ContextTypes.DEFAULT_TYPE, user_id: int, courier_id: int, role_id: int):
        """Сохранение данных курьера после авторизации."""
        state = FlowManager.get(context)
        state["courier_id"] = courier_id  # type: ignore
        state["user_role_id"] = role_id  # type: ignore

    @staticmethod
    def get_courier_id(context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        return FlowManager.get(context).get("courier_id")  # type: ignore

    @staticmethod
    def is_courier(context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Проверка, что пользователь — курьер (role_id=3)."""
        return FlowManager.get(context).get("user_role_id") == 3

    @staticmethod
    def clear_courier_data(context: ContextTypes.DEFAULT_TYPE):
        """Очистка данных курьера при выходе."""
        state = FlowManager.get(context)
        state.pop("courier_id", None)  # type: ignore
        state.pop("user_role_id", None)  # type: ignore
        
    @staticmethod
    def reset_delivery_state(context):
        """Полный сброс состояния доставки."""
        state = FlowManager.get(context)
        state["selected_delivery_id"] = None  # type: ignore
        state["location_shared"] = False  # type: ignore
        state["tracking_active"] = False  # type: ignore