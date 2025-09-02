#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для просмотра Excel документов с навигацией по листам
"""

import logging
from typing import Dict, Any, List, Optional
from database.database import SessionLocal
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

class ExcelViewerService:
    """Сервис для просмотра Excel документов с использованием SheetJS"""
    
    def __init__(self):
        self.logger = logger
    
    def get_excel_preview_data(self, document_id: int) -> Dict[str, Any]:
        """Получает данные для предварительного просмотра Excel документа"""
        try:
            with SessionLocal() as db:
                # Получаем информацию о документе
                from database.models import Document
                document = db.query(Document).filter(Document.id == document_id).first()
                
                if not document:
                    return {
                        'error': 'Документ не найден',
                        'local_download_url': f"/viewer/public/excel/{document_id}/file"
                    }
                
                # Получаем информацию о листах
                sheet_info = self._get_sheet_info(db, document_id)
                
                return {
                    'document_id': document_id,
                    'document_name': document.original_filename or document.filename,
                    'file_type': document.file_type,
                    'mime_type': document.mime_type,
                    'sheet_info': sheet_info,
                    'local_download_url': f"/viewer/public/excel/{document_id}/file",
                    'download_url': f"/viewer/public/excel/{document_id}/file"
                }
                
        except Exception as e:
            self.logger.error(f"Ошибка при получении данных Excel документа: {e}")
            return {
                'error': f'Ошибка получения данных: {str(e)}',
                'local_download_url': f"/viewer/public/excel/{document_id}/file"
            }
    
    def _get_sheet_info(self, db: Session, document_id: int) -> Dict[str, Any]:
        """Получает информацию о листах Excel документа"""
        try:
            from database.models import DocumentChunk
            
            chunks = db.query(DocumentChunk).filter(
                DocumentChunk.document_id == document_id
            ).all()
            
            if not chunks:
                return {
                    'sheets': ['Лист1'],
                    'total_sheets': 1,
                    'has_navigation': False
                }
            
            # Извлекаем названия листов из section_name
            sheets = []
            for chunk in chunks:
                if chunk.section_name and chunk.section_name not in sheets:
                    sheets.append(chunk.section_name)
            
            if not sheets:
                sheets = ['Лист1']
            
            return {
                'sheets': sheets,
                'total_sheets': len(sheets),
                'has_navigation': len(sheets) > 1
            }
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении информации о листах: {e}")
            return {
                'sheets': ['Лист1'],
                'total_sheets': 1,
                'has_navigation': False
            }
    
    def _generate_sheet_options(self, sheet_info: Dict[str, Any]) -> str:
        """Генерирует HTML опции для выбора листа"""
        try:
            sheets = sheet_info.get('sheets', ['Лист1'])
            
            options = []
            for i, sheet in enumerate(sheets):
                options.append(f'<option value="{i}">{sheet}</option>')
            
            return '\n'.join(options)
            
        except Exception as e:
            self.logger.error(f"Ошибка при генерации опций листов: {e}")
            return '<option value="0">Лист1</option>'
    
    def create_excel_viewer_html(self, document_data: Dict[str, Any]) -> str:
        """Создает HTML для просмотра Excel документа с использованием SheetJS"""
        try:
            document_name = document_data.get('document_name', 'Excel документ')
            sheet_info = document_data.get('sheet_info', {})
            sheets = sheet_info.get('sheets', ['Лист1'])
            total_sheets = sheet_info.get('total_sheets', 1)
            has_navigation = sheet_info.get('has_navigation', False)
            local_download_url = document_data.get('local_download_url', '')
            download_url = document_data.get('download_url', '')
            
            if not local_download_url:
                local_download_url = f"/viewer/public/excel/{document_data.get('document_id', 'unknown')}/file"
            
            if not download_url:
                download_url = local_download_url
            
            current_sheet = sheets[0] if sheets else 'Лист1'
            
            html = f"""
            <!DOCTYPE html>
            <html lang="ru">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>Excel Viewer - {document_name}</title>
                
                <!-- SheetJS библиотека -->
                <script src="https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js"></script>
                
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
                    
                    .sheet-navigation {{
                        display: flex;
                        align-items: center;
                        gap: 10px;
                    }}
                    
                    .sheet-select {{
                        padding: 8px;
                        border: 1px solid #ddd;
                        border-radius: 4px;
                        font-size: 14px;
                        min-width: 150px;
                    }}
                    
                    .excel-container {{
                        padding: 20px;
                        height: calc(100vh - 200px);
                    }}
                    
                    .excel-viewer {{
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
                    
                    .excel-table {{
                        width: 100%;
                        border-collapse: collapse;
                        margin-top: 20px;
                    }}
                    
                    .excel-table th,
                    .excel-table td {{
                        border: 1px solid #ddd;
                        padding: 8px 12px;
                        text-align: left;
                        font-size: 14px;
                    }}
                    
                    .excel-table th {{
                        background: #f8f9fa;
                        font-weight: 600;
                        color: #333;
                    }}
                    
                    .excel-table tr:nth-child(even) {{
                        background: #f8f9fa;
                    }}
                    
                    .excel-table tr:hover {{
                        background: #e9ecef;
                    }}
                    
                    .sheet-info {{
                        background: #e3f2fd;
                        padding: 15px;
                        border-radius: 6px;
                        margin-bottom: 20px;
                        border-left: 4px solid #2196f3;
                    }}
                    
                    .sheet-info h3 {{
                        color: #1976d2;
                        margin-bottom: 10px;
                    }}
                    
                    .sheet-info p {{
                        margin: 5px 0;
                        color: #424242;
                    }}
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>📊 {document_name}</h1>
                </div>
                
                <div class="controls">
                    <div class="sheet-navigation">
                        <button class="btn" onclick="previousSheet()" id="prevBtn" {'disabled' if not has_navigation else ''}>◀ Предыдущий</button>
                        <select class="sheet-select" id="sheetSelect" onchange="changeSheet()" {'disabled' if not has_navigation else ''}>
                            <option value="0">Загрузка...</option>
                        </select>
                        <button class="btn" onclick="nextSheet()" id="nextBtn" {'disabled' if not has_navigation else ''}>Следующий ▶</button>
                    </div>
                    
                    <div style="margin-left: auto;">
                        <button class="btn" onclick="downloadDocument()">📥 Скачать</button>
                        <button class="btn secondary" onclick="printDocument()">🖨️ Печать</button>
                    </div>
                </div>
                
                <div class="excel-container">
                    <div id="excelViewer" class="excel-viewer">
                        <div class="loading">Загрузка Excel документа...</div>
                    </div>
                </div>
                
                <script>
                    let currentSheetIndex = 0;
                    let currentSheet = '';
                    let workbook = null;
                    
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
                    
                    // Функция для перехода на предыдущий лист
                    function previousSheet() {{
                        if (currentSheetIndex > 0) {{
                            currentSheetIndex--;
                            changeSheet();
                        }}
                    }}
                    
                    // Функция для перехода на следующий лист
                    function nextSheet() {{
                        if (workbook && currentSheetIndex < workbook.SheetNames.length - 1) {{
                            currentSheetIndex++;
                            changeSheet();
                        }}
                    }}
                    
                    // Функция для смены листа
                    function changeSheet() {{
                        const sheetSelect = document.getElementById('sheetSelect');
                        currentSheetIndex = sheetSelect.selectedIndex;
                        displaySheet();
                    }}
                    
                    // Автоматически загружаем Excel документ
                    window.addEventListener('load', function() {{
                        loadExcelDocument();
                    }});
                    
                    // Загружаем Excel документ
                    async function loadExcelDocument() {{
                        try {{
                            const viewer = document.getElementById('excelViewer');
                            viewer.innerHTML = '<div class="loading">Загрузка Excel документа...</div>';
                            
                            // Загружаем файл через fetch
                            const response = await fetch('{local_download_url}');
                            if (!response.ok) {{
                                throw new Error(`HTTP error! status: ${{response.status}}`);
                            }}
                            
                            const arrayBuffer = await response.arrayBuffer();
                            
                            try {{
                                // Парсим Excel файл с помощью SheetJS
                                workbook = XLSX.read(arrayBuffer, {{ type: 'array' }});
                                
                                if (!workbook || !workbook.SheetNames || workbook.SheetNames.length === 0) {{
                                    throw new Error('Не удалось прочитать Excel файл');
                                }}
                                
                                // Обновляем информацию о листах
                                updateSheetInfo();
                                
                                // Отображаем первый лист
                                displaySheet();
                                
                            }} catch (xlsxError) {{
                                console.warn('SheetJS не смог обработать Excel файл:', xlsxError);
                                
                                // Fallback для старых .xls файлов
                                const fileSize = (arrayBuffer.byteLength / 1024).toFixed(2);
                                viewer.innerHTML = `
                                    <div class="section-info">
                                        <h3>📊 Excel документ загружен</h3>
                                        <p><strong>Файл:</strong> {document_name}</p>
                                        <p><strong>Размер:</strong> ${{fileSize}} КБ</p>
                                        <p><strong>Статус:</strong> Файл успешно загружен</p>
                                        <p><strong>Формат:</strong> Excel документ (.xls/.xlsx)</p>
                                        <div style="margin-top: 20px;">
                                            <button class="btn" onclick="downloadDocument()">📥 Скачать документ</button>
                                            <button class="btn secondary" onclick="printDocument()">🖨️ Печать</button>
                                        </div>
                                        <p style="margin-top: 20px; color: #666;">
                                            <em>Для просмотра содержимого Excel документа используйте Microsoft Excel, LibreOffice Calc или другие совместимые приложения.</em>
                                        </p>
                                        <p style="margin-top: 10px; color: #888; font-size: 12px;">
                                            <em>Примечание: Автоматический рендеринг не удался, возможно из-за формата файла (.xls вместо .xlsx)</em>
                                        </p>
                                    </div>
                                `;
                                return; // Выходим из функции
                            }}
                            
                        }} catch (error) {{
                            console.error('Ошибка загрузки Excel:', error);
                            showError('Ошибка загрузки Excel документа: ' + error.message);
                        }}
                    }}
                    
                    // Обновляем информацию о листах
                    function updateSheetInfo() {{
                        if (workbook && workbook.SheetNames) {{
                            const sheetSelect = document.getElementById('sheetSelect');
                            sheetSelect.innerHTML = '';
                            
                            workbook.SheetNames.forEach((sheetName, index) => {{
                                const option = document.createElement('option');
                                option.value = index;
                                option.textContent = sheetName;
                                sheetSelect.appendChild(option);
                            }});
                            
                            // Обновляем навигацию
                            const hasNav = workbook.SheetNames.length > 1;
                            document.getElementById('prevBtn').disabled = !hasNav;
                            document.getElementById('nextBtn').disabled = !hasNav;
                            document.getElementById('sheetSelect').disabled = !hasNav;
                        }}
                    }}
                    
                    // Отображаем выбранный лист
                    function displaySheet() {{
                        if (!workbook) return;
                        
                        try {{
                            const viewer = document.getElementById('excelViewer');
                            const sheetName = workbook.SheetNames[currentSheetIndex];
                            currentSheet = sheetName;
                            
                            // Получаем данные листа
                            const worksheet = workbook.Sheets[sheetName];
                            if (!worksheet) {{
                                throw new Error(`Лист "${{sheetName}}" не найден`);
                            }}
                            
                            // Конвертируем в HTML таблицу
                            const htmlTable = XLSX.utils.sheet_to_html(worksheet, {{
                                editable: false,
                                header: true
                            }});
                            
                            // Создаем HTML с информацией о листе
                            const sheetInfo = `
                                <div class="sheet-info">
                                    <h3>📋 Лист: ${{sheetName}}</h3>
                                    <p><strong>Номер листа:</strong> ${{currentSheetIndex + 1}} из ${{workbook.SheetNames.length}}</p>
                                    <p><strong>Файл:</strong> {document_name}</p>
                                </div>
                            `;
                            
                            viewer.innerHTML = sheetInfo + htmlTable;
                            
                            // Обновляем выбранный лист в селекте
                            const sheetSelect = document.getElementById('sheetSelect');
                            if (sheetSelect) {{
                                sheetSelect.selectedIndex = currentSheetIndex;
                            }}
                            
                        }} catch (error) {{
                            console.error('Ошибка отображения листа:', error);
                            showError('Ошибка отображения листа: ' + error.message);
                        }}
                    }}
                    
                    // Показываем ошибку
                    function showError(message) {{
                        const viewer = document.getElementById('excelViewer');
                        viewer.innerHTML = `
                            <div class="error">
                                <h3>❌ Ошибка</h3>
                                <p>${{message}}</p>
                                <button class="btn" onclick="loadExcelDocument()" style="margin-top: 20px;">🔄 Попробовать снова</button>
                            </div>
                        `;
                    }}
                </script>
            </body>
            </html>
            """
            
            return html
            
        except Exception as e:
            self.logger.error(f"Ошибка при создании HTML Excel просмотрщика: {e}")
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
excel_viewer_service = ExcelViewerService()
