#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Схемы для API управления очисткой кэша
"""

from pydantic import BaseModel, Field
from typing import Dict, Any, Optional, List
from datetime import datetime


class CleanupConfig(BaseModel):
    """Конфигурация очистки для конкретного типа"""
    enabled: bool = Field(..., description="Включена ли очистка")
    interval_hours: int = Field(..., description="Интервал очистки в часах")
    max_age_hours: Optional[int] = Field(None, description="Максимальный возраст файлов в часах")
    max_size_mb: Optional[int] = Field(None, description="Максимальный размер в MB")
    keep_days: Optional[int] = Field(None, description="Количество дней для хранения")


class CleanupStatus(BaseModel):
    """Статус сервиса очистки"""
    is_running: bool = Field(..., description="Запущен ли сервис очистки")
    active_tasks: int = Field(..., description="Количество активных задач")
    last_cleanup: Dict[str, Optional[datetime]] = Field(..., description="Время последней очистки по типам")
    config: Dict[str, CleanupConfig] = Field(..., description="Конфигурация очистки")


class CleanupRequest(BaseModel):
    """Запрос на очистку"""
    task_type: Optional[str] = Field(None, description="Тип очистки (если не указан - очистка всех типов)")
    force: bool = Field(False, description="Принудительная очистка")


class CleanupResponse(BaseModel):
    """Ответ на запрос очистки"""
    success: bool = Field(..., description="Успешность операции")
    message: str = Field(..., description="Сообщение о результате")
    deleted_count: Optional[int] = Field(None, description="Количество удаленных элементов")
    freed_size_mb: Optional[float] = Field(None, description="Освобожденное место в MB")
    task_type: Optional[str] = Field(None, description="Тип выполненной очистки")


class CleanupStats(BaseModel):
    """Статистика очистки"""
    total_deleted_files: int = Field(..., description="Общее количество удаленных файлов")
    total_freed_space_mb: float = Field(..., description="Общее освобожденное место в MB")
    cleanup_history: List[Dict[str, Any]] = Field(..., description="История очистки")


class UpdateCleanupConfigRequest(BaseModel):
    """Запрос на обновление конфигурации очистки"""
    config_updates: Dict[str, CleanupConfig] = Field(..., description="Обновления конфигурации")


class UpdateCleanupConfigResponse(BaseModel):
    """Ответ на обновление конфигурации"""
    success: bool = Field(..., description="Успешность операции")
    message: str = Field(..., description="Сообщение о результате")
    updated_configs: List[str] = Field(..., description="Список обновленных конфигураций")


