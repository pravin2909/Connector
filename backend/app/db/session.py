from collections.abc import AsyncIterator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings
from app.db.models import User

engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

LOCAL_USER_EMAIL = "local@connecter.ai"


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as db:
        yield db


async def ensure_local_user() -> User:
    """Single-user local mode: make sure the default user exists."""
    async with SessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == LOCAL_USER_EMAIL))
        if user is None:
            user = User(email=LOCAL_USER_EMAIL, display_name="Local User")
            db.add(user)
            await db.commit()
        return user
