#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Роутер для просмотра документов с навигацией
"""

from fastapi import APIRouter, HTTPException, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from typing import Optional
import logging
import urllib.parse

from services.pdf_viewer_service import pdf_viewer_service
from services.excel_viewer_service import excel_viewer_service
from services.word_viewer_service import word_viewer_service
from services.powerpoint_viewer_service import powerpoint_viewer_service
from services.auth_dependencies import get_current_token
from schemas import TokenValidation

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/viewer", tags=["document-viewer"])


@router.get("/pdf/{document_id}", response_class=HTMLResponse)
async def view_pdf_document(
    document_id: int,
    page: Optional[int] = Query(None, description="Номер страницы для перехода"),
    token: Optional[TokenValidation] = Depends(get_current_token)
):
    """Просмотр PDF документа с навигацией по страницам"""
    try:
        # Получаем данные для просмотра
        document_data = await pdf_viewer_service.get_pdf_preview_data(document_id, page)
        
        if document_data.get('error'):
            raise HTTPException(status_code=404, detail=document_data.get('error', 'Документ не найден'))
        
        # Создаем HTML просмотрщика
        html_content = pdf_viewer_service.create_pdf_viewer_html(document_data)
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре PDF {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/public/pdf/{document_id}", response_class=HTMLResponse)
async def view_pdf_document_public(
    document_id: int,
    page: Optional[int] = Query(None, description="Номер страницы для перехода")
):
    """Публичный просмотр PDF документа без аутентификации"""
    try:
        # Получаем данные для просмотра
        document_data = await pdf_viewer_service.get_pdf_preview_data(document_id, page)
        
        if document_data.get('error'):
            raise HTTPException(status_code=404, detail=document_data.get('error', 'Документ не найден'))
        
        # Создаем HTML просмотрщика
        html_content = pdf_viewer_service.create_pdf_viewer_html(document_data)
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Ошибка при публичном просмотре PDF {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/public/pdf/{document_id}/data")
async def get_pdf_data_public(document_id: int):
    """Получение PDF данных для просмотра (обход CORS)"""
    try:
        # Получаем данные для просмотра
        document_data = await pdf_viewer_service.get_pdf_preview_data(document_id)
        
        if document_data.get('error'):
            raise HTTPException(status_code=404, detail=document_data.get('error', 'Документ не найден'))
        
        return document_data
        
    except Exception as e:
        logger.error(f"Ошибка при получении PDF данных {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/public/pdf/{document_id}/file")
async def get_pdf_file_public(document_id: int):
    """Получение PDF файла напрямую с сервера"""
    try:
        from database.database import SessionLocal
        from database.models import Document
        from fastapi.responses import FileResponse
        import os
        
        db = SessionLocal()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise HTTPException(status_code=404, detail="Документ не найден")
            
            if not document.is_processed:
                raise HTTPException(status_code=400, detail="Документ еще не обработан")
            
            # Проверяем, что это PDF
            if not document.mime_type.startswith('application/pdf'):
                raise HTTPException(status_code=400, detail="Документ не является PDF")
            
            # Получаем файл из Supabase
            from services.supabase_service import supabase_service
            
            try:
                # Скачиваем файл из Supabase
                logger.info(f"Пытаемся скачать файл: {document.file_path or document.filename}")
                file_data = supabase_service.download_file(document.file_path or document.filename)
                
                if not file_data:
                    raise HTTPException(status_code=404, detail="Файл не найден в хранилище")
                
                logger.info(f"Файл успешно скачан, размер: {len(file_data)} байт")
                
                # Возвращаем файл как response
                from fastapi.responses import Response
                # Безопасно кодируем filename для HTTP headers
                try:
                    # Используем RFC 5987 формат для UTF-8 имен файлов
                    safe_filename = urllib.parse.quote(document.original_filename)
                    logger.info(f"Создаем Response с безопасным filename: {safe_filename}")
                    
                    return Response(
                        content=file_data,
                        media_type="application/pdf",
                        headers={
                            "Content-Disposition": f"inline; filename*=UTF-8''{safe_filename}",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                    
                except Exception as header_error:
                    logger.error(f"Ошибка при создании заголовков: {header_error}")
                    # Fallback на простые заголовки без filename
                    return Response(
                        content=file_data,
                        media_type="application/pdf",
                        headers={
                            "Content-Disposition": "inline",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                
            except Exception as e:
                logger.error(f"Ошибка при скачивании файла из Supabase: {e}")
                logger.error(f"Тип ошибки: {type(e).__name__}")
                logger.error(f"Детали ошибки: {str(e)}")
                
                # Попробуем создать прямую ссылку на Supabase
                try:
                    # Получаем bucket name из настроек или используем дефолтный
                    from config import settings
                    bucket_name = getattr(settings, 'supabase_bucket', 'rag-files')
                    file_path = document.file_path or document.filename
                    
                    # Создаем прямую ссылку
                    direct_url = f"https://mrvhrfsmhdvhwbwgsrra.supabase.co/storage/v1/object/public/{bucket_name}/{file_path}"
                    
                    logger.info(f"Создаем прямую ссылку: {direct_url}")
                    
                    # Возвращаем redirect на прямую ссылку
                    from fastapi.responses import RedirectResponse
                    return RedirectResponse(url=direct_url)
                    
                except Exception as redirect_error:
                    logger.error(f"Ошибка при создании прямой ссылки: {redirect_error}")
                    raise HTTPException(status_code=500, detail="Ошибка при получении файла")
                
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении PDF файла {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/public/excel/{document_id}/file")
async def get_excel_file_public(document_id: int):
    """Получение Excel файла напрямую с сервера"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"🔍 ВЫЗВАН ENDPOINT для скачивания Excel файла {document_id}")
    
    try:
        from database.database import SessionLocal
        from database.models import Document
        from fastapi.responses import Response
        import urllib.parse
        import logging
        
        logger = logging.getLogger(__name__)
        
        db = SessionLocal()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                logger.error(f"Документ {document_id} не найден в базе данных")
                raise HTTPException(status_code=404, detail="Документ не найден")
            
            if not document.is_processed:
                logger.error(f"Документ {document_id} еще не обработан")
                raise HTTPException(status_code=400, detail="Документ еще не обработан")
            
            # Проверяем, что это Excel файл
            logger.info(f"=== ДИАГНОСТИКА ДОКУМЕНТА {document_id} ===")
            logger.info(f"MIME тип документа: {document.mime_type}")
            logger.info(f"Тип файла: {document.file_type}")
            logger.info(f"Размер файла: {document.file_size} байт")
            logger.info(f"Путь файла: {document.file_path}")
            logger.info(f"Имя файла: {document.filename}")
            logger.info(f"Оригинальное имя: {document.original_filename}")
            logger.info(f"==========================================")
            
            if not document.mime_type.startswith('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') and not document.mime_type.startswith('application/vnd.ms-excel'):
                logger.error(f"Документ {document_id} не является Excel файлом. MIME тип: {document.mime_type}")
                raise HTTPException(status_code=400, detail=f"Документ не является Excel файлом. MIME тип: {document.mime_type}")
            
            # Получаем файл из Supabase
            from services.supabase_service import supabase_service
            
            try:
                # Скачиваем файл из Supabase
                logger.info(f"Пытаемся скачать Excel файл: {document.file_path or document.filename}")
                file_data = supabase_service.download_file(document.file_path or document.filename)
                
                if not file_data:
                    logger.error(f"Файл не найден в хранилище Supabase")
                    raise HTTPException(status_code=404, detail="Файл не найден в хранилище")
                
                logger.info(f"Excel файл успешно скачан, размер: {len(file_data)} байт")
                
                # Определяем MIME тип
                mime_type = document.mime_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                
                # Безопасно кодируем filename для HTTP headers
                try:
                    safe_filename = urllib.parse.quote(document.original_filename)
                    logger.info(f"Создаем Response с безопасным filename: {safe_filename}")
                    
                    return Response(
                        content=file_data,
                        media_type=mime_type,
                        headers={
                            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                    
                except Exception as header_error:
                    logger.error(f"Ошибка при создании заголовков: {header_error}")
                    return Response(
                        content=file_data,
                        media_type=mime_type,
                        headers={
                            "Content-Disposition": "attachment",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                
            except Exception as e:
                logger.error(f"Ошибка при скачивании Excel файла из Supabase: {e}")
                raise HTTPException(status_code=500, detail="Ошибка при получении файла")
                
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении Excel файла {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
    """Получение Excel файла напрямую с сервера"""
    try:
        from database.database import SessionLocal
        from database.models import Document
        from fastapi.responses import Response
        import urllib.parse
        import logging
        
        logger = logging.getLogger(__name__)
        
        db = SessionLocal()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise HTTPException(status_code=404, detail="Документ не найден")
            
            if not document.is_processed:
                raise HTTPException(status_code=400, detail="Документ еще не обработан")
            
            # Проверяем, что это Excel файл
            logger.info(f"MIME тип документа: {document.mime_type}")
            logger.info(f"Тип файла: {document.file_type}")
            logger.info(f"Размер файла: {document.file_size} байт")
            logger.info(f"Путь файла: {document.file_path}")
            logger.info(f"Имя файла: {document.filename}")
            
            if not document.mime_type.startswith('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') and not document.mime_type.startswith('application/vnd.ms-excel'):
                logger.error(f"Документ {document_id} не является Excel файлом. MIME тип: {document.mime_type}")
                raise HTTPException(status_code=400, detail=f"Документ не является Excel файлом. MIME тип: {document.mime_type}")
            
            # Получаем файл из Supabase
            from services.supabase_service import supabase_service
            
            try:
                # Скачиваем файл из Supabase
                logger.info(f"Пытаемся скачать Excel файл: {document.file_path or document.filename}")
                file_data = supabase_service.download_file(document.file_path or document.filename)
                
                if not file_data:
                    raise HTTPException(status_code=404, detail="Файл не найден в хранилище")
                
                logger.info(f"Excel файл успешно скачан, размер: {len(file_data)} байт")
                
                # Определяем MIME тип
                mime_type = document.mime_type or "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                
                # Безопасно кодируем filename для HTTP headers
                try:
                    safe_filename = urllib.parse.quote(document.original_filename)
                    logger.info(f"Создаем Response с безопасным filename: {safe_filename}")
                    
                    return Response(
                        content=file_data,
                        media_type=mime_type,
                        headers={
                            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                    
                except Exception as header_error:
                    logger.error(f"Ошибка при создании заголовков: {header_error}")
                    return Response(
                        content=file_data,
                        media_type=mime_type,
                        headers={
                            "Content-Disposition": "attachment",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                
            except Exception as e:
                logger.error(f"Ошибка при скачивании Excel файла из Supabase: {e}")
                raise HTTPException(status_code=500, detail="Ошибка при получении файла")
                
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении Excel файла {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
        from fastapi.responses import Response
        import os
        
        db = SessionLocal()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise HTTPException(status_code=404, detail="Документ не найден")
            
            if not document.is_processed:
                raise HTTPException(status_code=400, detail="Документ еще не обработан")
            
            # Проверяем, что это Excel
            if not (document.mime_type.startswith('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') or 
                   document.mime_type.startswith('application/vnd.ms-excel')):
                raise HTTPException(status_code=400, detail="Документ не является Excel файлом")
            
            # Получаем файл из Supabase
            from services.supabase_service import supabase_service
            
            try:
                # Скачиваем файл из Supabase
                logger.info(f"Пытаемся скачать Excel файл: {document.file_path or document.filename}")
                file_data = supabase_service.download_file(document.file_path or document.filename)
                
                if not file_data:
                    raise HTTPException(status_code=404, detail="Файл не найден в хранилище")
                
                logger.info(f"Excel файл успешно скачан, размер: {len(file_data)} байт")
                
                # Возвращаем файл как response
                try:
                    # Используем RFC 5987 формат для UTF-8 имен файлов
                    safe_filename = urllib.parse.quote(document.original_filename)
                    logger.info(f"Создаем Response с безопасным filename: {safe_filename}")
                    
                    return Response(
                        content=file_data,
                        media_type=document.mime_type,
                        headers={
                            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                    
                except Exception as header_error:
                    logger.error(f"Ошибка при создании заголовков: {header_error}")
                    # Fallback на простые заголовки без filename
                    return Response(
                        content=file_data,
                        media_type=document.mime_type,
                        headers={
                            "Content-Disposition": "attachment",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                
            except Exception as e:
                logger.error(f"Ошибка при скачивании Excel файла из Supabase: {e}")
                raise HTTPException(status_code=500, detail="Ошибка при получении файла")
                
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении Excel файла {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/public/word/{document_id}/file")
async def get_word_file_public(document_id: int):
    """Получение Word файла напрямую с сервера"""
    try:
        from database.database import SessionLocal
        from database.models import Document
        from fastapi.responses import Response
        import urllib.parse
        import logging
        
        logger = logging.getLogger(__name__)
        
        db = SessionLocal()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise HTTPException(status_code=404, detail="Документ не найден")
            
            if not document.is_processed:
                raise HTTPException(status_code=400, detail="Документ еще не обработан")
            
            # Проверяем, что это Word файл
            if not document.mime_type.startswith('application/vnd.openxmlformats-officedocument.wordprocessingml.document') and not document.mime_type.startswith('application/msword'):
                raise HTTPException(status_code=400, detail="Документ не является Word файлом")
            
            # Получаем файл из Supabase
            from services.supabase_service import supabase_service
            
            try:
                # Скачиваем файл из Supabase
                logger.info(f"Пытаемся скачать Word файл: {document.file_path or document.filename}")
                file_data = supabase_service.download_file(document.file_path or document.filename)
                
                if not file_data:
                    raise HTTPException(status_code=404, detail="Файл не найден в хранилище")
                
                logger.info(f"Word файл успешно скачан, размер: {len(file_data)} байт")
                
                # Определяем MIME тип
                mime_type = document.mime_type or "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                
                # Безопасно кодируем filename для HTTP headers
                try:
                    safe_filename = urllib.parse.quote(document.original_filename)
                    logger.info(f"Создаем Response с безопасным filename: {safe_filename}")
                    
                    return Response(
                        content=file_data,
                        media_type=mime_type,
                        headers={
                            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                    
                except Exception as header_error:
                    logger.error(f"Ошибка при создании заголовков: {header_error}")
                    return Response(
                        content=file_data,
                        media_type=mime_type,
                        headers={
                            "Content-Disposition": "attachment",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                
            except Exception as e:
                logger.error(f"Ошибка при скачивании Word файла из Supabase: {e}")
                raise HTTPException(status_code=500, detail="Ошибка при получении файла")
                
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении Word файла {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")
        from fastapi.responses import Response
        import os
        
        db = SessionLocal()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise HTTPException(status_code=404, detail="Документ не найден")
            
            if not document.is_processed:
                raise HTTPException(status_code=400, detail="Документ еще не обработан")
            
            # Проверяем, что это Word
            if not (document.mime_type.startswith('application/vnd.openxmlformats-officedocument.wordprocessingml.document') or 
                   document.mime_type.startswith('application/msword')):
                raise HTTPException(status_code=400, detail="Документ не является Word файлом")
            
            # Получаем файл из Supabase
            from services.supabase_service import supabase_service
            
            try:
                # Скачиваем файл из Supabase
                logger.info(f"Пытаемся скачать Word файл: {document.file_path or document.filename}")
                file_data = supabase_service.download_file(document.file_path or document.filename)
                
                if not file_data:
                    raise HTTPException(status_code=404, detail="Файл не найден в хранилище")
                
                logger.info(f"Word файл успешно скачан, размер: {len(file_data)} байт")
                
                # Возвращаем файл как response
                try:
                    # Используем RFC 5987 формат для UTF-8 имен файлов
                    safe_filename = urllib.parse.quote(document.original_filename)
                    logger.info(f"Создаем Response с безопасным filename: {safe_filename}")
                    
                    return Response(
                        content=file_data,
                        media_type=document.mime_type,
                        headers={
                            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                    
                except Exception as header_error:
                    logger.error(f"Ошибка при создании заголовков: {header_error}")
                    # Fallback на простые заголовки без filename
                    return Response(
                        content=file_data,
                        media_type=document.mime_type,
                        headers={
                            "Content-Disposition": "attachment",
                            "Cache-Control": "public, max-age=3600",
                            "Access-Control-Allow-Origin": "*",
                            "Access-Control-Allow-Methods": "GET, OPTIONS",
                            "Access-Control-Allow-Headers": "*"
                        }
                    )
                
            except Exception as e:
                logger.error(f"Ошибка при скачивании Word файла из Supabase: {e}")
                raise HTTPException(status_code=500, detail="Ошибка при получении файла")
                
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при получении Word файла {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/pdf/{document_id}/metadata")
async def get_pdf_metadata(
    document_id: int,
    token: TokenValidation = Depends(get_current_token)
):
    """Получение метаданных PDF документа"""
    try:
        metadata = pdf_viewer_service.get_pdf_metadata(document_id)
        
        if 'error' in metadata:
            raise HTTPException(status_code=404, detail=metadata['error'])
        
        return metadata
        
    except Exception as e:
        logger.error(f"Ошибка при получении метаданных PDF {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/pdf/{document_id}/page/{page_number}")
async def go_to_pdf_page(
    document_id: int,
    page_number: int,
    token: TokenValidation = Depends(get_current_token)
):
    """Переход на конкретную страницу PDF документа"""
    try:
        # Получаем данные для просмотра с указанной страницей
        document_data = await pdf_viewer_service.get_pdf_preview_data(document_id, page_number)
        
        if document_data.get('error'):
            raise HTTPException(status_code=404, detail=document_data.get('error', 'Документ не найден'))
        
        # Создаем HTML просмотрщика с переходом на нужную страницу
        html_content = pdf_viewer_service.create_pdf_viewer_html(document_data)
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Ошибка при переходе на страницу {page_number} PDF {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/excel/{document_id}")
async def view_excel_document(
    document_id: int,
    sheet: Optional[str] = Query(None, description="Название листа для перехода"),
    token: Optional[TokenValidation] = Depends(get_current_token)
):
    """Просмотр Excel документа через Google Sheets"""
    try:
        # Получаем данные для просмотра
        document_data = excel_viewer_service.get_excel_preview_data(document_id)
        
        if document_data.get('error'):
            raise HTTPException(status_code=404, detail=document_data.get('error', 'Документ не найден'))
        
        # Создаем HTML просмотрщика
        html_content = excel_viewer_service.create_excel_viewer_html(document_data)
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре Excel {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/public/excel/{document_id}", response_class=HTMLResponse)
async def view_excel_document_public(
    document_id: int,
    sheet: Optional[str] = Query(None, description="Название листа для перехода")
):
    """Публичный просмотр Excel документа без аутентификации"""
    try:
        # Получаем данные для просмотра
        document_data = excel_viewer_service.get_excel_preview_data(document_id)
        
        if document_data.get('error'):
            raise HTTPException(status_code=404, detail=document_data.get('error', 'Документ не найден'))
        
        # Создаем HTML просмотрщика
        html_content = excel_viewer_service.create_excel_viewer_html(document_data)
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Ошибка при публичном просмотре Excel {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/word/{document_id}", response_class=HTMLResponse)
async def view_word_document(
    document_id: int,
    token: Optional[TokenValidation] = Depends(get_current_token)
):
    """Просмотр Word документа с использованием docx-preview"""
    try:
        # Получаем данные для просмотра
        document_data = word_viewer_service.get_word_preview_data(document_id)
        
        if document_data.get('error'):
            raise HTTPException(status_code=404, detail=document_data.get('error', 'Документ не найден'))
        
        # Создаем HTML просмотрщика
        html_content = word_viewer_service.create_word_viewer_html(document_data)
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре Word {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/public/word/{document_id}", response_class=HTMLResponse)
async def view_word_document_public(
    document_id: int
):
    """Публичный просмотр Word документа без аутентификации"""
    try:
        # Получаем данные для просмотра
        document_data = word_viewer_service.get_word_preview_data(document_id)
        
        if document_data.get('error'):
            raise HTTPException(status_code=404, detail=document_data.get('error', 'Документ не найден'))
        
        # Создаем HTML просмотрщика
        html_content = word_viewer_service.create_word_viewer_html(document_data)
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Ошибка при публичном просмотре Word {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/powerpoint/{document_id}")
async def view_powerpoint_document(
    document_id: int,
    slide: Optional[int] = Query(None, description="Номер слайда для перехода"),
    token: Optional[TokenValidation] = Depends(get_current_token)
):
    """Просмотр PowerPoint документа через Office Online"""
    try:
        # TODO: Реализовать просмотр PowerPoint через Office Online
        return {
            "message": "Просмотр PowerPoint документов пока не реализован",
            "document_id": document_id,
            "slide": slide,
            "suggestion": "Используйте скачивание документа и открытие в PowerPoint"
        }
        
    except Exception as e:
        logger.error(f"Ошибка при просмотре PowerPoint {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/public/powerpoint/{document_id}")
async def view_powerpoint_document_public(
    document_id: int,
    slide: Optional[int] = Query(None, description="Номер слайда для перехода")
):
    """Публичный просмотр PowerPoint документа без аутентификации"""
    try:
        # Получаем данные для просмотра
        document_data = powerpoint_viewer_service.get_powerpoint_preview_data(document_id, slide)
        
        if document_data.get('error'):
            raise HTTPException(status_code=404, detail=document_data.get('error', 'Документ не найден'))
        
        # Создаем HTML просмотрщика
        html_content = powerpoint_viewer_service.create_powerpoint_viewer_html(document_data)
        
        return HTMLResponse(content=html_content)
        
    except Exception as e:
        logger.error(f"Ошибка при публичном просмотре PowerPoint {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/{document_type}/{document_id}")
async def view_document_generic(
    document_type: str,
    document_id: int,
    token: TokenValidation = Depends(get_current_token)
):
    """Универсальный просмотр документов"""
    try:
        # Определяем тип документа и перенаправляем на соответствующий обработчик
        if document_type == "pdf":
            return await view_pdf_document(document_id, None, token)
        elif document_type in ["excel", "xlsx", "xls"]:
            return await view_excel_document(document_id, None, token)
        elif document_type in ["word", "docx", "doc"]:
            return await view_word_document(document_id, token)
        elif document_type in ["powerpoint", "pptx", "ppt"]:
            return await view_powerpoint_document(document_id, None, token)
        else:
            raise HTTPException(
                status_code=400, 
                detail=f"Неподдерживаемый тип документа: {document_type}"
            )
            
    except Exception as e:
        logger.error(f"Ошибка при универсальном просмотре документа {document_id}: {e}")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервера")


@router.get("/health")
async def viewer_health_check():
    """Проверка здоровья сервиса просмотра документов"""
    return {
        "status": "healthy",
        "service": "document-viewer",
        "supported_formats": {
            "pdf": "Полная поддержка с навигацией",
            "excel": "Планируется (Google Sheets API)",
            "word": "Планируется (Office Online)",
            "powerpoint": "Планируется (Office Online)"
        },
        "features": [
            "PDF просмотр с навигацией по страницам",
            "Мобильная адаптация",
            "Скачивание документов",
            "Печать документов"
        ]
    }
