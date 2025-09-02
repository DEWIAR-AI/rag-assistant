import hashlib
import secrets
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from database.database import get_db
from database.models import AccessToken

logger = logging.getLogger(__name__)


class AuthService:
    def __init__(self):
        self.token_cache = {}
    
    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate an access token"""
        try:
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            
            db = next(get_db())
            try:
                access_token = db.query(AccessToken).filter(
                    AccessToken.token_hash == token_hash,
                    AccessToken.is_active == True
                ).first()
                
                if not access_token:
                    return None
                
                if access_token.expires_at and datetime.now() > access_token.expires_at:
                    return None
                
                return {
                    'is_valid': True,
                    'id': access_token.id,  # Add the token ID
                    'access_level': access_token.access_level,
                    'allowed_sections': access_token.allowed_sections,
                    'rate_limit_exceeded': False,
                    'token_expired': False,
                    'token_id': access_token.id
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error validating token: {e}")
            return None
    
    def validate_access(self, token_data: Dict[str, Any], 
                       required_section: str, 
                       required_access_level: Optional[str] = None) -> bool:
        """Validate if token has access to specific section and level"""
        try:
            if not token_data.get('is_valid'):
                return False
            
            if required_access_level and token_data.get('access_level') != required_access_level:
                return False
            
            allowed_sections = token_data.get('allowed_sections', [])
            if required_section not in allowed_sections:
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error validating access: {e}")
            return False


# Global instance
auth_service = AuthService()
