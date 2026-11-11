import asyncio
from app.core.database import engine
from sqlalchemy import inspect

async def check():
    async with engine.connect() as conn:
        def get_tables(sync_conn):
            return inspect(sync_conn).get_table_names()
        print('Tables:', await conn.run_sync(get_tables))

if __name__ == "__main__":
    asyncio.run(check())
