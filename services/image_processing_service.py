#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Сервис для обработки изображений в чате
"""

import base64
import io
import logging
import tempfile
import os
from typing import Dict, Any, List, Optional, Tuple
from PIL import Image
import mimetypes

# OCR imports
try:
    from paddleocr import PaddleOCR
    PADDLE_AVAILABLE = True
except ImportError:
    PADDLE_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

logger = logging.getLogger(__name__)


class ImageProcessingService:
    """Сервис для обработки изображений в чате"""
    
    def __init__(self):
        self.ocr_engine = None
        self._initialize_ocr()
    
    def _initialize_ocr(self):
        """Инициализация OCR движка"""
        try:
            logger.info("🔧 Initializing OCR engines...")
            
            # Временно отключаем PaddleOCR из-за проблем с путями к моделям
            logger.info("PaddleOCR temporarily disabled due to model path issues")
            
            if TESSERACT_AVAILABLE:
                try:
                    logger.info("🔄 Trying Tesseract...")
                    version = pytesseract.get_tesseract_version()
                    logger.info(f"✅ Tesseract version {version} found")
                    self.ocr_engine = 'tesseract'
                    logger.info("✅ Tesseract OCR initialized successfully")
                    return
                except Exception as e:
                    logger.warning(f"Tesseract not available: {e}")
                    self.ocr_engine = None
            
            logger.warning("❌ No OCR engines available")
            logger.info(f"PADDLE_AVAILABLE: {PADDLE_AVAILABLE}")
            logger.info(f"TESSERACT_AVAILABLE: {TESSERACT_AVAILABLE}")
                
        except Exception as e:
            logger.error(f"OCR initialization failed: {e}")
            self.ocr_engine = None
    
    def process_chat_images(self, images: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Обрабатывает изображения из чата и извлекает информацию"""
        if not images:
            logger.info("No images to process")
            return {}
        
        logger.info(f"Processing {len(images)} images...")
        
        results = {
            'total_images': len(images),
            'processed_images': 0,
            'extracted_text': [],
            'image_analysis': [],
            'errors': []
        }
        
        for i, image_data in enumerate(images):
            try:
                logger.info(f"Processing image {i+1}/{len(images)}")
                # Обрабатываем каждое изображение
                image_result = self._process_single_image(image_data, i)
                results['image_analysis'].append(image_result)
                results['processed_images'] += 1
                
                # Добавляем извлеченный текст
                if image_result.get('extracted_text'):
                    results['extracted_text'].append(image_result['extracted_text'])
                    logger.info(f"Image {i+1} extracted text length: {len(image_result['extracted_text'])}")
                else:
                    logger.warning(f"Image {i+1} no text extracted")
                    
            except Exception as e:
                error_msg = f"Error processing image {i}: {str(e)}"
                logger.error(error_msg)
                results['errors'].append(error_msg)
        
        # Объединяем весь извлеченный текст
        if results['extracted_text']:
            results['combined_text'] = '\n\n'.join(results['extracted_text'])
            logger.info(f"Combined text length: {len(results['combined_text'])}")
        
        logger.info(f"Processing complete: {results['processed_images']}/{results['total_images']} images processed")
        return results
    
    def _process_single_image(self, image_data, index: int) -> Dict[str, Any]:
        """Обрабатывает одно изображение"""
        try:
            # Проверяем, является ли image_data Pydantic моделью или словарем
            if hasattr(image_data, 'image_data'):
                # Pydantic модель
                image_bytes = base64.b64decode(image_data.image_data)
                image_type = image_data.image_type
                description = image_data.description
            else:
                # Словарь
                image_bytes = base64.b64decode(image_data['image_data'])
                image_type = image_data.get('image_type', 'image/jpeg')
                description = image_data.get('description', '')
            
            logger.info(f"Image {index}: decoded {len(image_bytes)} bytes")
            
            # Создаем временный файл
            with tempfile.NamedTemporaryFile(delete=False, suffix=self._get_file_extension(image_type)) as temp_file:
                temp_file.write(image_bytes)
                temp_file_path = temp_file.name
                logger.info(f"Image {index}: saved to {temp_file_path}")
            
            # Проверяем, что файл создался и содержит данные
            if os.path.exists(temp_file_path):
                file_size = os.path.getsize(temp_file_path)
                logger.info(f"Image {index}: file exists, size={file_size} bytes")
            else:
                logger.error(f"Image {index}: file was not created!")
                return {
                    'index': index,
                    'error': 'Temporary file was not created',
                    'extracted_text': '',
                    'text_confidence': 0.0
                }
            
            try:
                # Открываем изображение
                image = Image.open(io.BytesIO(image_bytes))
                logger.info(f"Image {index}: opened successfully, size={image.size}, mode={image.mode}")
                
                # Анализируем изображение
                analysis = {
                    'index': index,
                    'image_type': image_type,
                    'dimensions': image.size,
                    'mode': image.mode,
                    'description': description,
                    'extracted_text': '',
                    'text_confidence': 0.0,
                    'objects_detected': [],
                    'processing_time': 0.0
                }
                
                # Извлекаем текст через OCR
                if self.ocr_engine:
                    logger.info(f"Processing image {index} with OCR engine: {type(self.ocr_engine)}")
                    extracted_text, confidence = self._extract_text_from_image(temp_file_path)
                    analysis['extracted_text'] = extracted_text
                    analysis['text_confidence'] = confidence
                    logger.info(f"Image {index} OCR result: text length={len(extracted_text)}, confidence={confidence}")
                else:
                    logger.warning(f"No OCR engine available for image {index}")
                
                # Простой анализ содержимого изображения
                analysis['objects_detected'] = self._analyze_image_content(image)
                
                return analysis
                
            finally:
                # Удаляем временный файл
                try:
                    os.unlink(temp_file_path)
                    logger.info(f"Image {index}: temporary file deleted")
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error processing image {index}: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return {
                'index': index,
                'error': str(e),
                'extracted_text': '',
                'text_confidence': 0.0
            }
    
    def _extract_text_from_image(self, image_path: str) -> Tuple[str, float]:
        """Извлекает текст из изображения"""
        try:
            if isinstance(self.ocr_engine, PaddleOCR):
                return self._extract_text_with_paddle(image_path)
            elif self.ocr_engine == 'tesseract':
                return self._extract_text_with_tesseract(image_path)
            else:
                return "", 0.0
                
        except Exception as e:
            logger.error(f"Error extracting text: {e}")
            return "", 0.0
    
    def _extract_text_with_paddle(self, image_path: str) -> Tuple[str, float]:
        """Извлекает текст с помощью PaddleOCR"""
        try:
            result = self.ocr_engine.ocr(image_path, cls=True)
            
            if not result or not result[0]:
                return "", 0.0
            
            # Извлекаем текст и уверенность
            texts = []
            confidences = []
            
            for line in result[0]:
                if line and len(line) >= 2:
                    text = line[1][0]  # Текст
                    confidence = line[1][1]  # Уверенность
                    texts.append(text)
                    confidences.append(confidence)
            
            combined_text = '\n'.join(texts)
            avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
            
            return combined_text, avg_confidence
            
        except Exception as e:
            logger.error(f"PaddleOCR error: {e}")
            return "", 0.0
    
    def _extract_text_with_tesseract(self, image_path: str) -> Tuple[str, float]:
        """Извлекает текст с помощью Tesseract"""
        try:
            # Пробуем без указания языка (использует английский по умолчанию)
            text = pytesseract.image_to_string(
                image_path, 
                config='--psm 6 --oem 3'
            )
            
            # Если не получилось, пробуем с минимальной конфигурацией
            if not text.strip():
                text = pytesseract.image_to_string(
                    image_path, 
                    config='--psm 6'
                )
            
            # Если и это не помогло, пробуем без конфигурации
            if not text.strip():
                text = pytesseract.image_to_string(image_path)
            
            # Tesseract не предоставляет уверенность по умолчанию
            # Используем эвристику: если текст извлечен, считаем уверенность средней
            confidence = 0.7 if text.strip() else 0.0
            
            logger.info(f"Tesseract extracted text: '{text.strip()}' (confidence: {confidence})")
            return text.strip(), confidence
            
        except Exception as e:
            logger.error(f"Tesseract error: {e}")
            return "", 0.0
    
    def _analyze_image_content(self, image: Image.Image) -> List[str]:
        """Простой анализ содержимого изображения"""
        objects = []
        
        try:
            # Анализируем размеры
            width, height = image.size
            
            # Определяем тип изображения по размерам
            if width > height * 1.5:
                objects.append("landscape")
            elif height > width * 1.5:
                objects.append("portrait")
            else:
                objects.append("square")
            
            # Анализируем цвета
            if image.mode == 'RGB':
                # Простой анализ доминирующих цветов
                colors = image.getcolors(maxcolors=1000)
                if colors:
                    # Сортируем по количеству пикселей
                    colors.sort(key=lambda x: x[0], reverse=True)
                    dominant_color = colors[0][1]
                    
                    # Определяем яркость
                    r, g, b = dominant_color
                    brightness = (r + g + b) / 3
                    
                    if brightness > 200:
                        objects.append("light")
                    elif brightness < 50:
                        objects.append("dark")
                    else:
                        objects.append("medium_brightness")
            
            # Анализируем режим изображения
            if image.mode == 'L':
                objects.append("grayscale")
            elif image.mode == 'RGBA':
                objects.append("with_transparency")
            
        except Exception as e:
            logger.warning(f"Error analyzing image content: {e}")
        
        return objects
    
    def _get_file_extension(self, mime_type: str) -> str:
        """Получает расширение файла по MIME типу"""
        ext = mimetypes.guess_extension(mime_type)
        return ext if ext else '.jpg'
    
    def enhance_chat_context(self, message: str, image_analysis: Dict[str, Any]) -> str:
        """Улучшает контекст чата с информацией об изображениях"""
        if not image_analysis or not image_analysis.get('extracted_text'):
            return message
        
        enhanced_message = message + "\n\n"
        enhanced_message += "📸 Анализ изображений:\n"
        
        for i, img_analysis in enumerate(image_analysis.get('image_analysis', []), 1):
            if img_analysis.get('extracted_text'):
                enhanced_message += f"Изображение {i}:\n"
                enhanced_message += f"Текст: {img_analysis['extracted_text'][:200]}...\n"
                enhanced_message += f"Уверенность: {img_analysis.get('text_confidence', 0):.2f}\n\n"
        
        return enhanced_message


# Глобальный экземпляр сервиса
image_processing_service = ImageProcessingService()
