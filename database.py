from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from .config import DB_CONFIG, MONGODB_CONFIG
from motor.motor_asyncio import AsyncIOMotorClient
from .dependencies import logger

# PostgreSQL database configuration
# Database URL for async engine
DATABASE_URL = f"postgresql+asyncpg://{DB_CONFIG['username']}:{DB_CONFIG['password']}@" \
               f"{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"

# Main engine for API routes
async_engine = create_async_engine(
    DATABASE_URL,
    pool_size=25,
    max_overflow=5,
    pool_timeout=90,
    pool_recycle=3600,
    pool_pre_ping=True, # Verify connection health
)

# Session factory bound to the engine
AsyncSessionFactory = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

async def get_db():
    async with AsyncSessionFactory() as session:
        try:
            yield session
        except SQLAlchemyError as e:
            # await session.rollback()  # Rollback in case of an exception
            logger.error(f"Database session failed to create: {str(e)}")
            raise HTTPException(status_code=503, detail="We're experiencing a temporary issue. Please try again later.")

# MongoDB configuration
client = AsyncIOMotorClient(MONGODB_CONFIG["conn_url"])
mongo_db = client.get_database(MONGODB_CONFIG["database"])

def get_mongo_db():
    return mongo_db