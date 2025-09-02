#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для просмотра PowerPoint документов с навигацией по слайдам
"""

import logging
import os
import tempfile
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import base64

from services.supabase_service import supabase_service
from config import settings
from database.database import SessionLocal

logger = logging.getLogger(__name__)


class PowerPointViewerService:
    """Сервис для просмотра PowerPoint документов"""
    
    def __init__(self):
        self.temp_dir = Path("temp/powerpoint_viewer")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_powerpoint_preview_data(self, document_id: int, slide_number: Optional[int] = None) -> Dict[str, Any]:
        """Получает данные для предварительного просмотра PowerPoint"""
        try:
            # Получаем информацию о документе из БД
            from database.database import SessionLocal
            from database.models import Document
            
            db = SessionLocal()
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if not document:
                    raise Exception(f"Документ {document_id} не найден")
                
                if not document.is_processed:
                    raise Exception(f"Документ {document_id} еще не обработан")
                
                # Проверяем, что это PowerPoint
                if not document.mime_type.startswith('application/vnd.openxmlformats-officedocument.presentationml.presentation') and \
                   not document.mime_type.startswith('application/vnd.ms-powerpoint'):
                    raise Exception(f"Документ {document_id} не является PowerPoint файлом")
                
                # Получаем URL для скачивания
                download_url = self._get_download_url(document)
                
                # Получаем информацию о слайдах
                slide_info = await self._get_slide_info(document, slide_number)
                
                return {
                    'success': True,
                    'document_id': document_id,
                    'document_name': document.title or document.original_filename,
                    'download_url': download_url,
                    'local_url': f"/viewer/public/powerpoint/{document_id}/data",
                    'file_url': f"/viewer/public/powerpoint/{document_id}/file",
                    'slide_info': slide_info,
                    'viewer_config': self._get_viewer_config(),
                    'navigation_support': True
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка при получении данных PowerPoint: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _get_download_url(self, document) -> str:
        """Получает URL для скачивания документа"""
        try:
            # Создаем прямую ссылку на Supabase Storage
            bucket_name = getattr(settings, 'supabase_bucket', 'rag-files')
            file_path = document.file_path or document.filename
            
            if file_path:
                return f"{settings.supabase_url}/storage/v1/object/public/{bucket_name}/{file_path}"
            else:
                return f"{settings.supabase_url}/storage/v1/object/public/{bucket_name}/{document.filename}"
                
        except Exception as e:
            logger.error(f"Ошибка при создании URL скачивания: {e}")
            return ""
    
    async def _get_slide_info(self, document, target_slide: Optional[int] = None) -> Dict[str, Any]:
        """Получает информацию о слайдах PowerPoint"""
        try:
            # Получаем чанки документа для определения количества слайдов
            from database.models import DocumentChunk
            
            db = SessionLocal()
            try:
                chunks = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == document.id
                ).all()
                
                # Извлекаем информацию о слайдах из чанков
                slides = set()
                for chunk in chunks:
                    if chunk.page_number:
                        slides.add(chunk.page_number)
                
                # Если слайды не найдены, используем дефолтные
                if not slides:
                    slides = {1, 2, 3, 4, 5}
                
                slides = sorted(list(slides))
                current_slide = target_slide or slides[0] if slides else 1
                
                return {
                    'total_slides': len(slides),
                    'slides': slides,
                    'current_slide': current_slide,
                    'has_slides': len(slides) > 0
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка при получении информации о слайдах: {e}")
            return {
                'total_slides': 5,
                'slides': [1, 2, 3, 4, 5],
                'current_slide': 1,
                'has_slides': False
            }
    
    def _get_viewer_config(self) -> Dict[str, Any]:
        """Получает конфигурацию просмотрщика"""
        return {
            'theme': 'light',
            'zoom_levels': [0.5, 0.75, 1, 1.25, 1.5, 2],
            'default_zoom': 1,
            'enable_navigation': True,
            'enable_search': True,
            'enable_print': True
        }
    
    def create_powerpoint_viewer_html(self, document_data: Dict[str, Any]) -> str:
        """Создает HTML для PowerPoint просмотрщика"""
        try:
            if not document_data.get('success'):
                return self._create_error_html(document_data.get('error', 'Неизвестная ошибка'))
            
            document_name = document_data.get('document_name', 'Документ')
            download_url = document_data.get('download_url', '')
            local_url = document_data.get('local_url', '')
            file_url = document_data.get('file_url', '')
            slide_info = document_data.get('slide_info', {})
            viewer_config = document_data.get('viewer_config', {})
            
            # Создаем HTML для PowerPoint просмотрщика
            html_content = f"""
            <!DOCTYPE html>
            <html lang="ru">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Просмотр PowerPoint: {document_name}</title>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        margin: 0;
                        padding: 0;
                        background: #f5f5f5;
                    }}
                    .viewer-container {{
                        max-width: 100%;
                        margin: 0;
                        background: white;
                        min-height: 100vh;
                    }}
                    .toolbar {{
                        background: #2c3e50;
                        color: white;
                        padding: 15px 20px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        flex-wrap: wrap;
                        gap: 10px;
                        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    }}
                    .document-title {{
                        font-size: 18px;
                        font-weight: bold;
                    }}
                    .controls {{
                        display: flex;
                        gap: 10px;
                        align-items: center;
                    }}
                    .slide-controls {{
                        display: flex;
                        gap: 10px;
                        align-items: center;
                        background: rgba(255,255,255,0.1);
                        padding: 8px 12px;
                        border-radius: 6px;
                    }}
                    .btn {{
                        background: #3498db;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 4px;
                        cursor: pointer;
                        text-decoration: none;
                        font-size: 14px;
                        transition: background 0.3s ease;
                    }}
                    .btn:hover {{
                        background: #2980b9;
                    }}
                    .btn.secondary {{
                        background: #95a5a6;
                    }}
                    .btn.secondary:hover {{
                        background: #7f8c8d;
                    }}
                    .slide-input {{
                        background: white;
                        color: #2c3e50;
                        border: none;
                        padding: 6px 12px;
                        border-radius: 4px;
                        font-size: 14px;
                        width: 60px;
                        text-align: center;
                    }}
                    .powerpoint-container {{
                        padding: 20px;
                        text-align: center;
                        min-height: 600px;
                    }}
                    .powerpoint-viewer {{
                        border: 1px solid #ddd;
                        border-radius: 8px;
                        overflow: hidden;
                        max-width: 100%;
                        height: 80vh;
                        margin: 0 auto;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                    }}
                    .loading {{
                        padding: 40px;
                        font-size: 16px;
                        color: #666;
                    }}
                    .error {{
                        padding: 40px;
                        color: #e74c3c;
                        text-align: center;
                    }}
                    .fallback {{
                        padding: 40px;
                        text-align: center;
                        background: #f8f9fa;
                        border-radius: 8px;
                        margin: 20px;
                    }}
                    @media (max-width: 768px) {{
                        .toolbar {{
                            flex-direction: column;
                            align-items: stretch;
                        }}
                        .controls {{
                            justify-content: center;
                        }}
                        .powerpoint-viewer {{
                            height: 60vh;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="viewer-container">
                    <div class="toolbar">
                        <div class="document-title">📊 {document_name}</div>
                        <div class="controls">
                            <div class="slide-controls">
                                <button class="btn secondary" onclick="previousSlide()">◀</button>
                                <input type="number" class="slide-input" id="slideInput" min="1" max="{slide_info.get('total_slides', 5)}" value="{slide_info.get('current_slide', 1)}">
                                <span>/ {slide_info.get('total_slides', 5)}</span>
                                <button class="btn secondary" onclick="nextSlide()">▶</button>
                            </div>
                            <button class="btn" onclick="downloadDocument()">📥 Скачать</button>
                            <button class="btn secondary" onclick="openInOfficeOnline()">🌐 Office Online</button>
                            <button class="btn secondary" onclick="printDocument()">🖨️ Печать</button>
                        </div>
                    </div>
                    
                    <div class="powerpoint-container">
                        <div id="powerpointViewer" class="powerpoint-viewer">
                            <div class="loading">Загрузка PowerPoint документа...</div>
                        </div>
                    </div>
                </div>
                
                <script>
                    let currentSlide = {slide_info.get('current_slide', 1)};
                    const totalSlides = {slide_info.get('total_slides', 5)};
                    
                    // Функция для скачивания документа
                    function downloadDocument() {{
                        const link = document.createElement('a');
                        link.href = '{download_url}';
                        link.download = '{document_name}';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    }}
                    
                    // Функция для открытия в Office Online
                    function openInOfficeOnline() {{
                        const fileUrl = '{download_url}';
                        const officeUrl = `https://view.officeapps.live.com/op/embed.aspx?src=${{encodeURIComponent(fileUrl)}}`;
                        window.open(officeUrl, '_blank');
                    }}
                    
                    // Функция для печати
                    function printDocument() {{
                        window.print();
                    }}
                    
                    // Функция для перехода на предыдущий слайд
                    function previousSlide() {{
                        if (currentSlide > 1) {{
                            currentSlide--;
                            changeSlide();
                        }}
                    }}
                    
                    // Функция для перехода на следующий слайд
                    function nextSlide() {{
                        if (currentSlide < totalSlides) {{
                            currentSlide++;
                            changeSlide();
                        }}
                    }}
                    
                    // Функция для смены слайда
                    function changeSlide() {{
                        const slideInput = document.getElementById('slideInput');
                        slideInput.value = currentSlide;
                        loadPowerPointDocument();
                    }}
                    
                    // Автоматически загружаем PowerPoint документ
                    window.addEventListener('load', function() {{
                        loadPowerPointDocument();
                    }});
                    
                    // Загружаем PowerPoint документ
                    async function loadPowerPointDocument() {{
                        try {{
                            console.log('Загружаем PowerPoint документ, слайд:', currentSlide);
                            
                            // Сразу показываем fallback для PowerPoint
                            // (Office Online не работает с localhost)
                            showFallback();
                            
                        }} catch (error) {{
                            console.error('Ошибка загрузки PowerPoint:', error);
                            showFallback();
                        }}
                    }}
                    
                    // Показываем fallback если основной viewer не работает
                    function showFallback() {{
                        const viewer = document.getElementById('powerpointViewer');
                        viewer.innerHTML = `
                            <div class="fallback">
                                <h3>📊 PowerPoint презентация загружена</h3>
                                <p><strong>Файл:</strong> {document_name}</p>
                                <p><strong>Статус:</strong> Файл успешно загружен</p>
                                <p><strong>Формат:</strong> PowerPoint презентация (.ppt/.pptx)</p>
                                <div style="margin: 20px 0;">
                                    <button class="btn" onclick="downloadDocument()">📥 Скачать презентацию</button>
                                    <button class="btn secondary" onclick="printDocument()">🖨️ Печать</button>
                                </div>
                                <p style="margin-top: 20px; color: #666;">
                                    <em>Для просмотра содержимого PowerPoint презентации используйте Microsoft PowerPoint, LibreOffice Impress или другие совместимые приложения.</em>
                                </p>
                                <p style="margin-top: 10px; color: #888; font-size: 12px;">
                                    <em>Примечание: Автоматический рендеринг PowerPoint не поддерживается в браузере</em>
                                </p>
                            </div>
                        `;
                    }}
                </script>
            </body>
            </html>
            """
            
            return html_content
            
        except Exception as e:
            logger.error(f"Ошибка при создании HTML PowerPoint просмотрщика: {e}")
            return self._create_error_html(f"Ошибка создания просмотрщика: {e}")
    
    def _create_error_html(self, error_message: str) -> str:
        """Создает HTML для отображения ошибки"""
        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Ошибка просмотра PowerPoint</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    margin: 0;
                    padding: 40px;
                    background: #f5f5f5;
                    text-align: center;
                }}
                .error-container {{
                    background: white;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                    max-width: 600px;
                    margin: 0 auto;
                }}
                .error-icon {{
                    font-size: 48px;
                    color: #e74c3c;
                    margin-bottom: 20px;
                }}
                .error-title {{
                    color: #e74c3c;
                    font-size: 24px;
                    margin-bottom: 20px;
                }}
                .error-message {{
                    color: #666;
                    font-size: 16px;
                    line-height: 1.6;
                }}
            </style>
        </head>
        <body>
            <div class="error-container">
                <div class="error-icon">❌</div>
                <div class="error-title">Ошибка просмотра</div>
                <div class="error-message">{error_message}</div>
            </div>
        </body>
        </html>
        """


# Создаем экземпляр сервиса
powerpoint_viewer_service = PowerPointViewerService()
