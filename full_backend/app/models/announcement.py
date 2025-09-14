from typing import List, Optional, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
from bson import ObjectId
from enum import Enum


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")


class ProcedureType(str, Enum):
    AO = "AO"  # Appel d'offres
    AOO = "AOO"  # Appel d'offres ouvert
    AOR = "AOR"  # Appel d'offres restreint
    CC = "CC"   # Concours
    MA = "MA"   # Marché négocié


class AnnouncementBase(BaseModel):
    procedure: str = Field(default="N/A", description="Type de procédure (AO, AOO, etc.)")
    categorie: str = Field(default="N/A", description="Catégorie de l'annonce")
    reference: str = Field(default="N/A", description="Référence de l'annonce")
    objet: str = Field(default="N/A", description="Objet du marché")
    acheteurPublic: str = Field(default="N/A", description="Acheteur public")
    lots: str = Field(default="-", description="Information sur les lots")
    lieuExecution: str = Field(default="N/A", description="Lieu d'exécution")
    lienDeConsultation: str = Field(default="N/A", description="Lien de consultation")
    piecesJointes: List[str] = Field(default_factory=list, description="Liste des pièces jointes")
    datePublication: Optional[datetime] = Field(None, description="Date de publication")
    dateLimite: Optional[datetime] = Field(None, description="Date limite de soumission")


class AnnouncementCreate(AnnouncementBase):
    pass


class AnnouncementUpdate(BaseModel):
    procedure: Optional[str] = None
    categorie: Optional[str] = None
    reference: Optional[str] = None
    objet: Optional[str] = None
    acheteurPublic: Optional[str] = None
    lots: Optional[str] = None
    lieuExecution: Optional[str] = None
    lienDeConsultation: Optional[str] = None
    piecesJointes: Optional[List[str]] = None
    datePublication: Optional[datetime] = None
    dateLimite: Optional[datetime] = None


class AnnouncementInDB(AnnouncementBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    updatedAt: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class AnnouncementResponse(AnnouncementBase):
    id: str = Field(alias="_id")
    createdAt: datetime
    updatedAt: datetime
    
    @validator('id', pre=True)
    def validate_id(cls, v):
        return str(v)
    
    class Config:
        allow_population_by_field_name = True


class AnnouncementSearchFilters(BaseModel):
    procedure: Optional[str] = None
    categorie: Optional[str] = None
    acheteurPublic: Optional[str] = None
    lieuExecution: Optional[str] = None
    datePublicationFrom: Optional[datetime] = None
    datePublicationTo: Optional[datetime] = None
    dateLimiteFrom: Optional[datetime] = None
    dateLimiteTo: Optional[datetime] = None
    search: Optional[str] = Field(None, description="Recherche textuelle dans objet, acheteur, lieu")


class AnnouncementStats(BaseModel):
    totalAnnouncements: int
    byProcedure: dict
    byCategorie: dict
    recentAnnouncements: int
    avgPerDay: float


class ScraperStatus(BaseModel):
    isRunning: bool
    lastRun: Optional[datetime]
    nextRun: Optional[datetime]
    lastScrapedPages: int
    totalAnnouncementsScraped: int
    errors: List[str]


class ScraperConfig(BaseModel):
    maxPages: Optional[int] = Field(None, description="Nombre maximum de pages à scraper")
    startPage: int = Field(1, description="Page de début")
    delayBetweenRequests: int = Field(2, description="Délai entre les requêtes (secondes)")
    enabled: bool = Field(True, description="Activer/désactiver le scraper")


# User Models for Authentication
class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    VIEWER = "viewer"


class UserBase(BaseModel):
    email: str
    fullName: str
    role: UserRole = UserRole.VIEWER
    isActive: bool = True


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    email: Optional[str] = None
    fullName: Optional[str] = None
    role: Optional[UserRole] = None
    isActive: Optional[bool] = None
    password: Optional[str] = None


class UserInDB(UserBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    hashedPassword: str
    createdAt: datetime = Field(default_factory=datetime.utcnow)
    lastLogin: Optional[datetime] = None
    
    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


class UserResponse(UserBase):
    id: str = Field(alias="_id")
    createdAt: datetime
    lastLogin: Optional[datetime]
    
    @validator('id', pre=True)
    def validate_id(cls, v):
        return str(v)
    
    class Config:
        allow_population_by_field_name = True


class Token(BaseModel):
    accessToken: str
    refreshToken: str
    tokenType: str = "bearer"
    expiresIn: int


class TokenData(BaseModel):
    userId: Optional[str] = None
    email: Optional[str] = None
    role: Optional[UserRole] = None
