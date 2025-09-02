#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Зависимости аутентификации для избежания циклических импортов
"""

from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
import logging

from schemas import TokenValidation
from services.user_auth_service import user_auth_service
from services.rate_limiter import check_rate_limit_middleware

logger = logging.getLogger(__name__)

# Security
security = HTTPBearer()


async def get_current_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> TokenValidation:
    """Validate JWT access token"""
    try:
        token = credentials.credentials
        
        # Validate JWT token using user auth service
        token_data = user_auth_service.validate_token(token)
        
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный или просроченный токен доступа"
            )
        
        # Check rate limit
        try:
            check_rate_limit_middleware(str(token_data['user_id']), token_data['subscription_type'])
        except HTTPException as e:
            raise e
        
        return TokenValidation(
            id=token_data['user_id'],
            is_valid=token_data['is_valid'],
            access_level=token_data['subscription_type'],
            allowed_sections=token_data['allowed_sections'],
            detailed_access=token_data.get('detailed_access'),
            rate_limit_exceeded=False,
            token_expired=False
        )
        
    except Exception as e:
        logger.error(f"Проверка токена не удалась: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен доступа"
        )


async def get_admin_token(admin_token: str = Depends(HTTPBearer())):
    """Validate admin token"""
    try:
        token = admin_token.credentials
        
        # Validate admin token
        token_data = user_auth_service.validate_token(token)
        
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный или просроченный токен администратора"
            )
        
        # Check if user is admin
        if token_data.get('subscription_type') != 'admin':
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Доступ только для администраторов"
            )
        
        return token_data
        
    except Exception as e:
        logger.error(f"Проверка токена администратора не удалась: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный токен администратора"
        )


