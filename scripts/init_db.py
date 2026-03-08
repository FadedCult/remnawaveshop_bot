import asyncio

from app.db.bootstrap import init_db


if __name__ == "__main__":
    asyncio.run(init_db(with_seed=True))
    print("Database initialized")

