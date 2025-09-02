from pydantic import BaseModel, Field
from typing import Optional, List, Dict
from datetime import datetime
from enum import Enum


class AccessLevel(str, Enum):
    RESTAURANT_MANAGEMENT = "restaurant_management"
    KITCHEN_MANAGEMENT = "kitchen_management"
    CONCEPTS_RECIPES = "concepts_recipes"


class AccessTokenCreate(BaseModel):
    name: str = Field(..., description="Token name for identification")
    description: Optional[str] = Field(None, description="Token description")
    access_level: AccessLevel = Field(..., description="Access level for this token")
    allowed_sections: List[str] = Field(..., description="List of allowed document sections")
    rate_limit_per_hour: int = Field(1000, ge=1, le=10000, description="Rate limit per hour")
    expires_at: Optional[datetime] = Field(None, description="Token expiration date")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Kitchen Staff Token",
                "description": "Access token for kitchen management staff",
                "access_level": "kitchen_management",
                "allowed_sections": ["kitchen_ops", "procedures", "guidelines"],
                "rate_limit_per_hour": 500,
                "expires_at": "2024-12-31T23:59:59Z"
            }
        }


class AccessTokenResponse(BaseModel):
    id: int
    token_hash: str
    name: str
    description: Optional[str] = None
    access_level: str
    allowed_sections: List[str]
    is_active: bool
    rate_limit_per_hour: int
    current_usage: int
    created_at: Optional[str] = None
    expires_at: Optional[str] = None
    last_reset: Optional[str] = None  # Make this optional
    
    class Config:
        from_attributes = True


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Username for login")
    email: str = Field(..., description="User email address")
    password: str = Field(..., min_length=6, description="User password")
    subscription_type: AccessLevel = Field(..., description="Subscription type")
    company_name: Optional[str] = Field(None, description="Company name")


class UserLogin(BaseModel):
    username: str = Field(..., description="Username for login")
    password: str = Field(..., description="User password")


class UserInfo(BaseModel):
    id: int
    username: str
    email: str
    subscription_type: str
    company_name: Optional[str] = None
    is_active: bool
    created_at: Optional[str] = None


class AuthResponse(BaseModel):
    message: str
    access_token: str
    refresh_token: str
    user_info: UserInfo


class TokenValidation(BaseModel):
    id: int  # User ID
    is_valid: bool
    access_level: Optional[str] = None
    allowed_sections: Optional[List[str]] = None
    detailed_access: Optional[Dict[str, str]] = None  # Detailed access per section
    rate_limit_exceeded: bool = False
    token_expired: bool = False
    error_message: Optional[str] = None


class TokenUsage(BaseModel):
    token_id: int
    current_usage: int
    rate_limit: int
    usage_percentage: float
    reset_time: datetime
    is_over_limit: bool


class AccessControl(BaseModel):
    token_id: int
    access_level: str
    allowed_sections: List[str]
    permissions: List[str]  # read, search, chat, etc.


class RateLimitInfo(BaseModel):
    token_id: int
    requests_remaining: int
    rate_limit: int
    reset_time: datetime
    current_usage: int


class TokenRefresh(BaseModel):
    token_hash: str
    new_expires_at: Optional[datetime] = None
    extend_by_days: Optional[int] = Field(None, ge=1, le=365, description="Extend token by N days")


class TokenDeactivation(BaseModel):
    token_hash: str
    reason: Optional[str] = Field(None, description="Reason for deactivation")
    deactivate_immediately: bool = Field(True, description="Deactivate immediately or at end of day")
