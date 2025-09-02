import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from database.database import get_db
from database.models import AccessToken
from config import settings
import hashlib
import secrets

logger = logging.getLogger(__name__)


class AdminService:
    """Handles admin operations and authentication"""
    
    def __init__(self):
        # In production, this should be stored securely (e.g., environment variables)
        self.admin_tokens = {
            "admin_master": "admin_secret_key_2024",
            "supervisor": "supervisor_key_2024"
        }
    
    def validate_admin_token(self, admin_token: str) -> bool:
        """Validate admin authentication token"""
        return admin_token in self.admin_tokens.values()
    
    def create_access_token(self, name: str, description: str, access_level: str,
                           allowed_sections: List[str], rate_limit_per_hour: int = 1000,
                           expires_at: Optional[datetime] = None) -> Dict[str, Any]:
        """Create a new access token with enhanced validation"""
        try:
            # Validate access level and sections
            if access_level not in settings.access_levels:
                raise ValueError(f"Invalid access level: {access_level}. Must be one of: {list(settings.access_levels.keys())}")
            
            # Validate allowed sections based on access level
            valid_sections = settings.access_levels.get(access_level, [])
            invalid_sections = [s for s in allowed_sections if s not in valid_sections]
            if invalid_sections:
                raise ValueError(f"Invalid sections for {access_level}: {invalid_sections}. Valid sections: {valid_sections}")
            
            # Generate unique token and hash
            actual_token, token_hash = self._generate_token_hash()
            
            db = next(get_db())
            try:
                access_token = AccessToken(
                    token_hash=token_hash,
                    name=name,
                    description=description,
                    access_level=access_level,
                    allowed_sections=allowed_sections,
                    rate_limit_per_hour=rate_limit_per_hour,
                    expires_at=expires_at,
                    created_at=datetime.now(),
                    last_reset=datetime.now()
                )
                
                db.add(access_token)
                db.commit()
                db.refresh(access_token)
                
                logger.info(f"Created access token {access_token.id} for {name} with access level {access_level}")
                
                # Return both the actual token and the database record
                return {
                    'actual_token': actual_token,
                    'token_hash': token_hash,
                    'access_token': access_token
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error creating access token: {e}")
            raise
    
    def create_bulk_tokens(self, token_configs: List[Dict[str, Any]]) -> List[AccessToken]:
        """Create multiple access tokens for bulk operations"""
        created_tokens = []
        
        for config in token_configs:
            try:
                token = self.create_access_token(
                    name=config['name'],
                    description=config.get('description', ''),
                    access_level=config['access_level'],
                    allowed_sections=config['allowed_sections'],
                    rate_limit_per_hour=config.get('rate_limit_per_hour', 1000),
                    expires_at=config.get('expires_at')
                )
                created_tokens.append(token)
            except Exception as e:
                logger.error(f"Failed to create token for {config.get('name', 'Unknown')}: {e}")
                continue
        
        return created_tokens
    
    def get_token_analytics(self) -> Dict[str, Any]:
        """Get comprehensive token analytics"""
        try:
            db = next(get_db())
            try:
                # Get total tokens by access level
                total_tokens = db.query(AccessToken).count()
                active_tokens = db.query(AccessToken).filter(AccessToken.is_active == True).count()
                
                # Get usage statistics
                total_usage = db.query(AccessToken).with_entities(
                    func.sum(AccessToken.current_usage)
                ).scalar() or 0
                
                # Get tokens by access level
                tokens_by_level = {}
                for level in settings.access_levels.keys():
                    count = db.query(AccessToken).filter(
                        AccessToken.access_level == level
                    ).count()
                    tokens_by_level[level] = count
                
                return {
                    'total_tokens': total_tokens,
                    'active_tokens': active_tokens,
                    'inactive_tokens': total_tokens - active_tokens,
                    'total_usage': total_usage,
                    'tokens_by_access_level': tokens_by_level,
                    'access_levels': list(settings.access_levels.keys())
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error getting token analytics: {e}")
            return {}
    
    def _generate_token_hash(self) -> tuple[str, str]:
        """Generate a unique token and its hash"""
        # Generate a random token
        actual_token = secrets.token_urlsafe(32)
        # Hash it for storage
        token_hash = hashlib.sha256(actual_token.encode()).hexdigest()
        return actual_token, token_hash
    
    def list_access_tokens(self) -> List[AccessToken]:
        """List all access tokens"""
        try:
            db = next(get_db())
            try:
                tokens = db.query(AccessToken).order_by(AccessToken.created_at.desc()).all()
                return tokens
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error listing access tokens: {e}")
            return []
    
    def get_access_token(self, token_id: int) -> Optional[AccessToken]:
        """Get access token by ID"""
        try:
            db = next(get_db())
            try:
                return db.query(AccessToken).filter(AccessToken.id == token_id).first()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error getting access token {token_id}: {e}")
            return None
    
    def update_access_token(self, token_id: int, **kwargs) -> bool:
        """Update access token"""
        try:
            db = next(get_db())
            try:
                token = db.query(AccessToken).filter(AccessToken.id == token_id).first()
                if not token:
                    return False
                
                # Update allowed fields
                allowed_fields = ['name', 'description', 'allowed_sections', 
                                'rate_limit_per_hour', 'is_active', 'expires_at']
                
                for field, value in kwargs.items():
                    if field in allowed_fields and hasattr(token, field):
                        setattr(token, field, value)
                
                db.commit()
                logger.info(f"Updated access token {token_id}")
                return True
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error updating access token {token_id}: {e}")
            return False
    
    def delete_access_token(self, token_id: int) -> bool:
        """Delete access token"""
        try:
            db = next(get_db())
            try:
                result = db.query(AccessToken).filter(AccessToken.id == token_id).delete()
                db.commit()
                
                if result > 0:
                    logger.info(f"Deleted access token {token_id}")
                    return True
                return False
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error deleting access token {token_id}: {e}")
            return False
    
    def deactivate_token(self, token_id: int) -> bool:
        """Deactivate an access token"""
        return self.update_access_token(token_id, is_active=False)
    
    def reactivate_token(self, token_id: int) -> bool:
        """Reactivate an access token"""
        return self.update_access_token(token_id, is_active=True)
    
    def get_token_usage_stats(self, token_id: int) -> Dict[str, Any]:
        """Get usage statistics for a token"""
        try:
            db = next(get_db())
            try:
                token = db.query(AccessToken).filter(AccessToken.id == token_id).first()
                if not token:
                    return {}
                
                # Calculate usage statistics
                current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
                if token.last_reset and token.last_reset < current_hour:
                    # Reset usage counter
                    token.current_usage = 0
                    token.last_reset = current_hour
                    db.commit()
                
                return {
                    'token_id': token.id,
                    'name': token.name,
                    'current_usage': token.current_usage,
                    'rate_limit': token.rate_limit_per_hour,
                    'usage_percentage': (token.current_usage / token.rate_limit_per_hour) * 100,
                    'last_reset': token.last_reset.isoformat() if token.last_reset else None,
                    'is_active': token.is_active,
                    'expires_at': token.expires_at.isoformat() if token.expires_at else None
                }
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error getting token usage stats {token_id}: {e}")
            return {}
    
    def increment_token_usage(self, token_hash: str) -> bool:
        """Increment usage counter for a token"""
        try:
            db = next(get_db())
            try:
                token = db.query(AccessToken).filter(AccessToken.token_hash == token_hash).first()
                if not token:
                    return False
                
                # Check if we need to reset the counter
                current_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
                if token.last_reset and token.last_reset < current_hour:
                    token.current_usage = 1
                    token.last_reset = current_hour
                else:
                    token.current_usage += 1
                
                db.commit()
                return True
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error incrementing token usage: {e}")
            return False


# Global instance
admin_service = AdminService()
