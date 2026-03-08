from __future__ import annotations

import logging
from decimal import Decimal

from aiogram import Bot
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import BroadcastKindEnum, SegmentEnum, TicketStatusEnum
from app.db.repositories.broadcasts import BroadcastRepository
from app.db.repositories.logs import LogRepository
from app.db.repositories.subscriptions import SubscriptionRepository
from app.db.repositories.surveys import SurveyRepository
from app.db.repositories.tariffs import TariffRepository
from app.db.repositories.tickets import TicketRepository
from app.db.repositories.users import UserRepository
from app.db.session import get_db_session
from app.services.broadcast_service import BroadcastService
from app.services.server_service import ServerService
from app.services.subscription_service import SubscriptionService
from app.services.survey_service import SurveyService
from app.services.ticket_service import TicketService
from app.web.auth import COOKIE_NAME, create_session_token, hash_password, is_authorized, verify_password

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def _redirect_login() -> RedirectResponse:
    return RedirectResponse("/admin/login", status_code=302)


def _as_bool(raw: str | None) -> bool:
    return str(raw or "").lower() in {"1", "true", "on", "yes"}


async def _ensure_admin_login(request: Request) -> str | None:
    ok, login = is_authorized(request)
    if not ok:
        return None
    return login


def _tmpl(request: Request, template_name: str, context: dict):
    templates = request.app.state.templates
    return templates.TemplateResponse(
        template_name,
        {"request": request, **context},
    )


@router.get("/login")
async def admin_login_page(request: Request):
    ok, _ = is_authorized(request)
    if ok:
        return RedirectResponse("/admin/", status_code=302)
    return _tmpl(request, "admin/login.html", {"error": None})


@router.post("/login")
async def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    settings = get_settings()
    if username != settings.admin_username or not verify_password(password):
        return _tmpl(request, "admin/login.html", {"error": "Неверный логин или пароль"})
    token = create_session_token(username)
    response = RedirectResponse("/admin/", status_code=302)
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        secure=settings.is_production,
        samesite="lax",
        max_age=60 * 60 * 12,
    )
    return response


@router.get("/logout")
async def admin_logout():
    response = RedirectResponse("/admin/login", status_code=302)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get("/")
