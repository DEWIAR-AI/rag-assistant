from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DocumentSection(str, Enum):
    RESTAURANT_OPS = "restaurant_ops"
    KITCHEN_OPS = "kitchen_ops"
    RECIPES = "recipes"
    CONCEPTS = "concepts"
    STANDARDS = "standards"
    PROCEDURES = "procedures"
    GUIDELINES = "guidelines"
    INGREDIENTS = "ingredients"


class AccessLevel(str, Enum):
    RESTAURANT_MANAGEMENT = "restaurant_management"
    KITCHEN_MANAGEMENT = "kitchen_management"
    CONCEPTS_RECIPES = "concepts_recipes"


class DocumentCreate(BaseModel):
    title: Optional[str] = Field(None, description="Document title")
    description: Optional[str] = Field(None, description="Document description")
    section: DocumentSection = Field(..., description="Document section/category")
    access_level: AccessLevel = Field(..., description="Required access level to view document")
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Kitchen Safety Guidelines",
                "description": "Comprehensive safety procedures for kitchen staff",
                "section": "kitchen_ops",
                "access_level": "kitchen_management"
            }
        }


class DocumentResponse(BaseModel):
    id: int
    filename: str
    original_filename: str
    file_path: str
    file_size: int
    file_type: str
    mime_type: str
    title: Optional[str]
    description: Optional[str]
    section: str
    access_level: str
    is_processed: bool
    processing_error: Optional[str] = None
    has_images: bool
    text_content: Optional[str] = None
    extracted_metadata: Optional[Dict[str, Any]] = None
    uploaded_at: datetime
    processed_at: Optional[datetime]
    
    class Config:
        from_attributes = True


class DocumentList(BaseModel):
    documents: List[DocumentResponse]
    total: int
    page: int
    per_page: int
    total_pages: int


class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    section: Optional[DocumentSection] = None
    access_level: Optional[AccessLevel] = None


class DocumentChunkResponse(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    content: str
    content_length: int
    embedding_id: Optional[str]
    page_number: Optional[int]
    section_name: Optional[str]
    chunk_type: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True


class DocumentSearchResult(BaseModel):
    document_id: int
    chunk_id: int
    content: str
    score: float
    section: str
    access_level: str
    chunk_type: Optional[str]
    page_number: Optional[int]
    section_name: Optional[str]
    metadata: Optional[Dict[str, Any]]
    
    class Config:
        from_attributes = True


class DocumentProcessingStatus(BaseModel):
    document_id: int
    status: str  # processing, completed, failed
    progress: float  # 0.0 to 1.0
    message: str
    error: Optional[str] = None


class FileUploadResponse(BaseModel):
    success: bool
    document_id: Optional[int] = None
    filename: Optional[str] = None
    message: str
    processing_status: Optional[DocumentProcessingStatus] = None


class DocumentSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    section: Optional[DocumentSection] = Field(None, description="Filter by document section")
    access_level: Optional[AccessLevel] = Field(None, description="Filter by access level")
    limit: int = Field(10, ge=1, le=100, description="Maximum number of results")
    score_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Minimum similarity score")
    strict_section_search: bool = Field(False, description="If True, search only in specified section without fallback")


class DocumentSearchResult(BaseModel):
    document_id: int
    chunk_id: int
    content: str
    score: float
    section: str
    access_level: str
    chunk_type: Optional[str]
    page_number: Optional[int]
    section_name: Optional[str]
    metadata: Optional[Dict[str, Any]]
