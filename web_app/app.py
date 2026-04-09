# app.py
import asyncpg
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config import DB_CONFIG, SECRET_KEY, ROLE_NAMES
from routes import auth, main, profile, operator, client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация пула БД при старте
    app.state.db_pool = await asyncpg.create_pool(**DB_CONFIG, min_size=1, max_size=5)
    yield
    # Закрытие пула при остановке
    if app.state.db_pool:
        await app.state.db_pool.close()

app = FastAPI(title="LogiTrack Analytics MVP", lifespan=lifespan)

# Middleware
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# Статика и шаблоны
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
templates.env.globals["ROLE_NAMES"] = ROLE_NAMES

# Передаём templates в state, чтобы использовать в роутах
app.state.templates = templates

# Роуты
app.include_router(auth.router)
app.include_router(main.router)
app.include_router(profile.router)
app.include_router(operator.router) 
app.include_router(client.router) 