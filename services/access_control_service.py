#!/usr/bin/env python3
"""
Сервис для проверки детального доступа к разделам документов
"""

import logging
from typing import Dict, List, Optional, Tuple
from config import settings

logger = logging.getLogger(__name__)

class AccessControlService:
    """Сервис для проверки детального доступа к разделам документов"""
    
    def __init__(self):
        self.access_levels = settings.access_levels
        self.detailed_access = settings.detailed_access_levels
    
    def check_section_access(self, subscription_type: str, section: str, 
                           required_access: str = "read_only") -> bool:
        """
        Проверяет доступ пользователя к конкретному разделу
        
        Args:
            subscription_type: Тип подписки пользователя
            section: Раздел документа
            required_access: Требуемый уровень доступа (read_only, full, none)
        
        Returns:
            bool: True если доступ разрешен, False если запрещен
        """
        try:
            if subscription_type not in self.detailed_access:
                logger.warning(f"Неизвестный тип подписки: {subscription_type}")
                return False
            
            user_access = self.detailed_access[subscription_type]
            
            if section not in user_access:
                logger.warning(f"Раздел {section} не найден в правах доступа для {subscription_type}")
                return False
            
            section_access = user_access[section]
            
            # Проверяем уровень доступа
            if section_access == "none":
                return False
            elif section_access == "full":
                return True
            elif section_access == "read_only":
                # read_only разрешает только чтение
                return required_access in ["read_only", "read"]
            else:
                logger.warning(f"Неизвестный уровень доступа: {section_access}")
                return False
                
        except Exception as e:
            logger.error(f"Ошибка при проверке доступа: {e}")
            return False
    
    def get_user_sections(self, subscription_type: str) -> List[str]:
        """
        Возвращает список разделов, к которым у пользователя есть доступ
        
        Args:
            subscription_type: Тип подписки пользователя
        
        Returns:
            List[str]: Список доступных разделов
        """
        return self.access_levels.get(subscription_type, [])
    
    def get_detailed_access_info(self, subscription_type: str) -> Dict[str, str]:
        """
        Возвращает детальную информацию о доступе пользователя
        
        Args:
            subscription_type: Тип подписки пользователя
        
        Returns:
            Dict[str, str]: Детальная информация о доступе по разделам
        """
        return self.detailed_access.get(subscription_type, {})
    
    def can_upload_to_section(self, subscription_type: str, section: str) -> bool:
        """
        Проверяет, может ли пользователь загружать документы в раздел
        
        Args:
            subscription_type: Тип подписки пользователя
            section: Раздел документа
        
        Returns:
            bool: True если загрузка разрешена
        """
        return self.check_section_access(subscription_type, section, "full")
    
    def can_delete_from_section(self, subscription_type: str, section: str) -> bool:
        """
        Проверяет, может ли пользователь удалять документы из раздела
        
        Args:
            subscription_type: Тип подписки пользователя
            section: Раздел документа
        
        Returns:
            bool: True если удаление разрешено
        """
        return self.check_section_access(subscription_type, section, "full")
    
    def can_edit_section(self, subscription_type: str, section: str) -> bool:
        """
        Проверяет, может ли пользователь редактировать документы в разделе
        
        Args:
            subscription_type: Тип подписки пользователя
            section: Раздел документа
        
        Returns:
            bool: True если редактирование разрешено
        """
        return self.check_section_access(subscription_type, section, "full")
    
    def get_access_summary(self, subscription_type: str) -> Dict[str, Dict[str, str]]:
        """
        Возвращает полную сводку по доступу пользователя
        
        Args:
            subscription_type: Тип подписки пользователя
        
        Returns:
            Dict[str, Dict[str, str]]: Сводка по доступу
        """
        if subscription_type not in self.detailed_access:
            return {}
        
        summary = {}
        for section, access_level in self.detailed_access[subscription_type].items():
            summary[section] = {
                "access_level": access_level,
                "can_read": access_level in ["read_only", "full"],
                "can_write": access_level == "full",
                "can_delete": access_level == "full",
                "can_upload": access_level == "full"
            }
        
        return summary

# Global instance
access_control_service = AccessControlService()
