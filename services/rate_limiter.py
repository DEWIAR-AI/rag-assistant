import time
import logging
from typing import Dict, Optional
from fastapi import HTTPException, status
from config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter for API endpoints"""
    
    def __init__(self):
        self.requests: Dict[str, Dict[str, any]] = {}
        self.cleanup_interval = 3600  # 1 hour in seconds
    
    def _cleanup_old_requests(self):
        """Clean up old request records"""
        current_time = time.time()
        expired_tokens = []
        
        for token_id, data in self.requests.items():
            if current_time - data['last_reset'] > self.cleanup_interval:
                expired_tokens.append(token_id)
        
        for token_id in expired_tokens:
            del self.requests[token_id]
    
    def check_rate_limit(self, token_id: str, access_level: str) -> bool:
        """Check if request is within rate limit"""
        if not settings.enable_rate_limiting:
            return True
        
        current_time = time.time()
        
        # Clean up old records periodically
        if current_time % 60 < 1:  # Every minute
            self._cleanup_old_requests()
        
        # Get rate limit for access level
        base_limit = settings.rate_limit_per_hour
        
        # Adjust limits based on access level
        if access_level == "restaurant_management":
            limit = base_limit * 2  # Higher limit for admin users
        elif access_level == "kitchen_management":
            limit = base_limit
        else:  # concepts_recipes
            limit = base_limit // 2  # Lower limit for basic users
        
        # Initialize or get token data
        if token_id not in self.requests:
            self.requests[token_id] = {
                'count': 0,
                'last_reset': current_time,
                'access_level': access_level
            }
        
        token_data = self.requests[token_id]
        
        # Reset counter if hour has passed
        if current_time - token_data['last_reset'] >= self.cleanup_interval:
            token_data['count'] = 0
            token_data['last_reset'] = current_time
            token_data['access_level'] = access_level
        
        # Check if limit exceeded
        if token_data['count'] >= limit:
            logger.warning(f"Rate limit exceeded for token {token_id[:8]}... (access_level: {access_level})")
            return False
        
        # Increment counter
        token_data['count'] += 1
        
        return True
    
    def get_remaining_requests(self, token_id: str) -> Optional[int]:
        """Get remaining requests for a token"""
        if token_id not in self.requests:
            return None
        
        token_data = self.requests[token_id]
        current_time = time.time()
        
        # Reset counter if hour has passed
        if current_time - token_data['last_reset'] >= self.cleanup_interval:
            return self._get_limit_for_access_level(token_data['access_level'])
        
        limit = self._get_limit_for_access_level(token_data['access_level'])
        return max(0, limit - token_data['count'])
    
    def _get_limit_for_access_level(self, access_level: str) -> int:
        """Get rate limit for specific access level"""
        base_limit = settings.rate_limit_per_hour
        
        if access_level == "restaurant_management":
            return base_limit * 2
        elif access_level == "kitchen_management":
            return base_limit
        else:  # concepts_recipes
            return base_limit // 2


# Global rate limiter instance
rate_limiter = RateLimiter()


def check_rate_limit_middleware(token_id: str, access_level: str):
    """Middleware function to check rate limit"""
    if not rate_limiter.check_rate_limit(token_id, access_level):
        remaining = rate_limiter.get_remaining_requests(token_id)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "message": f"Too many requests. Limit: {rate_limiter._get_limit_for_access_level(access_level)} per hour",
                "retry_after": 3600,  # 1 hour
                "remaining_requests": remaining
            }
        )
