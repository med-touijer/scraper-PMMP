from datetime import datetime, timedelta
from typing import Optional, Union
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from bson import ObjectId
from loguru import logger

from app.core.config import settings
from app.db.database import get_users_collection
from app.models.announcement import UserInDB, TokenData, UserRole


# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT token handler
security = HTTPBearer()


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(data: dict) -> str:
    """Create JWT refresh token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


async def authenticate_user(email: str, password: str) -> Union[UserInDB, bool]:
    """Authenticate user by email and password"""
    try:
        users_collection = await get_users_collection()
        user_data = await users_collection.find_one({"email": email})
        
        if not user_data:
            return False
        
        user = UserInDB(**user_data)
        
        if not user.isActive:
            return False
            
        if not verify_password(password, user.hashedPassword):
            return False
            
        # Update last login
        await users_collection.update_one(
            {"_id": user.id},
            {"$set": {"lastLogin": datetime.utcnow()}}
        )
        
        return user
        
    except Exception as e:
        logger.error(f"Error authenticating user {email}: {e}")
        return False


async def get_user_by_id(user_id: str) -> Optional[UserInDB]:
    """Get user by ID"""
    try:
        users_collection = await get_users_collection()
        user_data = await users_collection.find_one({"_id": ObjectId(user_id)})
        
        if user_data:
            return UserInDB(**user_data)
        return None
        
    except Exception as e:
        logger.error(f"Error getting user by ID {user_id}: {e}")
        return None


async def get_user_by_email(email: str) -> Optional[UserInDB]:
    """Get user by email"""
    try:
        users_collection = await get_users_collection()
        user_data = await users_collection.find_one({"email": email})
        
        if user_data:
            return UserInDB(**user_data)
        return None
        
    except Exception as e:
        logger.error(f"Error getting user by email {email}: {e}")
        return None


def decode_token(token: str) -> TokenData:
    """Decode JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("role")
        token_type: str = payload.get("type")
        
        if user_id is None or email is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
                headers={"WWW-Authenticate": "Bearer"},
            )
            
        return TokenData(userId=user_id, email=email, role=role)
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserInDB:
    """Get current authenticated user"""
    token = credentials.credentials
    token_data = decode_token(token)
    
    user = await get_user_by_id(token_data.userId)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if not user.isActive:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Inactive user",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_active_user(current_user: UserInDB = Depends(get_current_user)) -> UserInDB:
    """Get current active user"""
    if not current_user.isActive:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Inactive user"
        )
    return current_user


def require_role(required_role: UserRole):
    """Decorator to require specific role"""
    async def role_checker(current_user: UserInDB = Depends(get_current_active_user)):
        if current_user.role != required_role and current_user.role != UserRole.ADMIN:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Operation not permitted"
            )
        return current_user
    return role_checker


def require_admin():
    """Require admin role"""
    return require_role(UserRole.ADMIN)


async def create_user(email: str, password: str, full_name: str, role: UserRole = UserRole.VIEWER) -> UserInDB:
    """Create new user"""
    try:
        users_collection = await get_users_collection()
        
        # Check if user exists
        existing_user = await users_collection.find_one({"email": email})
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Create user
        user_data = {
            "email": email,
            "fullName": full_name,
            "role": role,
            "hashedPassword": get_password_hash(password),
            "isActive": True,
            "createdAt": datetime.utcnow(),
            "lastLogin": None
        }
        
        result = await users_collection.insert_one(user_data)
        user_data["_id"] = result.inserted_id
        
        return UserInDB(**user_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating user {email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create user"
        )


async def refresh_token(refresh_token: str) -> dict:
    """Refresh access token using refresh token"""
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        email: str = payload.get("email")
        role: str = payload.get("role")
        token_type: str = payload.get("type")
        
        if token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type"
            )
            
        user = await get_user_by_id(user_id)
        if not user or not user.isActive:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive"
            )
        
        # Create new tokens
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role},
            expires_delta=access_token_expires
        )
        new_refresh_token = create_refresh_token(
            data={"sub": str(user.id), "email": user.email, "role": user.role}
        )
        
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
        
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate refresh token"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refreshing token: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not refresh token"
        )
