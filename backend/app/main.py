from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes.health import router as health_router
from app.routes.upload import router as upload_router
from app.routes.history import router as history_router
from app.config import SHEETS_WEBHOOK_URL, SHEETS_SECRET
from app.services.sheets_service import init_sheets
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import logging
import asyncio
import httpx
import os
from dotenv import load_dotenv

logger = logging.getLogger(__name__)
load_dotenv()

KEEP_ALIVE_URL = os.getenv("KEEP_ALIVE_URL", "https://mcl-daak.onrender.com/health")
_cors_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173")
CORS_ORIGINS = [origin.strip() for origin in _cors_origins.split(",") if origin.strip()]

if SHEETS_WEBHOOK_URL and SHEETS_SECRET:
    init_sheets(SHEETS_WEBHOOK_URL, SHEETS_SECRET)


logging.basicConfig(level=logging.INFO)



async def keep_alive():
    await asyncio.sleep(60)  # wait 1 min after startup before first ping
    while True:
        try:
            async with httpx.AsyncClient() as client:
                if KEEP_ALIVE_URL:
                    await client.get(KEEP_ALIVE_URL, timeout=10)
                logger.info("Keep-alive ping sent")
        except Exception as e:
            logger.warning(f"Keep-alive ping failed: {e}")
        await asyncio.sleep(600)  # wait 10 minutes before next ping
@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(keep_alive())
    yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(upload_router)
app.include_router(history_router)
