import uvicorn

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.web.app:app",
        host=settings.web_host,
        port=settings.web_port,
        reload=not settings.is_production,
    )


if __name__ == "__main__":
    main()

