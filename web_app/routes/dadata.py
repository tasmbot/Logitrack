# routes/dadata.py
import os
import logging
import httpx
from fastapi import APIRouter, Request, HTTPException, Query

router = APIRouter(prefix="/api", tags=["DaData"])
logger = logging.getLogger(__name__)

DADATA_API_KEY = os.getenv("DADATA_API_KEY")
DADATA_BASE_URL = os.getenv("DADATA_BASE_URL", "https://suggestions.dadata.ru/suggestions/api/4_1/rs")

@router.get("/addresses/suggest")
async def suggest_address(
    request: Request,
    query: str = Query(..., min_length=3, description="Поисковый запрос (мин. 3 символа)"),
    count: int = Query(5, ge=1, le=10, description="Количество подсказок")
):
    """
    Проксирует запрос к DaData API для получения подсказок адресов.
    Возвращает упрощённый формат для фронтенда.
    """
    if not DADATA_API_KEY:
        raise HTTPException(status_code=500, detail="DaData API key не настроен")

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{DADATA_BASE_URL}/suggest/address",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                    "Authorization": f"Token {DADATA_API_KEY}"
                },
                json={
                    "query": query,
                    "count": count,
                    "from_bound": {"value": "city"},
                    "to_bound": {"value": "house"}
                }
            )
            response.raise_for_status()
            data = response.json()

            # Формируем упрощённый ответ для фронтенда
            suggestions = []
            for item in data.get("suggestions", []):
                suggestions.append({
                    "value": item["value"],  # Человекочитаемый адрес
                    "unrestricted_value": item.get("unrestricted_value"),  # Полный адрес
                    "data": {
                        "lat": item["data"]["geo_lat"],
                        "lon": item["data"]["geo_lon"]
                    }
                })
            
            return {"suggestions": suggestions}

    except httpx.TimeoutException:
        logger.error("⏱ Таймаут запроса к DaData")
        raise HTTPException(status_code=504, detail="Сервис подсказок не отвечает")
    except httpx.HTTPStatusError as e:
        logger.error(f"❌ HTTP ошибка от DaData: {e.response.status_code}")
        if e.response.status_code == 429:
            raise HTTPException(status_code=429, detail="Превышен лимит запросов к сервису адресов")
        raise HTTPException(status_code=502, detail="Ошибка получения подсказок")
    except Exception as e:
        logger.error(f"❌ Неожиданная ошибка при запросе к DaData: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервиса подсказок")