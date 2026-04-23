# handlers/route_handler.py
"""Обработчики отображения маршрута курьера."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from typing import List, Tuple

from core.context import FlowManager
from core.db import get_pool, get_courier_current_route
from utils.keyboards import kb_back

logger = logging.getLogger(__name__)

def build_yandex_maps_url(lat: float, lon: float, zoom: int = 15) -> str:
    """Формирует ссылку на Яндекс.Карты с указанной точкой."""
    # Формат: ?pt=longitude,latitude&z=zoom&l=map
    return f"https://yandex.ru/maps/?pt={lon},{lat}&z={zoom}&l=map"

def build_yandex_route_url(points: List[Tuple[float, float]]) -> str:
    """
    Формирует ссылку на Яндекс.Карты с маршрутом через все точки.
    
    Args:
        points: Список кортежей (latitude, longitude) в порядке маршрута
        
    Returns:
        str: URL Яндекс.Карт с построенным маршрутом
        
    Пример:
        points = [(55.751244, 37.618423), (55.760123, 37.605678)]
        → https://yandex.ru/maps/?rtext=37.618423,55.751244~37.605678,55.760123&rtt=auto
    """
    if not points:
        return "https://yandex.ru/maps/"
    
    # Формат: longitude,latitude (обратный порядок!)
    route_points = "~".join(f"{lon},{lat}" for lat, lon in points)
    return f"https://yandex.ru/maps/?rtext={route_points}&rtt=auto"


async def show_courier_route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Показывает список точек текущего маршрута курьера."""
    query = update.callback_query
    await query.answer()
    
    if not FlowManager.is_courier(context):
        await query.edit_message_text("⚠️ Функция доступна только курьерам.", reply_markup=kb_back())
        return
    
    courier_id = FlowManager.get_courier_id(context)
    pool = get_pool(context)
    
    if not pool or not courier_id:
        await query.edit_message_text("❌ Ошибка подключения к БД.", reply_markup=kb_back())
        return
    
    try:
        delivery, points = await get_courier_current_route(pool, courier_id)
        
        if not delivery or not points:
            await query.edit_message_text(
                "🗺 *У вас нет активного маршрута.*\n\n"
                "Как только диспетчер назначит доставку с маршрутом, он появится здесь.",
                parse_mode="Markdown",
                reply_markup=kb_back()
            )
            return
        
        # Формируем текст с точками маршрута
        text = f"🗺 *Маршрут для заказа #{delivery['order_id']}*\n"
        text += f"📦 Доставка #{delivery['delivery_id']}\n"
        text += "─" * 20 + "\n\n"
        
        keyboard = []
        coords_for_route = []
        for p in points:
            # Статус точки
            status_icon = "✅" if p["actual_arrival_time"] else "⏳"
            time_info = ""
            if p["expected_arrival_time"]:
                time_info = f" 🕐 {p['expected_arrival_time'].strftime('%H:%M')}"
            
            # Текст кнопки: "1. 🏠 Адрес (15:30)"
            btn_text = f"{status_icon} {p['sequence_num']}. {p['address'][:40]}{'...' if len(p['address']) > 40 else ''}{time_info}"
            
            # Ссылка на Яндекс.Карты
            maps_url = build_yandex_maps_url(p["latitude"], p["longitude"])
            keyboard.append([InlineKeyboardButton(btn_text, url=maps_url)])

            # Добавляем координаты для общего маршрута
            coords_for_route.append((p["longitude"], p["latitude"]))
        
        if coords_for_route:
            full_route_url = build_yandex_route_url(coords_for_route)
            keyboard.append([InlineKeyboardButton("🗺 Открыть весь маршрут", url=full_route_url)])

        
        keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data="menu:main")])
        
        await query.edit_message_text(
            text + "📍 *Нажмите на адрес, чтобы открыть на карте:*\n",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    except Exception as e:
        logger.error(f"Ошибка загрузки маршрута: {e}")
        await query.edit_message_text("❌ Ошибка загрузки маршрута.", reply_markup=kb_back())