async def dashboard(request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()

    user_repo = UserRepository(session)
    log_repo = LogRepository(session)
    ticket_repo = TicketRepository(session)
    surveys = SurveyRepository(session)

    context = {
        "admin_login": admin_login,
        "total_users": await user_repo.count_all(),
        "active_subscriptions": await user_repo.count_active_subscribers(),
        "new_users_7d": await user_repo.count_new_for_days(7),
        "open_tickets": len(await ticket_repo.list_all(status=TicketStatusEnum.open)),
        "surveys_active": len(await surveys.get_active()),
        "actions": await log_repo.list_admin_actions(20),
    }
    return _tmpl(request, "admin/dashboard.html", context)


@router.get("/tariffs")
async def tariffs_page(request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    repo = TariffRepository(session)
    tariffs = await repo.list_all()
    return _tmpl(request, "admin/tariffs.html", {"admin_login": admin_login, "tariffs": tariffs})


@router.post("/tariffs/create")
async def tariffs_create(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    name: str = Form(...),
    description: str = Form(""),
    duration_days: int = Form(...),
    traffic_limit_gb: str = Form(""),
    price: Decimal = Form(...),
    currency: str = Form("RUB"),
    remnawave_plan_id: str = Form(""),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()

    repo = TariffRepository(session)
    log_repo = LogRepository(session)
    tariff = await repo.create(
        name=name,
        description=description or None,
        duration_days=duration_days,
        traffic_limit_gb=float(traffic_limit_gb) if traffic_limit_gb else None,
        price=price,
        currency=currency,
        remnawave_plan_id=remnawave_plan_id or None,
    )
    await log_repo.log_admin_action(
        admin_login=admin_login,
        action="create_tariff",
        entity="tariff",
        entity_id=str(tariff.id),
        details={"name": name, "price": str(price)},
    )
    await session.commit()
    return RedirectResponse("/admin/tariffs", status_code=302)


@router.post("/tariffs/{tariff_id}/update")
async def tariffs_update(
    tariff_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    name: str = Form(...),
    description: str = Form(""),
    duration_days: int = Form(...),
    traffic_limit_gb: str = Form(""),
    price: Decimal = Form(...),
    currency: str = Form("RUB"),
    remnawave_plan_id: str = Form(""),
    is_active: str = Form("off"),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    repo = TariffRepository(session)
    log_repo = LogRepository(session)
    tariff = await repo.get_by_id(tariff_id)
    if tariff:
        await repo.update(
            tariff,
            name=name,
            description=description or None,
            duration_days=duration_days,
            traffic_limit_gb=float(traffic_limit_gb) if traffic_limit_gb else None,
            price=price,
            currency=currency,
            remnawave_plan_id=remnawave_plan_id or None,
            is_active=_as_bool(is_active),
        )
        await log_repo.log_admin_action(
            admin_login=admin_login,
            action="update_tariff",
            entity="tariff",
            entity_id=str(tariff_id),
            details={"name": name, "price": str(price)},
        )
        await session.commit()
    return RedirectResponse("/admin/tariffs", status_code=302)


@router.post("/tariffs/{tariff_id}/delete")
async def tariffs_delete(tariff_id: int, request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    repo = TariffRepository(session)
    log_repo = LogRepository(session)
    tariff = await repo.get_by_id(tariff_id)
    if tariff:
        await repo.delete(tariff)
        await log_repo.log_admin_action(
            admin_login=admin_login,
            action="delete_tariff",
            entity="tariff",
            entity_id=str(tariff_id),
        )
        await session.commit()
    return RedirectResponse("/admin/tariffs", status_code=302)


@router.get("/users")
async def users_page(
    request: Request,
    q: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    repo = UserRepository(session)
    users = await repo.list_users(search=q, limit=200, offset=0)
    sub_repo = SubscriptionRepository(session)
    rows = []
    for user in users:
        active_sub = await sub_repo.get_active_for_user(user.id)
        rows.append({"user": user, "active_subscription": active_sub})
    return _tmpl(
        request,
        "admin/users.html",
        {
            "admin_login": admin_login,
            "rows": rows,
            "q": q or "",
        },
    )


@router.get("/users/{user_id}")
async def user_detail(
    user_id: int,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    user_repo = UserRepository(session)
    sub_repo = SubscriptionRepository(session)
    tariff_repo = TariffRepository(session)
    user = await user_repo.get_by_id(user_id)
    if not user:
        return RedirectResponse("/admin/users", status_code=302)
    sub = await sub_repo.get_active_for_user(user.id)
    tariff = await tariff_repo.get_by_id(sub.tariff_id) if sub and sub.tariff_id else None
    return _tmpl(
        request,
        "admin/user_detail.html",
        {"admin_login": admin_login, "user": user, "subscription": sub, "tariff": tariff},
    )


@router.post("/users/{user_id}/balance")
async def user_balance(
    user_id: int,
    request: Request,
    amount: Decimal = Form(...),
    session: AsyncSession = Depends(get_db_session),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    user_repo = UserRepository(session)
    log_repo = LogRepository(session)
    user = await user_repo.get_by_id(user_id)
    if user:
        await user_repo.adjust_balance(user, amount=amount)
        await log_repo.log_admin_action(
            admin_login=admin_login,
            action="adjust_balance",
            entity="user",
            entity_id=str(user.id),
            details={"delta": str(amount)},
        )
        await session.commit()
    return RedirectResponse(f"/admin/users/{user_id}", status_code=302)


@router.post("/users/{user_id}/message")
async def user_message(
    user_id: int,
    request: Request,
    text: str = Form(...),
    session: AsyncSession = Depends(get_db_session),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    user = await UserRepository(session).get_by_id(user_id)
    if user:
        settings = get_settings()
        bot = Bot(settings.bot_token)
        try:
            await bot.send_message(user.telegram_id, text)
        finally:
            await bot.session.close()
        await LogRepository(session).log_admin_action(
            admin_login=admin_login,
            action="send_user_message",
            entity="user",
            entity_id=str(user.id),
            details={"text": text[:500]},
        )
        await session.commit()
    return RedirectResponse(f"/admin/users/{user_id}", status_code=302)


@router.post("/users/{user_id}/delete")
async def user_delete(user_id: int, request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    user_repo = UserRepository(session)
    log_repo = LogRepository(session)
    user = await user_repo.get_by_id(user_id)
    if user:
        service = SubscriptionService(session)
        try:
            await service.delete_remote_user(user)
        except Exception:
            logger.exception("Failed to delete remote user")
        await user_repo.delete_user(user)
        await log_repo.log_admin_action(
            admin_login=admin_login,
            action="delete_user",
            entity="user",
            entity_id=str(user_id),
        )
        await session.commit()
    return RedirectResponse("/admin/users", status_code=302)


@router.get("/tickets")
async def tickets_page(
    request: Request,
    status: str | None = None,
    session: AsyncSession = Depends(get_db_session),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    repo = TicketRepository(session)
    status_enum = None
    if status and status in {s.value for s in TicketStatusEnum}:
        status_enum = TicketStatusEnum(status)
    tickets = await repo.list_all(status=status_enum)
    return _tmpl(request, "admin/tickets.html", {"admin_login": admin_login, "tickets": tickets, "status": status})


@router.post("/tickets/{ticket_id}/reply")
async def tickets_reply(
    ticket_id: int,
    request: Request,
    text: str = Form(...),
    session: AsyncSession = Depends(get_db_session),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    repo = TicketRepository(session)
    ticket = await repo.get_by_id(ticket_id)
    if ticket:
        service = TicketService(session)
        await service.reply_from_admin(ticket, admin_telegram_id=0, text=text)
        await LogRepository(session).log_admin_action(
            admin_login=admin_login,
            action="reply_ticket",
            entity="ticket",
            entity_id=str(ticket_id),
        )
        await session.commit()
    return RedirectResponse("/admin/tickets", status_code=302)


@router.post("/tickets/{ticket_id}/close")
async def tickets_close(ticket_id: int, request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    repo = TicketRepository(session)
    ticket = await repo.get_by_id(ticket_id)
    if ticket:
        service = TicketService(session)
        await service.close_ticket(ticket)
        await LogRepository(session).log_admin_action(
            admin_login=admin_login,
            action="close_ticket",
            entity="ticket",
            entity_id=str(ticket_id),
        )
        await session.commit()
    return RedirectResponse("/admin/tickets", status_code=302)


@router.get("/messages")
async def messages_page(request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    broadcasts = await BroadcastRepository(session).list_all()
    return _tmpl(
        request,
        "admin/messages.html",
        {"admin_login": admin_login, "broadcasts": broadcasts, "segments": list(SegmentEnum)},
    )


@router.post("/messages/send")
async def messages_send(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    image_url: str = Form(""),
    target_group: str = Form("all"),
    kind: str = Form("broadcast"),
    periodic_enabled: str = Form("off"),
    periodic_cron: str = Form(""),
    session: AsyncSession = Depends(get_db_session),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()

    segment = SegmentEnum(target_group) if target_group in {e.value for e in SegmentEnum} else SegmentEnum.all
    kind_enum = (
        BroadcastKindEnum(kind) if kind in {e.value for e in BroadcastKindEnum} else BroadcastKindEnum.broadcast
    )
    service = BroadcastService(session)
    broadcast = await service.create_broadcast(
        title=title,
        content=content,
        image_url=image_url or None,
        target_group=segment,
        kind=kind_enum,
        periodic_enabled=_as_bool(periodic_enabled),
        periodic_cron=periodic_cron or None,
        created_by=admin_login,
    )
    if not _as_bool(periodic_enabled):
        await service.send_broadcast(broadcast.id)
    await LogRepository(session).log_admin_action(
        admin_login=admin_login,
        action="create_broadcast",
        entity="broadcast",
        entity_id=str(broadcast.id),
        details={"segment": segment.value, "kind": kind_enum.value},
    )
    await session.commit()
    return RedirectResponse("/admin/messages", status_code=302)


@router.get("/surveys")
async def surveys_page(request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    repo = SurveyRepository(session)
    surveys = await repo.list_all()
    return _tmpl(request, "admin/surveys.html", {"admin_login": admin_login, "surveys": surveys})


@router.post("/surveys/create")
async def surveys_create(
    request: Request,
    question: str = Form(...),
    send_now: str = Form("on"),
    session: AsyncSession = Depends(get_db_session),
):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    service = SurveyService(session)
    if _as_bool(send_now):
        survey = await service.create_and_send(question=question, created_by=admin_login)
    else:
        survey = await SurveyRepository(session).create(question=question, created_by=admin_login)
    await LogRepository(session).log_admin_action(
        admin_login=admin_login,
        action="create_survey",
        entity="survey",
        entity_id=str(survey.id),
    )
    await session.commit()
    return RedirectResponse("/admin/surveys", status_code=302)


@router.post("/surveys/{survey_id}/close")
async def surveys_close(survey_id: int, request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    repo = SurveyRepository(session)
    survey = await repo.get_by_id(survey_id)
    if survey:
        await repo.close(survey)
        await LogRepository(session).log_admin_action(
            admin_login=admin_login,
            action="close_survey",
            entity="survey",
            entity_id=str(survey_id),
        )
        await session.commit()
    return RedirectResponse("/admin/surveys", status_code=302)


@router.get("/servers")
async def servers_page(request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    snapshots = await LogRepository(session).list_latest_snapshots(limit=200)
    stats = {}
    try:
        stats = await ServerService(session).get_stats()
    except Exception:
        logger.exception("Failed to load server stats")
    return _tmpl(
        request,
        "admin/servers.html",
        {"admin_login": admin_login, "snapshots": snapshots, "stats": stats},
    )


@router.post("/servers/sync")
async def servers_sync(request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    service = ServerService(session)
    await service.sync_servers()
    await LogRepository(session).log_admin_action(
        admin_login=admin_login,
        action="sync_servers",
        entity="server",
    )
    await session.commit()
    return RedirectResponse("/admin/servers", status_code=302)


@router.get("/system")
async def system_page(request: Request, session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    settings = get_settings()
    integrations = {
        "telegram": {"configured": bool(settings.bot_token), "admins": settings.bot_admin_ids},
        "remnawave": {
            "base_url": settings.remnawave_base_url,
            "configured": bool(settings.remnawave_api_key),
        },
        "payments": {
            "provider": settings.payment_provider,
            "configured": bool(settings.payment_api_key),
            "webhook_configured": bool(settings.payment_webhook_secret),
        },
    }
    return _tmpl(
        request,
        "admin/system.html",
        {"admin_login": admin_login, "integrations": integrations, "settings": settings},
    )


@router.post("/system/hash-password")
async def system_hash_password(request: Request, raw_password: str = Form(...), session: AsyncSession = Depends(get_db_session)):
    admin_login = await _ensure_admin_login(request)
    if not admin_login:
        return _redirect_login()
    hashed = hash_password(raw_password)
    await LogRepository(session).log_admin_action(
        admin_login=admin_login,
        action="generate_password_hash",
        entity="system",
    )
    await session.commit()
    return _tmpl(
        request,
        "admin/system.html",
        {
            "admin_login": admin_login,
            "integrations": {
                "telegram": {"configured": bool(get_settings().bot_token), "admins": get_settings().bot_admin_ids},
                "remnawave": {
                    "base_url": get_settings().remnawave_base_url,
                    "configured": bool(get_settings().remnawave_api_key),
                },
                "payments": {
                    "provider": get_settings().payment_provider,
                    "configured": bool(get_settings().payment_api_key),
                    "webhook_configured": bool(get_settings().payment_webhook_secret),
                },
            },
            "settings": get_settings(),
            "generated_hash": hashed,
        },
    )

