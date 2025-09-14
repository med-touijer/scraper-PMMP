from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase, AsyncIOMotorCollection
from pymongo.errors import DuplicateKeyError
from app.core.config import settings
from loguru import logger
import asyncio


class Database:
    client: AsyncIOMotorClient = None
    database: AsyncIOMotorDatabase = None


db = Database()


async def get_database() -> AsyncIOMotorDatabase:
    return db.database


async def get_announcements_collection() -> AsyncIOMotorCollection:
    return db.database[settings.MONGODB_COLLECTION_NAME]


async def get_users_collection() -> AsyncIOMotorCollection:
    return db.database[settings.MONGODB_USER_COLLECTION]


async def connect_to_mongo():
    """Create database connection"""
    logger.info("Connecting to MongoDB...")
    try:
        db.client = AsyncIOMotorClient(
            settings.MONGODB_URI,
            maxPoolSize=10,
            minPoolSize=1,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
        )
        
        # Test connection
        await db.client.admin.command('ping')
        db.database = db.client[settings.MONGODB_DB_NAME]
        
        # Create indexes
        await create_indexes()
        
        logger.info(f"Connected to MongoDB database: {settings.MONGODB_DB_NAME}")
        
    except Exception as e:
        logger.error(f"Could not connect to MongoDB: {e}")
        raise


async def close_mongo_connection():
    """Close database connection"""
    logger.info("Closing connection to MongoDB...")
    if db.client:
        db.client.close()


async def create_indexes():
    """Create database indexes for better performance"""
    try:
        announcements_collection = await get_announcements_collection()
        users_collection = await get_users_collection()
        
        # Indexes for announcements collection
        await announcements_collection.create_index("lienDeConsultation", unique=True, sparse=True)
        await announcements_collection.create_index([("reference", 1), ("datePublication", 1)])
        await announcements_collection.create_index("datePublication")
        await announcements_collection.create_index("dateLimite")
        await announcements_collection.create_index("procedure")
        await announcements_collection.create_index("categorie")
        await announcements_collection.create_index("acheteurPublic")
        await announcements_collection.create_index([("objet", "text"), ("acheteurPublic", "text"), ("lieuExecution", "text")])
        await announcements_collection.create_index("createdAt")
        
        # Indexes for users collection
        await users_collection.create_index("email", unique=True)
        await users_collection.create_index("role")
        await users_collection.create_index("isActive")
        
        logger.info("Database indexes created successfully")
        
    except DuplicateKeyError:
        logger.warning("Some indexes already exist, continuing...")
    except Exception as e:
        logger.error(f"Error creating indexes: {e}")
        raise


# Health check function
async def ping_database() -> bool:
    """Check if database is reachable"""
    try:
        if not db.client:
            return False
        await db.client.admin.command('ping')
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False


# Helper function for transactions
async def get_session():
    """Get a database session for transactions"""
    if db.client:
        return await db.client.start_session()
    return None
