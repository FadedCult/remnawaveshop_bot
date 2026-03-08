from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.bootstrap import init_db
from app.db.session import SessionLocal, get_db_session
from app.exceptions import RemnawaveAPIError
from app.logging import setup_logging
from app.services.payment_stub import PaymentService
from app.services.scheduler import AppScheduler
from app.web.routes_admin import router as admin_router

logger = logging.getLogger(__name__)
_scheduler = AppScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    await init_db(with_seed=True)
    _scheduler.start()
    _scheduler.register_periodic_promo_job(SessionLocal)
    logger.info("Web app started")
    yield
    _scheduler.stop()
    logger.info("Web app stopped")


def create_web_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    templates_path = Path(__file__).parent / "templates"
    static_path = Path(__file__).parent / "static"
    app.state.templates = Jinja2Templates(directory=str(templates_path))
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/")
    async def root(request: Request):
        return JSONResponse(
            {
                "service": settings.app_name,
                "admin_panel": f"https://{settings.web_domain}/admin/login",
                "message": "Use Telegram bot for user flow and /admin for operators.",
            }
        )

    @app.post("/api/payments/webhook")
    async def payment_webhook(
        payload: dict,
        session: AsyncSession = Depends(get_db_session),
    ):
        service = PaymentService(session)
        await service.process_webhook(payload)
        await session.commit()
        return {"ok": True}

    @app.exception_handler(RemnawaveAPIError)
    async def remnawave_error_handler(_: Request, exc: RemnawaveAPIError):
        logger.error("Remnawave error: status=%s payload=%s", exc.status_code, exc.payload)
        return JSONResponse(
            status_code=502,
            content={"detail": "Remnawave API error", "status": exc.status_code},
        )

    app.include_router(admin_router)
    return app


app = create_web_app()
