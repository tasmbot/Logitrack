# core/context.py
from typing import TypedDict, Optional, Literal, List
from telegram.ext import ContextTypes

class UserFlowState(TypedDict, total=False):
    auth: bool
    flow: Optional[Literal[
        "login_email", "login_pass",
        "reg_email", "reg_firstname", "reg_phone", "reg_pass",
        "write_data", "auth_failed"
    ]]
    temp_email: str
    temp_first_name: str
    temp_last_name: str 
    temp_phone: str
    
    target_table: str
    target_cols: List[str]
    
    # единое состояние для доставки
    selected_delivery_id: Optional[int]
    tracking_active: bool
    location_shared: bool
    courier_id: Optional[int]
    user_role_id: Optional[int]

class FlowManager:
    _STATE_KEY = "flow_state"

    @staticmethod
    def get(context: ContextTypes.DEFAULT_TYPE) -> UserFlowState:
        return context.user_data.setdefault(FlowManager._STATE_KEY, UserFlowState(auth=False))

    @staticmethod
    def set_flow(context: ContextTypes.DEFAULT_TYPE, flow: Optional[str]):
        FlowManager.get(context)["flow"] = flow

    @staticmethod
    def get_flow(context: ContextTypes.DEFAULT_TYPE) -> Optional[str]:
        return FlowManager.get(context).get("flow")

    @staticmethod
    def is_authenticated(context: ContextTypes.DEFAULT_TYPE) -> bool:
        return FlowManager.get(context).get("auth", False)

    @staticmethod
    def set_authenticated(context: ContextTypes.DEFAULT_TYPE, value: bool):
        FlowManager.get(context)["auth"] = value

    @staticmethod
    def set_temp_value(context: ContextTypes.DEFAULT_TYPE, key: str, value: str):
        FlowManager.get(context)[key] = value

    @staticmethod
    def get_temp_value(context: ContextTypes.DEFAULT_TYPE, key: str) -> Optional[str]:
        return FlowManager.get(context).get(key)

    @staticmethod
    def set_target_table(context: ContextTypes.DEFAULT_TYPE, table: str, cols: List[str]):
        state = FlowManager.get(context)
        state["target_table"] = table
        state["target_cols"] = cols

    @staticmethod
    def get_target_table(context: ContextTypes.DEFAULT_TYPE) -> tuple[Optional[str], Optional[List[str]]]:
        state = FlowManager.get(context)
        return state.get("target_table"), state.get("target_cols")

    @staticmethod
    def clear_temp_data(context: ContextTypes.DEFAULT_TYPE):
        state = FlowManager.get(context)
        for key in ("temp_email", "temp_first_name", "temp_last_name", "temp_phone", "target_table", "target_cols"):
            state.pop(key, None)

    @staticmethod
    def reset(context: ContextTypes.DEFAULT_TYPE):
        context.user_data[FlowManager._STATE_KEY] = UserFlowState(auth=False)

    @staticmethod
    def logout(context: ContextTypes.DEFAULT_TYPE):
        FlowManager.reset(context)

    # --- Методы для доставки ---

    @staticmethod
    def set_delivery(context: ContextTypes.DEFAULT_TYPE, delivery_id: int):
        """Сохраняет ID доставки и сбрасывает активность трекинга."""
        state = FlowManager.get(context)
        state["selected_delivery_id"] = delivery_id  # type: ignore
        state["tracking_active"] = False            # type: ignore

    @staticmethod
    def get_delivery(context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        return FlowManager.get(context).get("selected_delivery_id")  # type: ignore

    @staticmethod
    def set_tracking_active(context: ContextTypes.DEFAULT_TYPE, value: bool):
        state = FlowManager.get(context)
        state["tracking_active"] = value  # type: ignore

    @staticmethod
    def is_tracking_active(context: ContextTypes.DEFAULT_TYPE) -> bool:
        return FlowManager.get(context).get("tracking_active", False)  # type: ignore

    @staticmethod
    def set_location_shared(context: ContextTypes.DEFAULT_TYPE, value: bool):
        state = FlowManager.get(context)
        state["location_shared"] = value  # type: ignore

    @staticmethod
    def is_location_shared(context: ContextTypes.DEFAULT_TYPE) -> bool:
        return FlowManager.get(context).get("location_shared", False)

    @staticmethod
    def reset_delivery_state(context: ContextTypes.DEFAULT_TYPE):
        """Полный сброс состояния доставки."""
        state = FlowManager.get(context)
        state["selected_delivery_id"] = None  
        state["location_shared"] = False
        state["tracking_active"] = False     

    @staticmethod
    def set_courier_data(context: ContextTypes.DEFAULT_TYPE, user_id: int, courier_id: int, role_id: int):
        state = FlowManager.get(context)
        state["courier_id"] = courier_id
        state["user_role_id"] = role_id

    @staticmethod
    def get_courier_id(context: ContextTypes.DEFAULT_TYPE) -> Optional[int]:
        return FlowManager.get(context).get("courier_id")

    @staticmethod
    def is_courier(context: ContextTypes.DEFAULT_TYPE) -> bool:
        return FlowManager.get(context).get("user_role_id") == 3

    @staticmethod
    def clear_courier_data(context: ContextTypes.DEFAULT_TYPE):
        state = FlowManager.get(context)
        state.pop("courier_id", None)
        state.pop("user_role_id", None)
