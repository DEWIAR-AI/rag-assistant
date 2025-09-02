#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для просмотра PDF документов с навигацией по страницам
"""

import logging
import os
import tempfile
from typing import Dict, Any, Optional, Tuple
from pathlib import Path
import base64

from services.supabase_service import supabase_service
from config import settings

logger = logging.getLogger(__name__)


class PDFViewerService:
    """Сервис для просмотра PDF документов"""
    
    def __init__(self):
        self.temp_dir = Path("temp/pdf_viewer")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    async def get_pdf_preview_data(self, document_id: int, page_number: Optional[int] = None) -> Dict[str, Any]:
        """Получает данные для предварительного просмотра PDF"""
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
                
                # Проверяем, что это PDF
                if not document.mime_type.startswith('application/pdf'):
                    raise Exception(f"Документ {document_id} не является PDF")
                
                # Получаем URL для скачивания
                download_url = self._get_download_url(document)
                
                # Получаем информацию о страницах
                page_info = await self._get_page_info(document, page_number)
                
                return {
                    'success': True,
                    'document_id': document_id,
                    'document_name': document.title or document.original_filename,
                    'download_url': download_url,
                    'local_url': f"/viewer/public/pdf/{document_id}/data",
                    'file_url': f"/viewer/public/pdf/{document_id}/file",
                    'page_info': page_info,
                    'viewer_config': self._get_viewer_config(),
                    'navigation_support': True
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка при получении данных PDF: {e}")
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
    
    async def _get_page_info(self, document, target_page: Optional[int] = None) -> Dict[str, Any]:
        """Получает информацию о страницах PDF"""
        try:
            # Получаем чанки документа для определения количества страниц
            from database.models import DocumentChunk
            from database.database import SessionLocal
            
            db = SessionLocal()
            try:
                chunks = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == document.id
                ).all()
                
                # Определяем количество страниц
                pages = set()
                for chunk in chunks:
                    if chunk.page_number:
                        pages.add(chunk.page_number)
                
                total_pages = max(pages) if pages else 1
                
                # Если указана целевая страница, проверяем её существование
                if target_page and target_page > total_pages:
                    target_page = total_pages
                
                page_info = {
                    'total_pages': total_pages,
                    'current_page': target_page or 1,
                    'has_target_page': target_page is not None,
                    'navigation_urls': {}
                }
                
                # Создаем ссылки для навигации
                if target_page:
                    page_info['navigation_urls'] = {
                        'direct_link': f"{self._get_download_url(document)}#page={target_page}",
                        'viewer_link': f"/viewer/pdf/{document.id}?page={target_page}",
                        'download_with_page': f"/api/documents/{document.id}/download?page={target_page}"
                    }
                
                return page_info
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка при получении информации о страницах: {e}")
            return {
                'total_pages': 1,
                'current_page': 1,
                'has_target_page': False,
                'navigation_urls': {}
            }
    
    def _get_viewer_config(self) -> Dict[str, Any]:
        """Получает конфигурацию PDF просмотрщика"""
        return {
            'viewer_type': 'pdf_js',
            'mobile_friendly': True,
            'supports_navigation': True,
            'features': [
                'zoom',
                'page_navigation',
                'search',
                'download',
                'print'
            ],
            'default_zoom': 100,
            'max_zoom': 400,
            'min_zoom': 25
        }
    
    def create_pdf_viewer_html(self, document_data: Dict[str, Any]) -> str:
        """Создает HTML для PDF просмотрщика"""
        try:
            if not document_data.get('success'):
                return self._create_error_html(document_data.get('error', 'Неизвестная ошибка'))
            
            document_name = document_data.get('document_name', 'Документ')
            download_url = document_data.get('download_url', '')
            local_url = document_data.get('local_url', '')
            file_url = document_data.get('file_url', '')
            page_info = document_data.get('page_info', {})
            viewer_config = document_data.get('viewer_config', {})
            
            html = f"""
            <!DOCTYPE html>
            <html lang="ru">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Просмотр: {document_name}</title>
                <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
                <style>
                    body {{
                        margin: 0;
                        padding: 0;
                        font-family: Arial, sans-serif;
                        background: #f5f5f5;
                    }}
                    .viewer-container {{
                        max-width: 1200px;
                        margin: 0 auto;
                        background: white;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    }}
                    .toolbar {{
                        background: #2c3e50;
                        color: white;
                        padding: 15px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        flex-wrap: wrap;
                        gap: 10px;
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
                    .btn {{
                        background: #3498db;
                        color: white;
                        border: none;
                        padding: 8px 16px;
                        border-radius: 4px;
                        cursor: pointer;
                        text-decoration: none;
                        font-size: 14px;
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
                    .page-controls {{
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    }}
                    .page-input {{
                        width: 60px;
                        padding: 5px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        text-align: center;
                    }}
                    .pdf-container {{
                        padding: 20px;
                        text-align: center;
                        min-height: 600px;
                    }}
                    .pdf-viewer {{
                        border: 1px solid #ddd;
                        border-radius: 8px;
                        overflow: hidden;
                        max-width: 100%;
                        height: auto;
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
                    @media (max-width: 768px) {{
                        .toolbar {{
                            flex-direction: column;
                            align-items: stretch;
                        }}
                        .controls {{
                            justify-content: center;
                        }}
                    }}
                </style>
            </head>
            <body>
                <div class="viewer-container">
                    <div class="toolbar">
                        <div class="document-title">📄 {document_name}</div>
                        <div class="controls">
                            <div class="page-controls">
                                <button class="btn secondary" onclick="previousPage()">◀</button>
                                <input type="number" class="page-input" id="pageInput" min="1" max="{page_info.get('total_pages', 1)}" value="{page_info.get('current_page', 1)}">
                                <span>/ {page_info.get('total_pages', 1)}</span>
                                <button class="btn secondary" onclick="nextPage()">▶</button>
                            </div>
                            <button class="btn" onclick="downloadDocument()">📥 Скачать</button>
                            <button class="btn secondary" onclick="printDocument()">🖨️ Печать</button>
                        </div>
                    </div>
                    
                    <div class="pdf-container">
                        <div id="pdfViewer" class="pdf-viewer">
                            <div class="loading">Загрузка PDF документа...</div>
                        </div>
                    </div>
                </div>
                
                <script>
                    // Конфигурация PDF.js
                    pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
                    
                    let pdfDoc = null;
                    let pageNum = {page_info.get('current_page', 1)};
                    let pageRendering = false;
                    let pageNumPending = null;
                    const scale = 1.5;
                    
                    // Загружаем PDF
                    async function loadPDF() {{
                        try {{
                            // Сначала пробуем загрузить через локальный endpoint для файла
                            const fileUrl = '{file_url}';
                            console.log('Пробуем загрузить PDF через локальный endpoint:', fileUrl);
                            
                            const loadingTask = pdfjsLib.getDocument(fileUrl);
                            pdfDoc = await loadingTask.promise;
                            
                            // Рендерим первую страницу
                            renderPage(pageNum);
                            
                            // Обновляем информацию о страницах
                            document.getElementById('pageInput').max = pdfDoc.numPages;
                            
                        }} catch (error) {{
                            console.error('Ошибка загрузки PDF через локальный endpoint:', error);
                            
                            // Пробуем через прямой URL как fallback
                            try {{
                                console.log('Пробуем через прямой URL:', '{download_url}');
                                const loadingTask = pdfjsLib.getDocument('{download_url}');
                                pdfDoc = await loadingTask.promise;
                                
                                renderPage(pageNum);
                                document.getElementById('pageInput').max = pdfDoc.numPages;
                                
                            }} catch (fallbackError) {{
                                console.error('Ошибка загрузки PDF через прямой URL:', fallbackError);
                                document.getElementById('pdfViewer').innerHTML = 
                                    '<div class="error">Ошибка загрузки PDF документа. Попробуйте скачать файл.<br><br>Ошибка: ' + fallbackError.message + '</div>';
                            }}
                        }}
                    }}
                    
                    // Рендерим страницу
                    async function renderPage(num) {{
                        pageRendering = true;
                        
                        try {{
                            const page = await pdfDoc.getPage(num);
                            const viewport = page.getViewport({{scale}});
                            
                            const canvas = document.createElement('canvas');
                            const ctx = canvas.getContext('2d');
                            canvas.height = viewport.height;
                            canvas.width = viewport.width;
                            
                            const renderContext = {{
                                canvasContext: ctx,
                                viewport: viewport
                            }};
                            
                            await page.render(renderContext).promise;
                            
                            document.getElementById('pdfViewer').innerHTML = '';
                            document.getElementById('pdfViewer').appendChild(canvas);
                            
                            pageNum = num;
                            document.getElementById('pageInput').value = num;
                            
                        }} catch (error) {{
                            console.error('Ошибка рендеринга страницы:', error);
                        }}
                        
                        pageRendering = false;
                        
                        if (pageNumPending !== null) {{
                            renderPage(pageNumPending);
                            pageNumPending = null;
                        }}
                    }}
                    
                    // Переход на предыдущую страницу
                    function previousPage() {{
                        if (pageNum <= 1) return;
                        if (pageRendering) {{
                            pageNumPending = pageNum - 1;
                        }} else {{
                            renderPage(pageNum - 1);
                        }}
                    }}
                    
                    // Переход на следующую страницу
                    function nextPage() {{
                        if (pageNum >= pdfDoc.numPages) return;
                        if (pageRendering) {{
                            pageNumPending = pageNum + 1;
                        }} else {{
                            renderPage(pageNum + 1);
                        }}
                    }}
                    
                    // Переход на конкретную страницу
                    function goToPage() {{
                        const input = document.getElementById('pageInput');
                        const num = parseInt(input.value);
                        
                        if (num >= 1 && num <= pdfDoc.numPages) {{
                            if (pageRendering) {{
                                pageNumPending = num;
                            }} else {{
                                renderPage(num);
                            }}
                        }} else {{
                            input.value = pageNum;
                        }}
                    }}
                    
                    // Скачивание документа
                    function downloadDocument() {{
                        window.open('{download_url}', '_blank');
                    }}
                    
                    // Печать документа
                    function printDocument() {{
                        window.open('{download_url}', '_blank').print();
                    }}
                    
                    // Обработчик изменения страницы
                    document.getElementById('pageInput').addEventListener('change', goToPage);
                    
                    // Загружаем PDF при загрузке страницы
                    window.addEventListener('load', loadPDF);
                </script>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            logger.error(f"Ошибка при создании HTML просмотрщика: {e}")
            return self._create_error_html(f"Ошибка создания просмотрщика: {e}")
    
    def _create_error_html(self, error_message: str) -> str:
        """Создает HTML для отображения ошибки"""
        return f"""
        <!DOCTYPE html>
        <html lang="ru">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Ошибка просмотра</title>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    text-align: center;
                    padding: 50px;
                    background: #f5f5f5;
                }}
                .error-container {{
                    background: white;
                    padding: 40px;
                    border-radius: 8px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                    max-width: 500px;
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
                    margin-bottom: 15px;
                }}
                .error-message {{
                    color: #666;
                    margin-bottom: 20px;
                }}
                .btn {{
                    background: #3498db;
                    color: white;
                    text-decoration: none;
                    padding: 10px 20px;
                    border-radius: 4px;
                    display: inline-block;
                }}
            </style>
        </head>
        <body>
            <div class="error-container">
                <div class="error-icon">❌</div>
                <div class="error-title">Ошибка просмотра</div>
                <div class="error-message">{error_message}</div>
                <a href="javascript:history.back()" class="btn">← Назад</a>
            </div>
        </body>
        </html>
        """
    
    def get_pdf_metadata(self, document_id: int) -> Dict[str, Any]:
        """Получает метаданные PDF документа"""
        try:
            from database.database import SessionLocal
            from database.models import Document, DocumentChunk
            
            db = SessionLocal()
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if not document:
                    return {'error': 'Документ не найден'}
                
                # Получаем информацию о страницах
                chunks = db.query(DocumentChunk).filter(
                    DocumentChunk.document_id == document_id
                ).all()
                
                pages = set()
                for chunk in chunks:
                    if chunk.page_number:
                        pages.add(chunk.page_number)
                
                return {
                    'document_id': document_id,
                    'filename': document.original_filename,
                    'total_pages': max(pages) if pages else 1,
                    'file_size': document.file_size,
                    'uploaded_at': document.uploaded_at.isoformat() if document.uploaded_at else None,
                    'has_pages': len(pages) > 0
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Ошибка при получении метаданных PDF: {e}")
            return {'error': str(e)}


# Глобальный экземпляр
pdf_viewer_service = PDFViewerService()
