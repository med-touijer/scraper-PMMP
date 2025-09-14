from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi_pagination import add_pagination
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import redis.asyncio as redis
from contextlib import asynccontextmanager
from loguru import logger
import sys
from pathlib import Path

from app.core.config import settings
from app.db.database import connect_to_mongo, close_mongo_connection, ping_database
from app.api.routes import announcements, auth, scraper
from app.services.auth import create_user
from app.models.announcement import UserRole


# Configure logging
def setup_logging():
    """Setup application logging"""
    logger.remove()  # Remove default handler
    
    # Console logging
    logger.add(
        sys.stderr,
        level=settings.LOG_LEVEL,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
    )
    
    # File logging
    log_path = Path(settings.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.add(
        settings.LOG_FILE,
        rotation=settings.LOG_ROTATION,
        retention=settings.LOG_RETENTION,
        level=settings.LOG_LEVEL,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}"
    )


# Rate limiting setup
limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    logger.info("Starting up Marches Publics API...")
    
    try:
        # Setup logging
        setup_logging()
        
        # Connect to database
        await connect_to_mongo()
        
        # Create admin user if it doesn't exist
        await create_initial_admin()
        
        # Setup rate limiting with Redis
        try:
            redis_client = redis.from_url(settings.REDIS_URL)
            await redis_client.ping()
            limiter.storage = redis_client
            logger.info("Connected to Redis for rate limiting")
        except Exception as e:
            logger.warning(f"Could not connect to Redis: {e}. Using in-memory rate limiting.")
        
        logger.info("Application startup completed successfully")
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Marches Publics API...")
    await close_mongo_connection()
    logger.info("Application shutdown completed")


async def create_initial_admin():
    """Create initial admin user if none exists"""
    try:
        from app.services.auth import get_user_by_email
        
        admin_user = await get_user_by_email(settings.ADMIN_EMAIL)
        if not admin_user:
            await create_user(
                email=settings.ADMIN_EMAIL,
                password=settings.ADMIN_PASSWORD,
                full_name="System Administrator",
                role=UserRole.ADMIN
            )
            logger.info(f"Created initial admin user: {settings.ADMIN_EMAIL}")
        else:
            logger.info("Admin user already exists")
            
    except Exception as e:
        logger.error(f"Could not create initial admin user: {e}")


# Create FastAPI app
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="API for managing Moroccan public market announcements",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    docs_url=f"{settings.API_V1_PREFIX}/docs",
    redoc_url=f"{settings.API_V1_PREFIX}/redoc",
    lifespan=lifespan
)

# Add rate limiting middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=settings.ALLOWED_METHODS,
    allow_headers=settings.ALLOWED_HEADERS,
)

# Add trusted host middleware for production
if settings.ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*.marchespublics.ma", "localhost", "127.0.0.1"]
    )

# Add pagination
add_pagination(app)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    
    if settings.DEBUG:
        # In debug mode, return detailed error
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__,
                "path": str(request.url.path)
            }
        )
    else:
        # In production, return generic error
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"}
        )


# Health check endpoints
@app.get("/health")
async def health_check():
    """Basic health check"""
    return {"status": "healthy", "version": settings.PROJECT_VERSION}


@app.get("/health/detailed")
@limiter.limit("10/minute")
async def detailed_health_check(request: Request):
    """Detailed health check including database"""
    db_status = await ping_database()
    
    return {
        "status": "healthy" if db_status else "unhealthy",
        "version": settings.PROJECT_VERSION,
        "database": "connected" if db_status else "disconnected",
        "environment": settings.ENVIRONMENT,
        "timestamp": "2024-01-01T00:00:00Z"  # Would use actual timestamp
    }


# Root endpoint
@app.get("/")
async def root():
    """API root endpoint"""
    return {
        "message": "Marches Publics API",
        "version": settings.PROJECT_VERSION,
        "docs": f"{settings.API_V1_PREFIX}/docs",
        "health": "/health"
    }


# Rate limited test endpoint
@app.get("/test-rate-limit")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def test_rate_limit(request: Request):
    """Test rate limiting"""
    return {"message": "Rate limit test successful"}


# Include API routes
app.include_router(
    announcements.router,
    prefix=f"{settings.API_V1_PREFIX}/announcements",
    tags=["announcements"]
)

app.include_router(
    auth.router,
    prefix=f"{settings.API_V1_PREFIX}/auth",
    tags=["authentication"]
)

app.include_router(
    scraper.router,
    prefix=f"{settings.API_V1_PREFIX}/scraper",
    tags=["scraper"]
)


# Custom middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    
    # Log request
    logger.info(f"Request: {request.method} {request.url.path}")
    
    response = await call_next(request)
    
    # Log response
    process_time = time.time() - start_time
    logger.info(
        f"Response: {response.status_code} - Time: {process_time:.4f}s"
    )
    
    # Add process time header
    response.headers["X-Process-Time"] = str(process_time)
    
    return response


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
