# core/routing.py
import os
import httpx
import logging

logger = logging.getLogger(__name__)
ORS_API_KEY = os.getenv("ORS_API_KEY")
ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car"

async def get_route_geometry(lon_start: float, lat_start: float, lon_end: float, lat_end: float) -> list | None:
    """
    Возвращает геометрию маршрута (список [lon, lat]) от ORS.
    Формат координат: [longitude, latitude] — именно в таком порядке требует ORS.
    """
    if not ORS_API_KEY:
        logger.warning("⚠️ ORS API key не настроен")
        return None
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                ORS_URL,
                params={
                    "api_key": ORS_API_KEY,
                    "start": f"{lon_start},{lat_start}",
                    "end": f"{lon_end},{lat_end}",
                    "format": "geojson",
                    "geometry": "true",
                    "instructions": "false"
                }
            )
            
            # 🔹 Обработка ошибок с детальным логом
            if resp.status_code == 401:
                logger.error("❌ Неверный ORS API ключ")
                return None
            elif resp.status_code == 429:
                logger.error("⏱ Превышен лимит запросов к ORS")
                return None
            elif resp.status_code >= 400:
                logger.error(f"❌ Ошибка ORS {resp.status_code}: {resp.text[:200]}")
                return None
                
            resp.raise_for_status()
            data = resp.json()
            
            # Парсим GeoJSON LineString
            if data.get("features") and data["features"][0]["geometry"]["type"] == "LineString":
                # ORS возвращает [[lon1, lat1], [lon2, lat2], ...]
                segment = data["features"][0]["properties"]["segments"][0]
                return {
                    "geometry": data["features"][0]["geometry"]["coordinates"],  # [[lon, lat], ...]
                    "duration_sec": int(segment["duration"])  # время в секундах, умноженное на коэффициент (аналог небольших пробок)
                }
            return None
            
    except httpx.TimeoutException:
        logger.error("⏱ Таймаут запроса к ORS")
        return None
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при запросе к ORS: {e}")
        return None
    
    
async def get_route_geometry_from_coords(coords: list[tuple[float, float]]) -> list[list[float]] | None:
    """
    Возвращает геометрию маршрута от ORS для списка координат.
    
    Args:
        coords: список кортежей [(lon1, lat1), (lon2, lat2), ...]
                ВАЖНО: формат ORS — [longitude, latitude]
    
    Returns:
        Список координат [[lon1, lat1], [lon2, lat2], ...] для отрисовки на Leaflet,
        или None при ошибке.
    """
    if not ORS_API_KEY or len(coords) < 2:
        return None
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{ORS_URL}/geojson",
                headers={
                    "Accept": "application/json, application/geo+json, application/gpx+xml, img/png; charset=utf-8",
                    "Authorization": ORS_API_KEY,
                    "Content-Type": "application/json; charset=utf-8"
                },
                json={
                    "coordinates": coords,  # [[lon, lat], [lon, lat], ...]
                }
            )
            
            # Обработка ошибок
            if resp.status_code == 401:
                logger.error("❌ Неверный ORS API ключ")
                return None
            elif resp.status_code == 403:
                logger.error("❌ Доступ к ORS API запрещён (403)")
                return None
            elif resp.status_code == 429:
                logger.error("⏱ Превышен лимит запросов к ORS")
                return None
            elif resp.status_code >= 400:
                logger.error(f"❌ Ошибка ORS {resp.status_code}: {resp.text[:200]}")
                return None
            
            resp.raise_for_status()
            data = resp.json()
            
            # Парсим GeoJSON LineString
            if data.get("features") and data["features"][0]["geometry"]["type"] == "LineString":
                # ORS возвращает [[lon1, lat1], [lon2, lat2], ...]
                return data["features"][0]["geometry"]["coordinates"]
            return None
            
    except httpx.TimeoutException:
        logger.error("⏱ Таймаут запроса к ORS")
        return None
    except Exception as e:
        logger.error(f"❌ Ошибка при запросе к ORS: {e}")
        return None