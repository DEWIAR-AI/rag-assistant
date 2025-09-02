#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис аутентификации пользователей с RBAC
"""

import hashlib
import secrets
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import User, UserRole
from config import settings
import jwt

logger = logging.getLogger(__name__)


class UserAuthService:
    """Сервис аутентификации пользователей с ролевым доступом"""
    
    def __init__(self):
        self.secret_key = settings.jwt_secret_key
        self.algorithm = "HS256"
        self.access_token_expire_minutes = 30
        self.refresh_token_expire_days = 7
    
    def register_user(self, username: str, email: str, password: str, 
                     subscription_type: str, company_name: str = None) -> Dict[str, Any]:
        """Регистрация нового пользователя"""
        try:
            # Проверяем, что subscription_type валиден
            if subscription_type not in settings.access_levels:
                raise ValueError(f"Неверный тип подписки: {subscription_type}")
            
            db = next(get_db())
            try:
                # Проверяем, что пользователь не существует
                existing_user = db.query(User).filter(
                    (User.username == username) | (User.email == email)
                ).first()
                
                if existing_user:
                    raise ValueError("Пользователь с таким именем или email уже существует")
                
                # Хешируем пароль
                password_hash = self._hash_password(password)
                
                # Создаем пользователя
                user = User(
                    username=username,
                    email=email,
                    password_hash=password_hash,
                    subscription_type=subscription_type,
                    company_name=company_name,
                    is_active=True,
                    created_at=datetime.now(timezone.utc)
                )
                
                db.add(user)
                db.commit()
                db.refresh(user)
                
                # Создаем роль пользователя
                logger.info(f"Создаем роль для пользователя {username} с типами: {settings.access_levels}")
                
                # Получаем разрешенные разделы из основной конфигурации
                allowed_sections = settings.access_levels[subscription_type]
                
                # Создаем детальную информацию о доступе
                detailed_access = settings.detailed_access_levels[subscription_type]
                
                user_role = UserRole(
                    user_id=user.id,
                    role_name=subscription_type,
                    allowed_sections=allowed_sections,
                    detailed_access=detailed_access,  # Добавляем детальный доступ
                    created_at=datetime.now(timezone.utc)
                )
                
                db.add(user_role)
                db.commit()
                
                logger.info(f"Зарегистрирован новый пользователь: {username} с подпиской {subscription_type}")
                logger.info(f"Роль создана: {user_role.id}, разрешенные разделы: {user_role.allowed_sections}")
                
                return {
                    'success': True,
                    'user_id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'subscription_type': subscription_type,
                    'company_name': user.company_name,
                    'message': 'Пользователь успешно зарегистрирован'
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка при регистрации пользователя: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def authenticate_user(self, username: str, password: str) -> Dict[str, Any]:
        """Аутентификация пользователя"""
        try:
            db = next(get_db())
            try:
                # Ищем пользователя
                user = db.query(User).filter(User.username == username).first()
                
                if not user:
                    return {
                        'success': False,
                        'error': 'Неверное имя пользователя или пароль'
                    }
                
                if not user.is_active:
                    return {
                        'success': False,
                        'error': 'Аккаунт заблокирован'
                    }
                
                # Проверяем пароль
                if not self._verify_password(password, user.password_hash):
                    return {
                        'success': False,
                        'error': 'Неверное имя пользователя или пароль'
                    }
                
                # Получаем роль пользователя
                logger.info(f"Ищем роль для пользователя {username} (ID: {user.id})")
                user_role = db.query(UserRole).filter(UserRole.user_id == user.id).first()
                
                if not user_role:
                    logger.error(f"Роль не найдена для пользователя {username}")
                    return {
                        'success': False,
                        'error': 'Роль пользователя не найдена'
                    }
                
                logger.info(f"Роль найдена: {user_role.role_name}, разделы: {user_role.allowed_sections}")
                
                # Создаем JWT токены
                access_token = self._create_access_token(
                    user_id=user.id,
                    username=user.username,
                    subscription_type=user.subscription_type,
                    allowed_sections=user_role.allowed_sections
                )
                
                refresh_token = self._create_refresh_token(user.id)
                
                logger.info(f"Пользователь {username} успешно аутентифицирован")
                
                return {
                    'success': True,
                    'access_token': access_token,
                    'refresh_token': refresh_token,
                    'user_info': {
                        'id': user.id,
                        'username': user.username,
                        'email': user.email,
                        'subscription_type': user.subscription_type,
                        'company_name': user.company_name,
                        'is_active': user.is_active,
                        'created_at': user.created_at.isoformat() if user.created_at else None
                    }
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка при аутентификации: {e}")
            return {
                'success': False,
                'error': 'Внутренняя ошибка сервера'
            }
    
    def validate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Валидация JWT токена"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            
            # Проверяем срок действия - исправляем проблему с часовыми поясами
            exp_timestamp = payload['exp']
            current_timestamp = int(datetime.now(timezone.utc).timestamp())
            
            if exp_timestamp < current_timestamp:
                return None
            
            # Import access control service
            from services.access_control_service import access_control_service
            
            # Get detailed access information
            detailed_access = access_control_service.get_detailed_access_info(payload['subscription_type'])
            
            return {
                'is_valid': True,
                'user_id': payload['user_id'],
                'username': payload['username'],
                'subscription_type': payload['subscription_type'],
                'allowed_sections': payload['allowed_sections'],
                'detailed_access': detailed_access,
                'exp': payload['exp']
            }
            
        except jwt.ExpiredSignatureError:
            logger.warning("Токен истек")
            return None
        except jwt.InvalidTokenError:
            logger.warning("Неверный токен")
            return None
        except Exception as e:
            logger.error(f"Ошибка при валидации токена: {e}")
            return None
    
    def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Обновление access токена"""
        try:
            payload = jwt.decode(refresh_token, self.secret_key, algorithms=[self.algorithm])
            
            # Проверяем срок действия - исправляем проблему с часовыми поясами
            exp_timestamp = payload['exp']
            current_timestamp = int(datetime.now(timezone.utc).timestamp())
            
            if exp_timestamp < current_timestamp:
                return {
                    'success': False,
                    'error': 'Refresh токен истек'
                }
            
            # Получаем актуальную информацию о пользователе
            db = next(get_db())
            try:
                user = db.query(User).filter(User.id == payload['user_id']).first()
                user_role = db.query(UserRole).filter(UserRole.user_id == user.id).first()
                
                if not user or not user_role or not user.is_active:
                    return {
                        'success': False,
                        'error': 'Пользователь не найден или заблокирован'
                    }
                
                # Создаем новый access токен
                new_access_token = self._create_access_token(
                    user_id=user.id,
                    username=user.username,
                    subscription_type=user.subscription_type,
                    allowed_sections=user_role.allowed_sections
                )
                
                return {
                    'success': True,
                    'access_token': new_access_token
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка при обновлении токена: {e}")
            return {
                'success': False,
                'error': 'Ошибка при обновлении токена'
            }
    
    def _hash_password(self, password: str) -> str:
        """Хеширование пароля"""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Проверка пароля"""
        return self._hash_password(password) == password_hash
    
    def _create_access_token(self, user_id: int, username: str, 
                           subscription_type: str, allowed_sections: List[str]) -> str:
        """Создание JWT access токена"""
        expire = datetime.now(timezone.utc) + timedelta(minutes=self.access_token_expire_minutes)
        
        # Import access control service
        from services.access_control_service import access_control_service
        
        # Get detailed access information
        detailed_access = access_control_service.get_detailed_access_info(subscription_type)
        
        payload = {
            'user_id': user_id,
            'username': username,
            'subscription_type': subscription_type,
            'allowed_sections': allowed_sections,
            'detailed_access': detailed_access,
            'exp': int(expire.timestamp())
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def _create_refresh_token(self, user_id: int) -> str:
        """Создание JWT refresh токена"""
        expire = datetime.now(timezone.utc) + timedelta(days=self.refresh_token_expire_days)
        
        payload = {
            'user_id': user_id,
            'exp': int(expire.timestamp())
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)


# Global instance
user_auth_service = UserAuthService()



