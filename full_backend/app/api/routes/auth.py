from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, OAuth2PasswordRequestForm
from typing import List

from app.models.announcement import (
    Token, 
    UserCreate, 
    UserResponse, 
    UserUpdate, 
    UserInDB,
    UserRole
)
from app.services.auth import (
    authenticate_user,
    create_access_token,
    create_refresh_token,
    get_current_active_user,
    require_admin,
    create_user,
    refresh_token,
    get_user_by_id
)
from app.core.config import settings
from app.db.database import get_users_collection
from loguru import logger

router = APIRouter()


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()):
    """Login user and return JWT tokens"""
    user = await authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Create tokens
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role},
        expires_delta=access_token_expires
    )
    refresh_token_str = create_refresh_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role}
    )
    
    return Token(
        accessToken=access_token,
        refreshToken=refresh_token_str,
        tokenType="bearer",
        expiresIn=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )


@router.post("/refresh", response_model=Token)
async def refresh_access_token(refresh_token_str: str):
    """Refresh access token using refresh token"""
    try:
        token_data = await refresh_token(refresh_token_str)
        return Token(**token_data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not refresh token"
        )


@router.post("/register", response_model=UserResponse)
async def register(
    user_data: UserCreate,
    current_user: UserInDB = Depends(require_admin())
):
    """Register new user (Admin only)"""
    try:
        user = await create_user(
            email=user_data.email,
            password=user_data.password,
            full_name=user_data.fullName,
            role=user_data.role
        )
        
        return UserResponse(
            **user.dict(by_alias=True),
            id=str(user.id)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User registration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not create user"
        )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: UserInDB = Depends(get_current_active_user)):
    """Get current user information"""
    return UserResponse(
        **current_user.dict(by_alias=True),
        id=str(current_user.id)
    )


@router.put("/me", response_model=UserResponse)
async def update_current_user(
    user_update: UserUpdate,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Update current user information"""
    try:
        users_collection = await get_users_collection()
        
        # Prepare update data
        update_data = {}
        if user_update.email and user_update.email != current_user.email:
            # Check if email is already taken
            existing = await users_collection.find_one({"email": user_update.email})
            if existing:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            update_data["email"] = user_update.email
        
        if user_update.fullName:
            update_data["fullName"] = user_update.fullName
            
        if user_update.password:
            from app.services.auth import get_password_hash
            update_data["hashedPassword"] = get_password_hash(user_update.password)
        
        if not update_data:
            return UserResponse(
                **current_user.dict(by_alias=True),
                id=str(current_user.id)
            )
        
        # Update user
        result = await users_collection.update_one(
            {"_id": current_user.id},
            {"$set": update_data}
        )
        
        if result.matched_count:
            updated_user = await get_user_by_id(str(current_user.id))
            return UserResponse(
                **updated_user.dict(by_alias=True),
                id=str(updated_user.id)
            )
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update user"
        )


@router.get("/users", response_model=List[UserResponse])
async def get_all_users(
    current_user: UserInDB = Depends(require_admin()),
    skip: int = 0,
    limit: int = 100
):
    """Get all users (Admin only)"""
    try:
        users_collection = await get_users_collection()
        
        cursor = users_collection.find({}).skip(skip).limit(limit).sort("createdAt", -1)
        users_data = await cursor.to_list(length=limit)
        
        return [
            UserResponse(**user_data, id=str(user_data["_id"]))
            for user_data in users_data
        ]
        
    except Exception as e:
        logger.error(f"Error getting users: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not retrieve users"
        )


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    current_user: UserInDB = Depends(require_admin())
):
    """Get user by ID (Admin only)"""
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    
    return UserResponse(
        **user.dict(by_alias=True),
        id=str(user.id)
    )


@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: UserInDB = Depends(require_admin())
):
    """Update user by ID (Admin only)"""
    try:
        users_collection = await get_users_collection()
        
        # Get user to update
        user = await get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        # Prepare update data
        update_data = {}
        
        if user_update.email and user_update.email != user.email:
            # Check if email is already taken
            existing = await users_collection.find_one({"email": user_update.email})
            if existing and str(existing["_id"]) != user_id:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already registered"
                )
            update_data["email"] = user_update.email
        
        if user_update.fullName:
            update_data["fullName"] = user_update.fullName
            
        if user_update.role:
            update_data["role"] = user_update.role
            
        if user_update.isActive is not None:
            update_data["isActive"] = user_update.isActive
            
        if user_update.password:
            from app.services.auth import get_password_hash
            update_data["hashedPassword"] = get_password_hash(user_update.password)
        
        if not update_data:
            return UserResponse(
                **user.dict(by_alias=True),
                id=str(user.id)
            )
        
        # Update user
        result = await users_collection.update_one(
            {"_id": user.id},
            {"$set": update_data}
        )
        
        if result.matched_count:
            updated_user = await get_user_by_id(user_id)
            return UserResponse(
                **updated_user.dict(by_alias=True),
                id=str(updated_user.id)
            )
        
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User update error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not update user"
        )


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: UserInDB = Depends(require_admin())
):
    """Delete user by ID (Admin only)"""
    try:
        # Don't allow deleting self
        if str(current_user.id) == user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        users_collection = await get_users_collection()
        result = await users_collection.delete_one({"_id": ObjectId(user_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {"message": "User deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User deletion error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not delete user"
        )


@router.post("/logout")
async def logout(current_user: UserInDB = Depends(get_current_active_user)):
    """Logout user (token invalidation would be handled client-side or with token blacklist)"""
    # In a production system, you might want to implement token blacklisting
    # For now, just return success - the client should discard the token
    return {"message": "Successfully logged out"}


@router.post("/change-password")
async def change_password(
    current_password: str,
    new_password: str,
    current_user: UserInDB = Depends(get_current_active_user)
):
    """Change current user's password"""
    try:
        from app.services.auth import verify_password, get_password_hash
        
        # Verify current password
        if not verify_password(current_password, current_user.hashedPassword):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect"
            )
        
        # Update password
        users_collection = await get_users_collection()
        result = await users_collection.update_one(
            {"_id": current_user.id},
            {"$set": {"hashedPassword": get_password_hash(new_password)}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        
        return {"message": "Password changed successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Password change error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not change password"
        )
