#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для генерации ссылок на исходные документы с поддержкой навигации
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from config import settings
import urllib.parse

logger = logging.getLogger(__name__)


class SourceLinker:
    """Сервис для создания ссылок на исходные документы с навигацией"""
    
    def __init__(self):
        self.supabase_url = settings.supabase_url
        self.storage_bucket = "rag-files"
        
        # Настройки для различных типов документов
        self.document_viewers = {
            'pdf': {
                'web_viewer': 'pdf',  # PDF.js
                'mobile_friendly': True,
                'navigation_support': True
            },
            'docx': {
                'web_viewer': 'office_online',
                'mobile_friendly': True,
                'navigation_support': False
            },
            'xlsx': {
                'web_viewer': 'google_sheets',
                'mobile_friendly': True,
                'navigation_support': True
            },
            'pptx': {
                'web_viewer': 'office_online',
                'mobile_friendly': True,
                'navigation_support': False
            }
        }
    
    def generate_document_links(self, search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Генерирует ссылки на исходные документы для результатов поиска"""
        try:
            enhanced_results = []
            
            for result in search_results:
                enhanced_result = result.copy()
                
                # Генерируем ссылку на документ
                document_link = self._create_document_link(result)
                enhanced_result['document_link'] = document_link
                
                # Генерируем ссылку на конкретную страницу/лист
                specific_link = self._create_specific_link(result)
                enhanced_result['specific_link'] = specific_link
                
                # Генерируем ссылку на веб-просмотр
                web_viewer_link = self._create_web_viewer_link(result)
                enhanced_result['web_viewer_link'] = web_viewer_link
                
                # Форматируем метаданные для отображения
                display_info = self._format_display_info(result)
                enhanced_result['display_info'] = display_info
                
                # Добавляем инструкции по навигации
                navigation_guide = self._create_navigation_guide(result)
                enhanced_result['navigation_guide'] = navigation_guide
                
                enhanced_results.append(enhanced_result)
            
            logger.info(f"Сгенерировано {len(enhanced_results)} ссылок на документы с навигацией")
            return enhanced_results
            
        except Exception as e:
            logger.error(f"Ошибка при генерации ссылок: {e}")
            return search_results
    
    def _create_document_link(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Создает ссылку на исходный документ"""
        try:
            document_id = result.get('document_id')
            document_name = result.get('document_name', '')
            file_type = result.get('file_type', '')
            file_path = result.get('file_path', '')
            
            if not document_id:
                return {}
            
            # Создаем прямую ссылку на скачивание из Supabase
            if file_path:
                download_url = f"{self.supabase_url}/storage/v1/object/public/{self.storage_bucket}/{file_path}"
            else:
                download_url = f"{self.supabase_url}/storage/v1/object/public/{self.storage_bucket}/{document_name}"
            
            # API endpoint для скачивания
            api_url = f"/api/documents/{document_id}/download"
            
            return {
                'download_url': download_url,
                'api_url': api_url,
                'document_id': document_id,
                'document_name': document_name,
                'file_type': file_type,
                'file_extension': self._get_file_extension(file_type),
                'direct_download': True
            }
            
        except Exception as e:
            logger.error(f"Ошибка при создании ссылки на документ: {e}")
            return {}
    
    def _create_specific_link(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Создает ссылку на конкретную страницу/лист/секцию"""
        try:
            document_id = result.get('document_id')
            page_number = result.get('page_number')
            sheet_name = result.get('sheet_name')
            section_name = result.get('section_name')
            chunk_index = result.get('chunk_index', 0)
            file_type = result.get('file_type', '')
            
            if not document_id:
                return {}
            
            specific_info = {
                'document_id': document_id,
                'chunk_index': chunk_index,
                'has_navigation': False
            }
            
            # Для PDF документов - ссылка на страницу
            if page_number and file_type in ['pdf', 'application/pdf']:
                specific_info.update({
                    'type': 'page',
                    'value': page_number,
                    'display': f"Страница {page_number}",
                    'url': f"/api/documents/{document_id}/page/{page_number}",
                    'pdf_anchor': f"#page={page_number}",
                    'has_navigation': True
                })
            
            # Для Excel документов - ссылка на лист
            elif sheet_name and file_type in ['xlsx', 'xls', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
                specific_info.update({
                    'type': 'sheet',
                    'value': sheet_name,
                    'display': f"Лист: {sheet_name}",
                    'url': f"/api/documents/{document_id}/sheet/{urllib.parse.quote(sheet_name)}",
                    'has_navigation': True
                })
            
            # Для Word документов - ссылка на раздел
            elif section_name and file_type in ['docx', 'doc', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                specific_info.update({
                    'type': 'section',
                    'value': section_name,
                    'display': f"Раздел: {section_name}",
                    'url': f"/api/documents/{document_id}/section/{urllib.parse.quote(section_name)}",
                    'has_navigation': False  # Word не поддерживает прямую навигацию
                })
            
            # Для PowerPoint - ссылка на слайд
            elif page_number and file_type in ['pptx', 'ppt', 'application/vnd.openxmlformats-officedocument.presentationml.presentation']:
                specific_info.update({
                    'type': 'slide',
                    'value': page_number,
                    'display': f"Слайд {page_number}",
                    'url': f"/api/documents/{document_id}/slide/{page_number}",
                    'has_navigation': False
                })
            
            return specific_info
            
        except Exception as e:
            logger.error(f"Ошибка при создании специфичной ссылки: {e}")
            return {}
    
    def _create_web_viewer_link(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Создает ссылку на веб-просмотрщик документа"""
        try:
            document_id = result.get('document_id')
            file_type = result.get('file_type', '')
            file_path = result.get('file_path', '')
            document_name = result.get('document_name', '')
            
            if not document_id:
                return {}
            
            viewer_info = {
                'document_id': document_id,
                'available': False,
                'viewer_type': None,
                'url': None
            }
            
            # Определяем тип просмотрщика
            if file_type in ['pdf', 'application/pdf']:
                # PDF.js просмотрщик
                viewer_info.update({
                    'available': True,
                    'viewer_type': 'pdf_js',
                    'url': f"/viewer/public/pdf/{document_id}",
                    'mobile_friendly': True,
                    'supports_navigation': True
                })
            
            elif file_type in ['xlsx', 'xls', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
                # Excel просмотрщик
                viewer_info.update({
                    'available': True,
                    'viewer_type': 'excel_viewer',
                    'url': f"/viewer/public/excel/{document_id}",
                    'mobile_friendly': True,
                    'supports_navigation': True
                })
            
            elif file_type in ['docx', 'doc', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
                # Word просмотрщик
                viewer_info.update({
                    'available': True,
                    'viewer_type': 'word_viewer',
                    'url': f"/viewer/public/word/{document_id}",
                    'mobile_friendly': True,
                    'supports_navigation': True
                })
            
            elif file_type in ['pptx', 'ppt', 'application/vnd.openxmlformats-officedocument.presentationml.presentation']:
                # PowerPoint просмотрщик
                viewer_info.update({
                    'available': True,
                    'viewer_type': 'powerpoint_viewer',
                    'url': f"/viewer/public/powerpoint/{document_id}",
                    'mobile_friendly': True,
                    'supports_navigation': True
                })
            
            return viewer_info
            
        except Exception as e:
            logger.error(f"Ошибка при создании ссылки на веб-просмотрщик: {e}")
            return {}
    
    def _create_navigation_guide(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Создает инструкции по навигации к нужному месту в документе"""
        try:
            file_type = result.get('file_type', '')
            page_number = result.get('page_number')
            sheet_name = result.get('sheet_name')
            section_name = result.get('section_name')
            
            guide = {
                'file_type': file_type,
                'instructions': [],
                'quick_navigation': False
            }
            
            # Инструкции для PDF
            if file_type in ['pdf', 'application/pdf'] and page_number:
                guide['instructions'] = [
                    "1. Скачайте PDF документ",
                    f"2. Откройте документ в любом PDF просмотрщике",
                    f"3. Перейдите на страницу {page_number}",
                    "4. Или используйте веб-просмотрщик для прямого перехода"
                ]
                guide['quick_navigation'] = True
            
            # Инструкции для Excel
            elif file_type in ['xlsx', 'xls'] and sheet_name:
                guide['instructions'] = [
                    "1. Скачайте Excel документ",
                    "2. Откройте в Microsoft Excel, LibreOffice Calc или Google Sheets",
                    f"3. Перейдите на лист '{sheet_name}'",
                    "4. Или используйте веб-просмотрщик (если доступен)"
                ]
                guide['quick_navigation'] = True
            
            # Инструкции для Word
            elif file_type in ['docx', 'doc'] and section_name:
                guide['instructions'] = [
                    "1. Скачайте Word документ",
                    "2. Откройте в Microsoft Word, LibreOffice Writer или Google Docs",
                    f"3. Используйте поиск (Ctrl+F) для поиска раздела '{section_name}'",
                    "4. Или используйте веб-просмотрщик Office Online"
                ]
                guide['quick_navigation'] = False
            
            # Инструкции для PowerPoint
            elif file_type in ['pptx', 'ppt'] and page_number:
                guide['instructions'] = [
                    "1. Скачайте PowerPoint презентацию",
                    "2. Откройте в Microsoft PowerPoint, LibreOffice Impress или Google Slides",
                    f"3. Перейдите на слайд {page_number}",
                    "4. Или используйте веб-просмотрщик Office Online"
                ]
                guide['quick_navigation'] = False
            
            # Общие инструкции
            else:
                guide['instructions'] = [
                    "1. Скачайте документ по ссылке выше",
                    "2. Откройте в соответствующем приложении",
                    "3. Используйте поиск для нахождения нужной информации"
                ]
            
            return guide
            
        except Exception as e:
            logger.error(f"Ошибка при создании инструкций по навигации: {e}")
            return {}
    
    def _format_display_info(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Форматирует метаданные для отображения"""
        try:
            file_type = result.get('file_type', '')
            page_number = result.get('page_number')
            sheet_name = result.get('sheet_name')
            section_name = result.get('section_name')
            
            display_info = {
                'file_type_icon': self._get_file_type_icon(file_type),
                'file_type_name': self._get_file_type_name(file_type),
                'navigation_hint': None,
                'quick_access': False
            }
            
            # Подсказка для навигации
            if page_number:
                display_info['navigation_hint'] = f"Страница {page_number}"
                display_info['quick_access'] = True
            elif sheet_name:
                display_info['navigation_hint'] = f"Лист: {sheet_name}"
                display_info['quick_access'] = True
            elif section_name:
                display_info['navigation_hint'] = f"Раздел: {section_name}"
                display_info['quick_access'] = False
            
            return display_info
            
        except Exception as e:
            logger.error(f"Ошибка при форматировании информации для отображения: {e}")
            return {}
    
    def _get_file_extension(self, file_type: str) -> str:
        """Получает расширение файла по MIME типу"""
        extensions = {
            'application/pdf': '.pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '.docx',
            'application/msword': '.doc',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '.xlsx',
            'application/vnd.ms-excel': '.xls',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': '.pptx',
            'application/vnd.ms-powerpoint': '.ppt',
            'text/plain': '.txt',
            'text/markdown': '.md'
        }
        return extensions.get(file_type, '')
    
    def _get_file_type_icon(self, file_type: str) -> str:
        """Получает иконку для типа файла"""
        icons = {
            'application/pdf': '📄',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': '📝',
            'application/msword': '📝',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': '📊',
            'application/vnd.ms-excel': '📊',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': '📽️',
            'application/vnd.ms-powerpoint': '📽️',
            'text/plain': '📄',
            'text/markdown': '📝'
        }
        return icons.get(file_type, '📄')
    
    def _get_file_type_name(self, file_type: str) -> str:
        """Получает человекочитаемое название типа файла"""
        names = {
            'application/pdf': 'PDF документ',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word документ',
            'application/msword': 'Word документ',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'Excel таблица',
            'application/vnd.ms-excel': 'Excel таблица',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'PowerPoint презентация',
            'application/vnd.ms-powerpoint': 'PowerPoint презентация',
            'text/plain': 'Текстовый файл',
            'text/markdown': 'Markdown документ'
        }
        return names.get(file_type, 'Документ')
    
    def get_document_preview_url(self, document_id: int, file_type: str) -> Optional[str]:
        """Получает URL для предварительного просмотра документа"""
        try:
            # Нормализуем file_type
            file_type = file_type.lower().strip()
            
            # Убираем точку в начале, если есть
            if file_type.startswith('.'):
                file_type = file_type[1:]
            
            # Убираем MIME type prefix, если есть
            if file_type.startswith('application/'):
                file_type = file_type.split('/')[-1]
            
            logger.info(f"🔗 Создаем URL для document_id={document_id}, file_type='{file_type}'")
            
            if file_type in ['pdf']:
                url = f"/viewer/public/pdf/{document_id}"
                logger.info(f"✅ PDF URL: {url}")
                return url
            elif file_type in ['xlsx', 'xls']:
                url = f"/viewer/public/excel/{document_id}"
                logger.info(f"✅ Excel URL: {url}")
                return url
            elif file_type in ['docx', 'doc']:
                url = f"/viewer/public/word/{document_id}"
                logger.info(f"✅ Word URL: {url}")
                return url
            elif file_type in ['pptx', 'ppt']:
                url = f"/viewer/public/powerpoint/{document_id}"
                logger.info(f"✅ PowerPoint URL: {url}")
                return url
            else:
                logger.warning(f"⚠️ Неподдерживаемый тип файла: {file_type}")
                return None
        except Exception as e:
            logger.error(f"Ошибка при получении URL предварительного просмотра: {e}")
            return None
    
    def format_response_with_sources(self, response: str, sources: List[Dict[str, Any]]) -> str:
        """Форматирует ответ AI с источниками для отображения пользователю"""
        try:
            logger.info(f"🔍 format_response_with_sources вызван с {len(sources)} источниками")
            if not sources:
                logger.info("📝 Источники отсутствуют, возвращаем исходный ответ")
                return response
            
            # Добавляем информацию об источниках в конец ответа
            formatted_response = response.strip()
            
            if not formatted_response.endswith('\n'):
                formatted_response += '\n\n'
            
            formatted_response += "📚 **Источники информации:**\n\n"
            
            for i, source in enumerate(sources, 1):
                logger.info(f"🔍 Обрабатываем источник {i}: {source}")
                
                document_name = source.get('document_name', f'Документ {source.get("document_id", "N/A")}')
                page_number = source.get('page_number')
                sheet_name = source.get('sheet_name')
                section_name = source.get('section_name')
                
                # Формируем строку с источником
                source_line = f"{i}. **{document_name}**"
                
                # Добавляем специфичную информацию
                if page_number:
                    source_line += f" (страница {page_number})"
                elif sheet_name:
                    source_line += f" (лист '{sheet_name}')"
                elif section_name:
                    source_line += f" (раздел '{section_name}')"
                
                # Добавляем ссылку на просмотр, если доступна
                document_id = source.get('document_id')
                file_type = source.get('file_type', '')
                mime_type = source.get('mime_type', '')
                
                # Определяем тип файла для создания ссылки
                file_type_for_url = file_type or mime_type
                
                # Очищаем file_type от точки (если есть)
                if file_type_for_url and file_type_for_url.startswith('.'):
                    file_type_for_url = file_type_for_url[1:]  # Убираем точку
                
                # Убираем MIME type prefix, если есть
                if file_type_for_url and file_type_for_url.startswith('application/'):
                    file_type_for_url = file_type_for_url.split('/')[-1]
                
                logger.info(f"🔗 Создаем ссылку для document_id={document_id}, file_type='{file_type}', mime_type='{mime_type}', file_type_for_url='{file_type_for_url}'")
                
                if document_id and file_type_for_url:
                    preview_url = self.get_document_preview_url(document_id, file_type_for_url)
                    if preview_url:
                        source_line += f" - [Просмотр]({preview_url})"
                        logger.info(f"✅ Добавлена ссылка: {preview_url}")
                    else:
                        logger.warning(f"⚠️ Не удалось создать URL для {file_type_for_url}")
                else:
                    logger.warning(f"⚠️ Недостаточно данных для создания ссылки: document_id={document_id}, file_type_for_url='{file_type_for_url}'")
                
                formatted_response += source_line + "\n"
            
            return formatted_response
            
        except Exception as e:
            logger.error(f"Ошибка при форматировании ответа с источниками: {e}")
            return response


# Глобальный экземпляр
source_linker = SourceLinker()
