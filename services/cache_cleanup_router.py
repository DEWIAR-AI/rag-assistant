#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Роутер для API управления очисткой кэша
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from typing import Dict, Any
import logging

from schemas.cache_cleanup import (
    CleanupStatus, CleanupRequest, CleanupResponse,
    UpdateCleanupConfigRequest, UpdateCleanupConfigResponse
)
from services.cache_cleanup_service import cache_cleanup_service
from services.auth_dependencies import get_current_token
from schemas import TokenValidation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cache", tags=["cache-cleanup"])


@router.get("/status", response_model=CleanupStatus)
async def get_cleanup_status(token: TokenValidation = Depends(get_current_token)):
    """Получить статус сервиса очистки кэша"""
    try:
        if not token.access_level == "admin":
            raise HTTPException(status_code=403, detail="Доступ только для администраторов")
        
        status = cache_cleanup_service.get_cleanup_status()
        return CleanupStatus(**status)
        
    except Exception as e:
        logger.error(f"Ошибка при получении статуса очистки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/cleanup", response_model=CleanupResponse)
async def trigger_cleanup(
    request: CleanupRequest,
    background_tasks: BackgroundTasks,
    token: TokenValidation = Depends(get_current_token)
):
    """Запустить очистку кэша"""
    try:
        if not token.access_level == "admin":
            raise HTTPException(status_code=403, detail="Доступ только для администраторов")
        
        # Запускаем очистку в фоновом режиме
        background_tasks.add_task(
            cache_cleanup_service.force_cleanup,
            request.task_type
        )
        
        task_type = request.task_type or "all"
        return CleanupResponse(
            success=True,
            message=f"Очистка {task_type} запущена в фоновом режиме",
            task_type=task_type
        )
        
    except Exception as e:
        logger.error(f"Ошибка при запуске очистки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/start", response_model=CleanupResponse)
async def start_cleanup_service(token: TokenValidation = Depends(get_current_token)):
    """Запустить сервис автоматической очистки"""
    try:
        if not token.access_level == "admin":
            raise HTTPException(status_code=403, detail="Доступ только для администраторов")
        
        if cache_cleanup_service.is_running:
            return CleanupResponse(
                success=False,
                message="Сервис очистки уже запущен"
            )
        
        # Запускаем сервис
        cache_cleanup_service.start()
        
        return CleanupResponse(
            success=True,
            message="Сервис автоматической очистки запущен"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при запуске сервиса очистки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.post("/stop", response_model=CleanupResponse)
async def stop_cleanup_service(token: TokenValidation = Depends(get_current_token)):
    """Остановить сервис автоматической очистки"""
    try:
        if not token.access_level == "admin":
            raise HTTPException(status_code=403, detail="Доступ только для администраторов")
        
        if not cache_cleanup_service.is_running:
            return CleanupResponse(
                success=False,
                message="Сервис очистки не запущен"
            )
        
        cache_cleanup_service.stop()
        
        return CleanupResponse(
            success=True,
            message="Сервис автоматической очистки остановлен"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при остановке сервиса очистки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.put("/config", response_model=UpdateCleanupConfigResponse)
async def update_cleanup_config(
    request: UpdateCleanupConfigRequest,
    token: TokenValidation = Depends(get_current_token)
):
    """Обновить конфигурацию очистки"""
    try:
        if not token.access_level == "admin":
            raise HTTPException(status_code=403, detail="Доступ только для администраторов")
        
        # Преобразуем Pydantic модели в словари
        config_updates = {}
        for task_name, config in request.config_updates.items():
            config_updates[task_name] = config.dict()
        
        # Обновляем конфигурацию
        cache_cleanup_service.update_cleanup_config(config_updates)
        
        updated_configs = list(config_updates.keys())
        
        return UpdateCleanupConfigResponse(
            success=True,
            message=f"Обновлено {len(updated_configs)} конфигураций",
            updated_configs=updated_configs
        )
        
    except Exception as e:
        logger.error(f"Ошибка при обновлении конфигурации очистки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/config", response_model=Dict[str, Any])
async def get_cleanup_config(token: TokenValidation = Depends(get_current_token)):
    """Получить текущую конфигурацию очистки"""
    try:
        if not token.access_level == "admin":
            raise HTTPException(status_code=403, detail="Доступ только для администраторов")
        
        return cache_cleanup_service.cleanup_config
        
    except Exception as e:
        logger.error(f"Ошибка при получении конфигурации очистки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/health")
async def cleanup_health_check():
    """Проверка здоровья сервиса очистки (публичный эндпоинт)"""
    try:
        status = cache_cleanup_service.get_status()
        return {
            "status": "healthy" if status['is_running'] else "stopped",
            "running": status['running'],
            "categories": status.get('categories', {}),
            "next_cleanup": status.get('next_cleanup')
        }
        
    except Exception as e:
        logger.error(f"Ошибка при проверке здоровья сервиса очистки: {e}")
        return {
            "status": "error",
            "error": str(e)
        }


@router.delete("/reset")
async def reset_cleanup_service(token: TokenValidation = Depends(get_current_token)):
    """Сбросить сервис очистки (перезапуск)"""
    try:
        if not token.access_level == "admin":
            raise HTTPException(status_code=403, detail="Доступ только для администраторов")
        
        # Останавливаем сервис
        if cache_cleanup_service.is_running:
            cache_cleanup_service.stop()
        
        # Запускаем заново
        cache_cleanup_service.start()
        
        return CleanupResponse(
            success=True,
            message="Сервис очистки перезапущен"
        )
        
    except Exception as e:
        logger.error(f"Ошибка при сбросе сервиса очистки: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")

