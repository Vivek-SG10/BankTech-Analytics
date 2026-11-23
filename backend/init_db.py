import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from app.auth.models import Base
import app.surveys.models
from app.auth.crud import get_user_by_email, create_user
from app.auth.security import hash_password
from app.auth.seed import DEMO_ACCOUNTS, DEMO_PASSWORD
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

DB_FILE = os.path.join(os.path.dirname(__file__), "banktech.db")
DB_URL = f"sqlite+aiosqlite:///{DB_FILE.replace(chr(92), '/')}"

async def init():
    print(f"Initializing database at {DB_URL}...")
    engine = create_async_engine(DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Tables created.")
    
    Session = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        for acct in DEMO_ACCOUNTS:
            existing = await get_user_by_email(session, acct["email"])
            if not existing:
                await create_user(
                    session,
                    name=acct["name"],
                    email=acct["email"],
                    hashed_password=hash_password(DEMO_PASSWORD),
                    role=acct["role"],
                    department=acct["department"],
                )
                print(f"Created demo account: {acct['email']} ({acct['role']})")
    await engine.dispose()
    print("Database initialization complete!")

if __name__ == "__main__":
    asyncio.run(init())

