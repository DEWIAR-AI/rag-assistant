import os
import shutil
import logging
import schedule
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from pathlib import Path

class CacheCleanupService:
    """Сервис для автоматической очистки кэша и временных файлов"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.running = False
        self.scheduler_thread = None
        self.cleanup_config = {
            'temp_files': {
                'path': 'temp',
                'max_age_hours': 24,
                'enabled': True
            },
            'sessions': {
                'path': 'sessions',
                'max_age_hours': 168,  # 7 дней
                'enabled': True
            },
            'logs': {
                'path': 'logs',
                'max_age_hours': 720,  # 30 дней
                'enabled': True
            },
            'uploads': {
                'path': 'uploads',
                'max_age_hours': 48,
                'enabled': True
            },
            'vector_cache': {
                'path': 'vector_cache',
                'max_age_hours': 168,  # 7 дней
                'enabled': True
            }
        }
        
    def start(self):
        """Запускает сервис очистки кэша"""
        if self.running:
            self.logger.info("Сервис очистки кэша уже запущен")
            return
            
        self.running = True
        self.scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        self.logger.info("Сервис очистки кэша запущен")
        
    def stop(self):
        """Останавливает сервис очистки кэша"""
        if not self.running:
            return
            
        self.running = False
        if self.scheduler_thread:
            self.scheduler_thread.join(timeout=5)
        self.logger.info("Сервис очистки кэша остановлен")
        
    def run_automatic_cleanup(self):
        """Запускает автоматическую очистку всех категорий"""
        try:
            self.logger.info("Запуск автоматической очистки кэша")
            
            for category, config in self.cleanup_config.items():
                if config['enabled']:
                    self._cleanup_category(category, config)
                    
            self.logger.info("Автоматическая очистка кэша завершена")
            
        except Exception as e:
            self.logger.error(f"Ошибка при автоматической очистке кэша: {e}")
            
    def manual_cleanup(self, categories: Optional[List[str]] = None):
        """Запускает ручную очистку указанных категорий или всех"""
        try:
            if categories is None:
                categories = list(self.cleanup_config.keys())
                
            self.logger.info(f"Запуск ручной очистки кэша для категорий: {categories}")
            
            for category in categories:
                if category in self.cleanup_config and self.cleanup_config[category]['enabled']:
                    self._cleanup_category(category, self.cleanup_config[category])
                    
            self.logger.info("Ручная очистка кэша завершена")
            
        except Exception as e:
            self.logger.error(f"Ошибка при ручной очистке кэша: {e}")
            
    def _cleanup_category(self, category: str, config: Dict):
        """Очищает указанную категорию файлов"""
        try:
            path = Path(config['path'])
            if not path.exists():
                self.logger.debug(f"Путь {path} не существует, пропускаем")
                return
                
            max_age = timedelta(hours=config['max_age_hours'])
            current_time = datetime.now()
            deleted_count = 0
            deleted_size = 0
            
            self.logger.info(f"Очистка категории {category} в {path}")
            
            for item in path.rglob('*'):
                if item.is_file():
                    try:
                        file_age = current_time - datetime.fromtimestamp(item.stat().st_mtime)
                        if file_age > max_age:
                            file_size = item.stat().st_size
                            item.unlink()
                            deleted_count += 1
                            deleted_size += file_size
                            self.logger.debug(f"Удален файл: {item}")
                    except Exception as e:
                        self.logger.warning(f"Не удалось удалить файл {item}: {e}")
                        
            # Удаляем пустые директории
            self._remove_empty_directories(path)
            
            if deleted_count > 0:
                self.logger.info(f"Категория {category}: удалено {deleted_count} файлов, освобождено {deleted_size / 1024 / 1024:.2f} МБ")
            else:
                self.logger.info(f"Категория {category}: файлы для удаления не найдены")
                
        except Exception as e:
            self.logger.error(f"Ошибка при очистке категории {category}: {e}")
            
    def _remove_empty_directories(self, path: Path):
        """Рекурсивно удаляет пустые директории"""
        try:
            for item in sorted(path.rglob('*'), key=lambda x: len(x.parts), reverse=True):
                if item.is_dir() and item != path:
                    try:
                        if not any(item.iterdir()):
                            item.rmdir()
                            self.logger.debug(f"Удалена пустая директория: {item}")
                    except Exception as e:
                        self.logger.debug(f"Не удалось удалить директорию {item}: {e}")
        except Exception as e:
            self.logger.debug(f"Ошибка при удалении пустых директорий: {e}")
            
    def _run_scheduler(self):
        """Запускает планировщик задач"""
        try:
            # Планируем очистку каждые 6 часов
            schedule.every(6).hours.do(self.run_automatic_cleanup)
            
            # Планируем очистку в определенное время (например, в 3:00)
            schedule.every().day.at("03:00").do(self.run_automatic_cleanup)
            
            self.logger.info("Планировщик очистки кэша запущен")
            
            while self.running:
                schedule.run_pending()
                time.sleep(60)  # Проверяем каждую минуту
                
        except Exception as e:
            self.logger.error(f"Ошибка в планировщике очистки кэша: {e}")
            
    def _schedule_cleanup(self, category: str, interval_hours: int):
        """Планирует очистку конкретной категории"""
        try:
            schedule.every(interval_hours).hours.do(
                self._cleanup_category, category, self.cleanup_config[category]
            )
            self.logger.info(f"Запланирована очистка категории {category} каждые {interval_hours} часов")
        except Exception as e:
            self.logger.error(f"Ошибка при планировании очистки категории {category}: {e}")
            
    def _check_cleanup_schedule(self):
        """Проверяет расписание очистки"""
        try:
            jobs = schedule.get_jobs()
            if jobs:
                self.logger.info(f"Активных задач очистки: {len(jobs)}")
                for job in jobs:
                    self.logger.info(f"Задача: {job.job_func.__name__}, следующее выполнение: {job.next_run}")
            else:
                self.logger.info("Активных задач очистки нет")
        except Exception as e:
            self.logger.error(f"Ошибка при проверке расписания очистки: {e}")
            
    @property
    def is_running(self) -> bool:
        """Возвращает True, если сервис запущен"""
        return self.running
        
    def get_status(self) -> Dict:
        """Возвращает статус сервиса очистки кэша"""
        try:
            status = {
                'running': self.running,
                'is_running': self.running,  # Добавляем для совместимости
                'categories': {},
                'next_cleanup': None
            }
            
            # Получаем информацию о каждой категории
            for category, config in self.cleanup_config.items():
                path = Path(config['path'])
                if path.exists():
                    total_files = sum(1 for _ in path.rglob('*') if _.is_file())
                    total_size = sum(f.stat().st_size for f in path.rglob('*') if f.is_file())
                    
                    status['categories'][category] = {
                        'enabled': config['enabled'],
                        'path': str(path),
                        'total_files': total_files,
                        'total_size_mb': round(total_size / 1024 / 1024, 2),
                        'max_age_hours': config['max_age_hours']
                    }
                else:
                    status['categories'][category] = {
                        'enabled': config['enabled'],
                        'path': str(path),
                        'total_files': 0,
                        'total_size_mb': 0,
                        'max_age_hours': config['max_age_hours']
                    }
                    
            # Получаем информацию о следующей запланированной очистке
            try:
                jobs = schedule.get_jobs()
                if jobs:
                    next_job = min(jobs, key=lambda x: x.next_run)
                    status['next_cleanup'] = next_job.next_run.isoformat()
            except Exception as e:
                self.logger.debug(f"Не удалось получить информацию о следующей очистке: {e}")
                
            return status
            
        except Exception as e:
            self.logger.error(f"Ошибка при получении статуса сервиса: {e}")
            return {'error': str(e)}
            
    def update_cleanup_config(self, config_updates: Dict[str, Dict]) -> None:
        """Обновляет конфигурацию очистки кэша"""
        try:
            for category, config in config_updates.items():
                if category in self.cleanup_config:
                    self.cleanup_config[category].update(config)
                    self.logger.info(f"Обновлена конфигурация для категории {category}")
                else:
                    self.logger.warning(f"Неизвестная категория {category}")
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении конфигурации: {e}")

# Создаем экземпляр сервиса
cache_cleanup_service = CacheCleanupService()
