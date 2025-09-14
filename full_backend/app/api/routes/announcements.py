from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi_pagination import Page, paginate
from fastapi_pagination.ext.motor import paginate as motor_paginate

from app.models.announcement import (
    AnnouncementResponse,
    AnnouncementCreate,
    AnnouncementUpdate,
    AnnouncementSearchFilters,
    AnnouncementStats,
    UserInDB
)
from app.services.announcement import AnnouncementService
from app.services.auth import get_current_active_user, require_admin

router = APIRouter()


@router.get("/", response_model=Page[AnnouncementResponse])
async def get_announcements(
    skip: int = Query(0, ge=0, description="Number of announcements to skip"),
    limit: int = Query(20, ge=1, le=100, description="Number of announcements to return"),
    procedure: Optional[str] = Query(None, description="Filter by procedure type"),
    categorie: Optional[str] = Query(None, description="Filter by category"),
    acheteur_public: Optional[str] = Query(None, description="Filter by public buyer"),
    lieu_execution: Optional[str] = Query(None, description="Filter by execution location"),
    date_publication_from: Optional[str] = Query(None, description="Filter by publication date from (ISO format)"),
    date_publication_to: Optional[str] = Query(None, description="Filter by publication date to (ISO format)"),
    date_limite_from: Optional[str] = Query(None, description="Filter by deadline from (ISO format)"),
    date_limite_to: Optional[str] = Query(None, description="Filter by deadline to (ISO format)"),
    search: Optional[str] = Query(None, description="Text search in title, buyer, location"),
    sort_field: str = Query("datePublication", description="Sort field"),
    sort_order: int = Query(-1, description="Sort order: 1 for ascending, -1 for descending"),
):
    """Get announcements with pagination and filters"""
    try:
        # Parse dates
        from datetime import datetime
        
        date_publication_from_dt = None
        date_publication_to_dt = None
        date_limite_from_dt = None
        date_limite_to_dt = None
        
        if date_publication_from:
            date_publication_from_dt = datetime.fromisoformat(date_publication_from.replace('Z', '+00:00'))
        if date_publication_to:
            date_publication_to_dt = datetime.fromisoformat(date_publication_to.replace('Z', '+00:00'))
        if date_limite_from:
            date_limite_from_dt = datetime.fromisoformat(date_limite_from.replace('Z', '+00:00'))
        if date_limite_to:
            date_limite_to_dt = datetime.fromisoformat(date_limite_to.replace('Z', '+00:00'))
        
        filters = AnnouncementSearchFilters(
            procedure=procedure,
            categorie=categorie,
            acheteurPublic=acheteur_public,
            lieuExecution=lieu_execution,
            datePublicationFrom=date_publication_from_dt,
            datePublicationTo=date_publication_to_dt,
            dateLimiteFrom=date_limite_from_dt,
            dateLimiteTo=date_limite_to_dt,
            search=search
        )
        
        announcements, total = await AnnouncementService.get_announcements(
            skip=skip,
            limit=limit,
            filters=filters,
            sort_field=sort_field,
            sort_order=sort_order
        )
        
        # Convert to response model
        response_data = [
            AnnouncementResponse(
                **announcement.dict(by_alias=True),
                id=str(announcement.id)
            )
            for announcement in announcements
        ]
        
        # Manual pagination since we already have total count
        return Page.create(
            items=response_data,
            total=total,
            params={"size": limit, "page": skip // limit + 1}
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving announcements"
        )


@router.get("/{announcement_id}", response_model=AnnouncementResponse)
async def get_announcement(announcement_id: str):
    """Get specific announcement by ID"""
    announcement = await AnnouncementService.get_announcement_by_id(announcement_id)
    if not announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found"
        )
    
    return AnnouncementResponse(
        **announcement.dict(by_alias=True),
        id=str(announcement.id)
    )


@router.post("/", response_model=AnnouncementResponse)
async def create_announcement(
    announcement: AnnouncementCreate,
    current_user: UserInDB = Depends(require_admin())
):
    """Create new announcement (Admin only)"""
    try:
        created_announcement = await AnnouncementService.create_announcement(announcement)
        return AnnouncementResponse(
            **created_announcement.dict(by_alias=True),
            id=str(created_announcement.id)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating announcement"
        )


@router.put("/{announcement_id}", response_model=AnnouncementResponse)
async def update_announcement(
    announcement_id: str,
    announcement_update: AnnouncementUpdate,
    current_user: UserInDB = Depends(require_admin())
):
    """Update announcement (Admin only)"""
    updated_announcement = await AnnouncementService.update_announcement(
        announcement_id, announcement_update
    )
    if not updated_announcement:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found"
        )
    
    return AnnouncementResponse(
        **updated_announcement.dict(by_alias=True),
        id=str(updated_announcement.id)
    )


@router.delete("/{announcement_id}")
async def delete_announcement(
    announcement_id: str,
    current_user: UserInDB = Depends(require_admin())
):
    """Delete announcement (Admin only)"""
    deleted = await AnnouncementService.delete_announcement(announcement_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Announcement not found"
        )
    
    return {"message": "Announcement deleted successfully"}


@router.get("/stats/overview", response_model=AnnouncementStats)
async def get_announcement_stats():
    """Get announcement statistics"""
    return await AnnouncementService.get_announcement_stats()


@router.get("/search/text", response_model=List[AnnouncementResponse])
async def search_announcements(
    q: str = Query(..., min_length=3, description="Search query"),
    limit: int = Query(50, ge=1, le=100, description="Maximum results")
):
    """Full text search in announcements"""
    announcements = await AnnouncementService.search_announcements_text(q, limit)
    
    return [
        AnnouncementResponse(
            **announcement.dict(by_alias=True),
            id=str(announcement.id)
        )
        for announcement in announcements
    ]


@router.get("/expiring/soon", response_model=List[AnnouncementResponse])
async def get_expiring_announcements(
    days: int = Query(7, ge=1, le=30, description="Number of days to look ahead")
):
    """Get announcements expiring within specified days"""
    announcements = await AnnouncementService.get_expiring_announcements(days)
    
    return [
        AnnouncementResponse(
            **announcement.dict(by_alias=True),
            id=str(announcement.id)
        )
        for announcement in announcements
    ]
