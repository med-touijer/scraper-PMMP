from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from pymongo import UpdateOne
from bson import ObjectId
from loguru import logger

from app.db.database import get_announcements_collection
from app.models.announcement import (
    AnnouncementInDB, 
    AnnouncementCreate, 
    AnnouncementUpdate, 
    AnnouncementSearchFilters,
    AnnouncementStats
)


class AnnouncementService:
    
    @staticmethod
    async def create_announcement(announcement_data: AnnouncementCreate) -> AnnouncementInDB:
        """Create new announcement"""
        try:
            collection = await get_announcements_collection()
            
            announcement_dict = announcement_data.dict()
            announcement_dict["createdAt"] = datetime.utcnow()
            announcement_dict["updatedAt"] = datetime.utcnow()
            
            result = await collection.insert_one(announcement_dict)
            announcement_dict["_id"] = result.inserted_id
            
            return AnnouncementInDB(**announcement_dict)
            
        except Exception as e:
            logger.error(f"Error creating announcement: {e}")
            raise
    
    @staticmethod
    async def get_announcement_by_id(announcement_id: str) -> Optional[AnnouncementInDB]:
        """Get announcement by ID"""
        try:
            collection = await get_announcements_collection()
            announcement_data = await collection.find_one({"_id": ObjectId(announcement_id)})
            
            if announcement_data:
                return AnnouncementInDB(**announcement_data)
            return None
            
        except Exception as e:
            logger.error(f"Error getting announcement by ID {announcement_id}: {e}")
            return None
    
    @staticmethod
    async def get_announcements(
        skip: int = 0,
        limit: int = 20,
        filters: Optional[AnnouncementSearchFilters] = None,
        sort_field: str = "datePublication",
        sort_order: int = -1
    ) -> tuple[List[AnnouncementInDB], int]:
        """Get announcements with pagination and filters"""
        try:
            collection = await get_announcements_collection()
            
            # Build query
            query = {}
            
            if filters:
                if filters.procedure:
                    query["procedure"] = {"$regex": filters.procedure, "$options": "i"}
                
                if filters.categorie:
                    query["categorie"] = {"$regex": filters.categorie, "$options": "i"}
                
                if filters.acheteurPublic:
                    query["acheteurPublic"] = {"$regex": filters.acheteurPublic, "$options": "i"}
                
                if filters.lieuExecution:
                    query["lieuExecution"] = {"$regex": filters.lieuExecution, "$options": "i"}
                
                if filters.datePublicationFrom or filters.datePublicationTo:
                    date_query = {}
                    if filters.datePublicationFrom:
                        date_query["$gte"] = filters.datePublicationFrom
                    if filters.datePublicationTo:
                        date_query["$lte"] = filters.datePublicationTo
                    query["datePublication"] = date_query
                
                if filters.dateLimiteFrom or filters.dateLimiteTo:
                    date_query = {}
                    if filters.dateLimiteFrom:
                        date_query["$gte"] = filters.dateLimiteFrom
                    if filters.dateLimiteTo:
                        date_query["$lte"] = filters.dateLimiteTo
                    query["dateLimite"] = date_query
                
                if filters.search:
                    query["$text"] = {"$search": filters.search}
            
            # Get total count
            total = await collection.count_documents(query)
            
            # Get documents with pagination
            cursor = collection.find(query).sort(sort_field, sort_order).skip(skip).limit(limit)
            announcements_data = await cursor.to_list(length=limit)
            
            announcements = [AnnouncementInDB(**data) for data in announcements_data]
            
            return announcements, total
            
        except Exception as e:
            logger.error(f"Error getting announcements: {e}")
            return [], 0
    
    @staticmethod
    async def update_announcement(announcement_id: str, update_data: AnnouncementUpdate) -> Optional[AnnouncementInDB]:
        """Update announcement"""
        try:
            collection = await get_announcements_collection()
            
            update_dict = {k: v for k, v in update_data.dict(exclude_unset=True).items() if v is not None}
            if not update_dict:
                return None
            
            update_dict["updatedAt"] = datetime.utcnow()
            
            result = await collection.update_one(
                {"_id": ObjectId(announcement_id)},
                {"$set": update_dict}
            )
            
            if result.matched_count:
                return await AnnouncementService.get_announcement_by_id(announcement_id)
            return None
            
        except Exception as e:
            logger.error(f"Error updating announcement {announcement_id}: {e}")
            return None
    
    @staticmethod
    async def delete_announcement(announcement_id: str) -> bool:
        """Delete announcement"""
        try:
            collection = await get_announcements_collection()
            result = await collection.delete_one({"_id": ObjectId(announcement_id)})
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error deleting announcement {announcement_id}: {e}")
            return False
    
    @staticmethod
    async def bulk_upsert_announcements(announcements: List[dict]) -> int:
        """Bulk insert/update announcements from scraper"""
        try:
            if not announcements:
                return 0
                
            collection = await get_announcements_collection()
            operations = []
            
            for ann_data in announcements:
                # Build query for upsert
                query = {}
                if ann_data.get("lienDeConsultation") and ann_data["lienDeConsultation"] != "N/A":
                    query = {"lienDeConsultation": ann_data["lienDeConsultation"]}
                elif ann_data.get("reference") and ann_data["reference"] != "N/A":
                    query = {
                        "reference": ann_data["reference"],
                        "datePublication": ann_data.get("datePublication")
                    }
                else:
                    # Fallback: insert directly if no unique identifier
                    ann_data["createdAt"] = datetime.utcnow()
                    ann_data["updatedAt"] = datetime.utcnow()
                    operations.append(ann_data)
                    continue
                
                # Prepare upsert data
                ann_data["updatedAt"] = datetime.utcnow()
                if "createdAt" not in ann_data:
                    ann_data["createdAt"] = datetime.utcnow()
                
                operations.append(
                    UpdateOne(
                        query,
                        {"$set": ann_data, "$setOnInsert": {"createdAt": datetime.utcnow()}},
                        upsert=True
                    )
                )
            
            # Separate bulk operations from direct inserts
            bulk_ops = [op for op in operations if hasattr(op, 'upsert')]
            direct_inserts = [op for op in operations if not hasattr(op, 'upsert')]
            
            inserted_count = 0
            
            if bulk_ops:
                result = await collection.bulk_write(bulk_ops, ordered=False)
                inserted_count += getattr(result, 'upserted_count', 0) + getattr(result, 'inserted_count', 0)
            
            if direct_inserts:
                result = await collection.insert_many(direct_inserts)
                inserted_count += len(result.inserted_ids)
            
            return inserted_count
            
        except Exception as e:
            logger.error(f"Error in bulk upsert: {e}")
            return 0
    
    @staticmethod
    async def get_announcement_stats() -> AnnouncementStats:
        """Get announcement statistics"""
        try:
            collection = await get_announcements_collection()
            
            # Total count
            total = await collection.count_documents({})
            
            # Stats by procedure
            procedure_pipeline = [
                {"$group": {"_id": "$procedure", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            procedure_stats = {}
            async for doc in collection.aggregate(procedure_pipeline):
                procedure_stats[doc["_id"]] = doc["count"]
            
            # Stats by category
            category_pipeline = [
                {"$group": {"_id": "$categorie", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}}
            ]
            category_stats = {}
            async for doc in collection.aggregate(category_pipeline):
                category_stats[doc["_id"]] = doc["count"]
            
            # Recent announcements (last 7 days)
            week_ago = datetime.utcnow() - timedelta(days=7)
            recent_count = await collection.count_documents({
                "datePublication": {"$gte": week_ago}
            })
            
            # Average per day (last 30 days)
            month_ago = datetime.utcnow() - timedelta(days=30)
            monthly_count = await collection.count_documents({
                "datePublication": {"$gte": month_ago}
            })
            avg_per_day = monthly_count / 30.0
            
            return AnnouncementStats(
                totalAnnouncements=total,
                byProcedure=procedure_stats,
                byCategorie=category_stats,
                recentAnnouncements=recent_count,
                avgPerDay=round(avg_per_day, 2)
            )
            
        except Exception as e:
            logger.error(f"Error getting announcement stats: {e}")
            return AnnouncementStats(
                totalAnnouncements=0,
                byProcedure={},
                byCategorie={},
                recentAnnouncements=0,
                avgPerDay=0.0
            )
    
    @staticmethod
    async def search_announcements_text(query: str, limit: int = 50) -> List[AnnouncementInDB]:
        """Full text search in announcements"""
        try:
            collection = await get_announcements_collection()
            
            # Text search
            cursor = collection.find(
                {"$text": {"$search": query}},
                {"score": {"$meta": "textScore"}}
            ).sort([("score", {"$meta": "textScore"})]).limit(limit)
            
            announcements_data = await cursor.to_list(length=limit)
            return [AnnouncementInDB(**data) for data in announcements_data]
            
        except Exception as e:
            logger.error(f"Error in text search: {e}")
            return []
    
    @staticmethod
    async def get_expiring_announcements(days: int = 7) -> List[AnnouncementInDB]:
        """Get announcements expiring within specified days"""
        try:
            collection = await get_announcements_collection()
            
            future_date = datetime.utcnow() + timedelta(days=days)
            
            cursor = collection.find({
                "dateLimite": {
                    "$gte": datetime.utcnow(),
                    "$lte": future_date
                }
            }).sort("dateLimite", 1)
            
            announcements_data = await cursor.to_list(length=None)
            return [AnnouncementInDB(**data) for data in announcements_data]
            
        except Exception as e:
            logger.error(f"Error getting expiring announcements: {e}")
            return []
