from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import get_settings
from app.exceptions import RemnawaveAPIError

logger = logging.getLogger(__name__)


class RemnawaveClient:
    """
    Thin API wrapper. Paths are configurable via env to match exact Remnawave schema.
    """

    def __init__(self) -> None:
        self.settings = get_settings()
        self.headers = {
            "Authorization": f"Bearer {self.settings.remnawave_api_key}",
            "Content-Type": "application/json",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url_path = path if path.startswith("/") else f"/{path}"
        async with httpx.AsyncClient(
            base_url=self.settings.remnawave_base_url.rstrip("/"),
            headers=self.headers,
            timeout=self.settings.remnawave_timeout,
        ) as client:
            response = await client.request(method, url_path, params=params, json=json)
        if response.status_code >= 400:
            payload: dict[str, Any]
            try:
                payload = response.json()
            except ValueError:
                payload = {"raw": response.text}
            raise RemnawaveAPIError(
                f"Remnawave API error on {method} {url_path}",
                status_code=response.status_code,
                payload=payload,
            )
        if not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise RemnawaveAPIError(
                f"Invalid JSON from Remnawave on {method} {url_path}", status_code=response.status_code
            ) from exc

    async def create_user(self, telegram_id: int, username: str | None, full_name: str | None) -> dict[str, Any]:
        payload = {"external_id": str(telegram_id), "username": username, "full_name": full_name}
        return await self._request("POST", self.settings.remnawave_users_path, json=payload)

    async def get_user(self, remote_user_id: str) -> dict[str, Any]:
        return await self._request("GET", f"{self.settings.remnawave_users_path}/{remote_user_id}")

    async def find_user_by_external_id(self, external_id: int) -> dict[str, Any] | None:
        resp = await self._request(
            "GET",
            self.settings.remnawave_users_path,
            params={"external_id": str(external_id)},
        )
        data = resp.get("data") or resp.get("items") or []
        if isinstance(data, list) and data:
            return data[0]
        return None

    async def delete_user(self, remote_user_id: str) -> None:
        await self._request("DELETE", f"{self.settings.remnawave_users_path}/{remote_user_id}")

    async def get_user_subscriptions(self, remote_user_id: str) -> list[dict[str, Any]]:
        resp = await self._request(
            "GET",
            self.settings.remnawave_subscriptions_path,
            params={"user_id": remote_user_id},
        )
        data = resp.get("data") or resp.get("items") or []
        return data if isinstance(data, list) else []

    async def create_subscription(
        self,
        remote_user_id: str,
        *,
        plan_id: str | None,
        duration_days: int,
        traffic_limit_gb: float | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "user_id": remote_user_id,
            "duration_days": duration_days,
        }
        if plan_id:
            payload["plan_id"] = plan_id
        if traffic_limit_gb is not None:
            payload["traffic_limit_gb"] = traffic_limit_gb
        return await self._request("POST", self.settings.remnawave_subscriptions_path, json=payload)

    async def extend_subscription(self, remote_subscription_id: str, duration_days: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"{self.settings.remnawave_subscriptions_path}/{remote_subscription_id}/extend",
            json={"duration_days": duration_days},
        )

    async def get_subscription(self, remote_subscription_id: str) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"{self.settings.remnawave_subscriptions_path}/{remote_subscription_id}",
        )

    async def get_connect_link(self, remote_subscription_id: str) -> str | None:
        response = await self._request(
            "GET",
            f"{self.settings.remnawave_subscriptions_path}/{remote_subscription_id}/connect-link",
        )
        if "connect_url" in response:
            return response["connect_url"]
        data = response.get("data") or {}
        if isinstance(data, dict):
            return data.get("connect_url")
        return None

    async def list_servers(self) -> list[dict[str, Any]]:
        response = await self._request("GET", self.settings.remnawave_servers_path)
        data = response.get("data") or response.get("items") or []
        return data if isinstance(data, list) else []

    async def list_nodes(self) -> list[dict[str, Any]]:
        response = await self._request("GET", self.settings.remnawave_nodes_path)
        data = response.get("data") or response.get("items") or []
        return data if isinstance(data, list) else []

    async def get_stats(self) -> dict[str, Any]:
        return await self._request("GET", self.settings.remnawave_stats_path)

