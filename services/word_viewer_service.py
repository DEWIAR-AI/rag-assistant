#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для просмотра Word документов с навигацией по разделам
"""

import logging
from typing import Dict, Any, List, Optional
from database.database import SessionLocal
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class WordViewerService:
    """Сервис для просмотра Word документов с использованием docx-preview"""
    
    def __init__(self):
        self.logger = logger
    
    def get_word_preview_data(self, document_id: int) -> Dict[str, Any]:
        """Получает данные для предварительного просмотра Word документа"""
        try:
            with SessionLocal() as db:
                # Получаем информацию о документе
                from database.models import Document
                document = db.query(Document).filter(Document.id == document_id).first()
                
                if not document:
                    return {
                        'error': 'Документ не найден',
                        'local_download_url': f"/viewer/public/word/{document_id}/file"
                    }
                
                # Получаем информацию о разделах
                section_info = self._get_section_info(db, document_id)
                
                return {
                    'document_id': document_id,
                    'document_name': document.original_filename or document.filename,
                    'file_type': document.file_type,
                    'mime_type': document.mime_type,
                    'section_info': section_info,
                    'local_download_url': f"/viewer/public/word/{document_id}/file",
                    'download_url': f"/viewer/public/word/{document_id}/file"
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка при получении данных Word документа: {e}")
            return {
                'error': f'Ошибка получения данных: {str(e)}',
                'local_download_url': f"/viewer/public/word/{document_id}/file"
            }
    
    def _get_section_info(self, db: Session, document_id: int) -> Dict[str, Any]:
        """Получает информацию о разделах Word документа"""
        try:
            from database.models import DocumentChunk
            
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).all()
            
            if not chunks:
                return {
                    'sections': ['Раздел 1'],
                    'total_sections': 1,
                    'has_navigation': False
                }
            
            # Извлекаем названия разделов из section_name
            sections = []
            for chunk in chunks:
                if chunk.section_name and chunk.section_name not in sections:
                    sections.append(chunk.section_name)
            
            if not sections:
                sections = ['Раздел 1']
            
            return {
                'sections': sections,
                'total_sections': len(sections),
                'has_navigation': len(sections) > 1
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о разделах: {e}")
            return {
                'sections': ['Раздел 1'],
                'total_sections': 1,
                'has_navigation': False
            }
    
    def _generate_section_options(self, section_info: Dict[str, Any]) -> str:
        """Генерирует HTML опции для выбора раздела"""
        try:
            sections = section_info.get('sections', ['Раздел 1'])
            
            options = []
            for i, section in enumerate(sections):
                options.append(f'<option value="{i}">{section}</option>')
            
            return '\n'.join(options)
            
        except Exception as e:
            self.logger.error(f"Ошибка при генерации опций разделов: {e}")
            return '<option value="0">Раздел 1</option>'
    
    def create_word_viewer_html(self, document_data: Dict[str, Any]) -> str:
        """Создает HTML для просмотра Word документа с использованием docx-preview"""
        try:
            document_name = document_data.get('document_name', 'Word документ')
            section_info = document_data.get('section_info', {})
            sections = section_info.get('sections', ['Раздел 1'])
            total_sections = section_info.get('total_sections', 1)
            has_navigation = section_info.get('has_navigation', False)
            local_download_url = document_data.get('local_download_url', '')
            download_url = document_data.get('download_url', '')
            
            if not local_download_url:
                local_download_url = f"/viewer/public/word/{document_data.get('document_id', 'unknown')}/file"
            
            if not download_url:
                download_url = local_download_url
            
            current_section = sections[0] if sections else 'Раздел 1'
            
            html = f"""
            <!DOCTYPE html>
            <html lang="ru">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Word Viewer - {document_name}</title>
                
                <!-- mammoth.js библиотека для Word -->
                <script src="https://cdnjs.cloudflare.com/ajax/libs/mammoth/1.6.0/mammoth.browser.min.js"></script>
                <!-- Fallback библиотека -->
                <script>
                    // Проверяем загрузку mammoth.js
                    window.addEventListener('load', function() {{
                        if (typeof mammoth === 'undefined') {{
                            console.warn('mammoth.js не загрузился, используем fallback');
                        }}
                    }});
                </script>
                
                <style>
                    * {{
                        margin: 0;
                        padding: 0;
                        box-sizing: border-box;
                    }}
                    
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh;
                    }}
                    
                    .header {{
                        background: rgba(255, 255, 255, 0.95);
                        padding: 20px;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        text-align: center;
                    }}
                    
                    .header h1 {{
                        color: #333;
                        font-size: 24px;
                        font-weight: 600;
                    }}
                    
                    .controls {{
                        background: rgba(255, 255, 255, 0.95);
                        padding: 15px 20px;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                        flex-wrap: wrap;
                        gap: 15px;
                    }}
                    
                    .btn {{
                        background: #667eea;
                        color: white;
                        border: none;
                        padding: 10px 20px;
                        border-radius: 6px;
                        cursor: pointer;
                        font-size: 14px;
                        font-weight: 500;
                        transition: all 0.3s ease;
                        text-decoration: none;
                        display: inline-block;
                    }}
                    
                    .btn:hover {{
                        background: #5a6fd8;
                        transform: translateY(-2px);
                    }}
                    
                    .btn.secondary {{
                        background: #6c757d;
                    }}
                    
                    .btn.secondary:hover {{
                        background: #5a6268;
                    }}
                    
                    .btn:disabled {{
                        background: #ccc;
                        cursor: not-allowed;
                        transform: none;
                    }}
                    
                    .section-navigation {{
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    }}
                    
                    .section-select {{
                        padding: 8px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        font-size: 14px;
                        min-width: 150px;
                    }}
                    
                    .word-container {{
                        padding: 20px;
                        height: calc(100vh - 200px);
                    }}
                    
                    .word-viewer {{
                        background: white;
                        border-radius: 8px;
                        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
                        height: 100%;
                        overflow: auto;
                        padding: 20px;
                    }}
                    
                    .loading {{
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        height: 100%;
                        font-size: 18px;
                        color: #666;
                    }}
                    
                    .error {{
                        padding: 40px;
                        text-align: center;
                        color: #dc3545;
                    }}
                    
                    .error h3 {{
                        color: #dc3545;
                        margin-bottom: 20px;
                    }}
                    
                    .section-info {{
                        background: #e3f2fd;
                        padding: 15px;
                        border-radius: 6px;
                        margin-bottom: 20px;
                        border-left: 4px solid #2196f3;
                    }}
                    
                    .section-info h3 {{
                        color: #1976d2;
                        margin-bottom: 10px;
                    }}
                    
                    .section-info p {{
                        margin: 5px 0;
                        color: #424242;
                    }}
                    
                    .docx-content {{
                        line-height: 1.6;
                        color: #333;
                    }}
                    
                    .docx-content h1, .docx-content h2, .docx-content h3 {{
                        color: #1976d2;
                        margin: 20px 0 10px 0;
                    }}
                    
                    .docx-content p {{
                        margin: 10px 0;
                    }}
                    
                    .docx-content table {{
                        border-collapse: collapse;
                        width: 100%;
                        margin: 15px 0;
                    }}
                    
                    .docx-content th, .docx-content td {{
                        border: 1px solid #ddd;
                        padding: 8px 12px;
                        text-align: left;
                    }}
                    
                    .docx-content th {{
                        background: #f8f9fa;
                        font-weight: 600;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>📄 {document_name}</h1>
                </div>
                
                <div class="controls">
                    <div style="margin-left: auto;">
                        <button class="btn" onclick="downloadDocument()">📥 Скачать</button>
                        <button class="btn secondary" onclick="printDocument()">🖨️ Печать</button>
                    </div>
                </div>
                
                <div class="word-container">
                    <div id="wordViewer" class="word-viewer">
                        <div class="loading">Загрузка Word документа...</div>
                    </div>
                </div>
                
                <script>
                    let documentContent = null;
                    
                    // Функция для скачивания документа
                    function downloadDocument() {{
                        const link = document.createElement('a');
                        link.href = '{download_url}';
                        link.download = '{document_name}';
                        document.body.appendChild(link);
                        link.click();
                        document.body.removeChild(link);
                    }}
                    
                    // Функция для печати
                    function printDocument() {{
                        window.print();
                    }}
                    
                    // Функции навигации пока не реализованы для Word
                    
                    // Автоматически загружаем Word документ
                    window.addEventListener('load', function() {{
                        loadWordDocument();
                    }});
                    
                    // Загружаем Word документ
                    async function loadWordDocument() {{
                        try {{
                            const viewer = document.getElementById('wordViewer');
                            viewer.innerHTML = '<div class="loading">Загрузка Word документа...</div>';
                            
                            // Загружаем файл через fetch
                            const response = await fetch('{local_download_url}');
                            if (!response.ok) {{
                                throw new Error(`HTTP error! status: ${{response.status}}`);
                            }}
                            
                            const arrayBuffer = await response.arrayBuffer();
                            
                            // Проверяем, загрузилась ли библиотека mammoth
                            if (typeof mammoth === 'undefined') {{
                                throw new Error('Библиотека mammoth.js не загрузилась');
                            }}
                            
                            try {{
                                // Пытаемся рендерить Word документ с помощью mammoth.js
                                const result = await mammoth.convertToHtml({{arrayBuffer: arrayBuffer}});
                                
                                if (result && result.value) {{
                                    // Вставляем HTML контент
                                    viewer.innerHTML = result.value;
                                }} else {{
                                    throw new Error('Не удалось отрендерить Word документ');
                                }}
                            }} catch (mammothError) {{
                                console.warn('Mammoth.js не смог обработать документ:', mammothError);
                                
                                // Fallback: показываем информацию о файле
                                const fileSize = (arrayBuffer.byteLength / 1024).toFixed(2);
                                viewer.innerHTML = `
                                    <div class="section-info">
                                        <h3>📋 Word документ загружен</h3>
                                        <p><strong>Файл:</strong> {document_name}</p>
                                        <p><strong>Размер:</strong> ${{fileSize}} КБ</p>
                                        <p><strong>Статус:</strong> Файл успешно загружен</p>
                                        <p><strong>Формат:</strong> Word документ (.doc/.docx)</p>
                                        <div style="margin-top: 20px;">
                                            <button class="btn" onclick="downloadDocument()">📥 Скачать документ</button>
                                            <button class="btn secondary" onclick="printDocument()">🖨️ Печать</button>
                                        </div>
                                        <p style="margin-top: 20px; color: #666;">
                                            <em>Для просмотра содержимого Word документа используйте Microsoft Word, LibreOffice или другие совместимые приложения.</em>
                                        </p>
                                        <p style="margin-top: 10px; color: #888; font-size: 12px;">
                                            <em>Примечание: Автоматический рендеринг не удался, возможно из-за формата файла (.doc вместо .docx)</em>
                                        </p>
                                    </div>
                                `;
                                return; // Выходим из функции, так как уже показали fallback
                            }}
                            
                            // Добавляем информацию о документе прямо в начало
                            const infoDiv = document.createElement('div');
                            infoDiv.className = 'section-info';
                            infoDiv.innerHTML = `
                                <h3>📋 Word документ загружен</h3>
                                <p><strong>Файл:</strong> {document_name}</p>
                                <p><strong>Статус:</strong> Успешно отрендерен</p>
                            `;
                            viewer.insertBefore(infoDiv, viewer.firstChild);
                            
                        }} catch (error) {{
                            console.error('Ошибка загрузки Word:', error);
                            showError('Ошибка загрузки Word документа: ' + error.message);
                        }}
                    }}
                    
                    // Функция addDocumentInfo больше не используется
                    
                    // Показываем ошибку
                    function showError(message) {{
                        const viewer = document.getElementById('wordViewer');
                        viewer.innerHTML = `
                            <div class="error">
                                <h3>❌ Ошибка</h3>
                                <p>${{message}}</p>
                                <button class="btn" onclick="loadWordDocument()" style="margin-top: 20px;">🔄 Попробовать снова</button>
                            </div>
                        `;
                    }}
                </script>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании HTML Word просмотрщика: {e}")
            return f"""
            <!DOCTYPE html>
            <html>
            <head><title>Ошибка</title></head>
            <body>
                <h1>Ошибка создания просмотрщика</h1>
                <p>{str(e)}</p>
            </body>
            </html>
            """

# Создаем экземпляр сервиса
word_viewer_service = WordViewerService()
