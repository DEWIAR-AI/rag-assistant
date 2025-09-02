from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime


class ImageContent(BaseModel):
    """Represents an image in a chat message"""
    image_data: str = Field(..., description="Base64 encoded image data")
    image_type: str = Field(..., description="Image MIME type (e.g., image/jpeg, image/png)")
    description: Optional[str] = Field(None, description="Optional description of the image")


class ChatRequest(BaseModel):
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Conversation session ID")
    context: Optional[str] = Field(None, description="Additional user context (legacy field)")
    section: Optional[str] = Field(None, description="Specific section to search in (standards, restaurant_ops, procedures)")
    images: Optional[List[ImageContent]] = Field(None, description="Optional images attached to the message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "What are the safety procedures for handling hot oil?",
                "session_id": "session_123",
                "context": "Kitchen staff training",
                "section": "procedures",
                "images": [
                    {
                        "image_data": "base64_encoded_image_data_here",
                        "image_type": "image/jpeg",
                        "description": "Kitchen safety equipment"
                    }
                ]
            }
        }


class MultimodalChatRequest(BaseModel):
    """Enhanced chat request that supports both text and images"""
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Conversation session ID")
    context: Optional[str] = Field(None, description="Additional user context")
    section: Optional[str] = Field(None, description="Specific section to search in")
    images: Optional[List[ImageContent]] = Field(None, description="Images attached to the message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Что изображено на этой картинке?",
                "session_id": "session_123",
                "section": "restaurant_ops",
                "images": [
                    {
                        "image_data": "base64_encoded_image_data",
                        "image_type": "image/png",
                        "description": "Kitchen layout diagram"
                    }
                ]
            }
        }


class ChatResponse(BaseModel):
    response: str
    session_id: str
    sources: List[Dict[str, Any]]
    context_chunks_used: int
    timestamp: str
    follow_up_questions: Optional[List[str]] = None
    image_analysis: Optional[Dict[str, Any]] = Field(None, description="Analysis results if images were provided")
    response_strategy: Optional[str] = Field(None, description="Strategy used for response generation")
    question_analysis: Optional[Dict[str, Any]] = Field(None, description="Analysis of the question type and characteristics")
    
    class Config:
        json_schema_extra = {
            "example": {
                "response": "Based on the kitchen safety guidelines document...",
                "session_id": "session_123",
                "sources": [
                    {
                        "document_id": 1,
                        "section": "procedures",
                        "page_number": 5,
                        "document_title": "Kitchen Safety Procedures"
                    }
                ],
                "context_chunks_used": 3,
                "timestamp": "2024-01-15T10:30:00Z",
                "follow_up_questions": [
                    "What are the emergency procedures?",
                    "How often should safety training be conducted?"
                ],
                "image_analysis": {
                    "text_extracted": "Safety equipment checklist",
                    "objects_detected": ["fire extinguisher", "first aid kit"],
                    "analysis_confidence": 0.95
                },
                "response_strategy": "hybrid",
                "question_analysis": {
                    "type": "practical",
                    "suggested_strategy": "document_heavy",
                    "is_practical": True
                }
            }
        }


class ConversationCreate(BaseModel):
    title: Optional[str] = Field(None, description="Conversation title")
    user_context: Optional[str] = Field(None, description="User context for the conversation")
    
    class Config:
        json_schema_extra = {
            "example": {
                "title": "Kitchen Safety Discussion",
                "user_context": "Training new kitchen staff on safety procedures"
            }
        }


class ConversationResponse(BaseModel):
    id: int
    session_id: str
    title: Optional[str]
    user_context: Optional[str]
    created_at: datetime
    last_activity: datetime
    message_count: int
    
    class Config:
        from_attributes = True


class ConversationMessage(BaseModel):
    id: int
    conversation_id: int
    role: str  # user, assistant, system
    content: str
    source_chunks: Optional[List[int]] = None
    source_documents: Optional[List[int]] = None
    tokens_used: Optional[int] = None
    processing_time: Optional[float] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class ConversationHistory(BaseModel):
    conversation_id: int
    session_id: str
    title: Optional[str]
    messages: List[ConversationMessage]
    total_messages: int
    created_at: datetime
    last_activity: datetime


class ConversationSummary(BaseModel):
    conversation_id: int
    session_id: str
    title: Optional[str]
    summary: str
    key_topics: List[str]
    total_messages: int
    created_at: datetime


class FollowUpQuestion(BaseModel):
    question: str
    relevance_score: float
    context: str


class ChatAnalytics(BaseModel):
    session_id: str
    total_messages: int
    user_messages: int
    assistant_messages: int
    average_response_time: float
    topics_discussed: List[str]
    documents_referenced: List[int]
    session_duration: float  # in seconds
