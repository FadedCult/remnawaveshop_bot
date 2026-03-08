from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories.logs import LogRepository
from app.services.remnawave import RemnawaveClient


class ServerService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.remnawave = RemnawaveClient()
        self.log_repo = LogRepository(session)

    async def sync_servers(self) -> dict:
        servers = await self.remnawave.list_servers()
        nodes = await self.remnawave.list_nodes()

        by_server_name: dict[str, dict] = {}
        for server in servers:
            name = str(server.get("name") or server.get("id") or "unknown-server")
            by_server_name[name] = {"server": server, "nodes": []}

        for node in nodes:
            server_name = str(node.get("server_name") or node.get("server") or "unknown-server")
            by_server_name.setdefault(server_name, {"server": {"name": server_name}, "nodes": []})
            by_server_name[server_name]["nodes"].append(node)

        for server_name, payload in by_server_name.items():
            server = payload["server"]
            for node in payload["nodes"] or [{}]:
                await self.log_repo.add_server_snapshot(
                    server_name=server_name,
                    status=str(node.get("status") or server.get("status") or "unknown"),
                    node_id=str(node.get("id")) if node.get("id") else None,
                    load_percent=float(node.get("load_percent")) if node.get("load_percent") is not None else None,
                    users_online=int(node.get("users_online")) if node.get("users_online") is not None else None,
                    raw={"server": server, "node": node},
                )
        await self.session.flush()
        return {"servers": servers, "nodes": nodes, "grouped": by_server_name}

    async def get_stats(self) -> dict:
        return await self.remnawave.get_stats()

