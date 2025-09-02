from supabase import create_client, Client
from config import settings
import logging
from typing import Optional, List, Dict, Any
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)


class SupabaseService:
    def __init__(self):
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )
        self.bucket_name = settings.supabase_bucket
        
    def upload_file(self, file_path: str, destination_path: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Upload a file to Supabase Storage"""
        try:
            with open(file_path, 'rb') as f:
                file_data = f.read()
                
            # Upload file
            result = self.client.storage.from_(self.bucket_name).upload(
                path=destination_path,
                file=file_data,
                file_options={"content-type": self._get_mime_type(file_path)}
            )
            
            if result:
                # Get public URL
                public_url = self.client.storage.from_(self.bucket_name).get_public_url(destination_path)
                logger.info(f"File uploaded successfully: {destination_path}")
                return public_url
            else:
                raise Exception("Upload failed")
                
        except Exception as e:
            logger.error(f"Error uploading file {file_path}: {e}")
            raise
    
    def download_file(self, file_path: str, local_path: Optional[str] = None) -> bytes:
        """Download a file from Supabase Storage"""
        try:
            # Download file
            result = self.client.storage.from_(self.bucket_name).download(file_path)
            
            # Ensure result is bytes
            if isinstance(result, str):
                result = result.encode('utf-8')
            elif not isinstance(result, bytes):
                result = bytes(result)
            
            # If local_path is provided, save to file
            if local_path:
                # Ensure local directory exists (only if there's a directory component)
                dir_name = os.path.dirname(local_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                
                with open(local_path, 'wb') as f:
                    f.write(result)
                    
                logger.info(f"File downloaded successfully: {local_path}")
                return result
            
            # Return file data as bytes
            return result
            
        except Exception as e:
            logger.error(f"Error downloading file {file_path}: {e}")
            raise
    
    async def download_file_to_temp(self, file_path: str) -> str:
        """Download a file from Supabase Storage to a temporary location"""
        try:
            import tempfile
            
            # Create a temporary file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file_path)[1])
            temp_path = temp_file.name
            temp_file.close()
            
            # Download file to temp location
            self.download_file(file_path, temp_path)
            logger.info(f"File downloaded to temp location: {temp_path}")
            return temp_path
                
        except Exception as e:
            logger.error(f"Error downloading file to temp: {e}")
            raise
    
    def delete_file(self, file_path: str) -> bool:
        """Delete a file from Supabase Storage"""
        try:
            logger.info(f"🗑️ Удаляем файл из Supabase Storage: {file_path}")
            
            # Проверяем, существует ли файл перед удалением
            try:
                file_metadata = self.get_file_metadata(file_path)
                if not file_metadata:
                    logger.warning(f"⚠️ Файл {file_path} не найден в Storage")
                    return True  # Считаем успешным, если файл уже не существует
            except Exception as e:
                logger.warning(f"⚠️ Не удалось проверить существование файла {file_path}: {e}")
            
            # Удаляем файл
            result = self.client.storage.from_(self.bucket_name).remove([file_path])
            
            if result:
                logger.info(f"✅ Файл успешно удален из Supabase Storage: {file_path}")
                
                # Дополнительная проверка - убеждаемся, что файл действительно удален
                try:
                    time.sleep(1)  # Небольшая задержка для обновления Storage
                    file_metadata_after = self.get_file_metadata(file_path)
                    if not file_metadata_after:
                        logger.info(f"✅ Подтверждено удаление файла {file_path}")
                        return True
                    else:
                        logger.warning(f"⚠️ Файл {file_path} все еще существует после удаления")
                        return False
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось проверить удаление файла {file_path}: {e}")
                    return True  # Считаем успешным, если основное удаление прошло
            else:
                logger.error(f"❌ Supabase вернул False при удалении файла {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Ошибка при удалении файла {file_path}: {e}")
            return False
    
    def list_files(self, folder_path: str = "") -> List[Dict[str, Any]]:
        """List files in a folder"""
        try:
            result = self.client.storage.from_(self.bucket_name).list(folder_path)
            return result
        except Exception as e:
            logger.error(f"Error listing files in {folder_path}: {e}")
            return []
    
    def get_file_url(self, file_path: str) -> str:
        """Get public URL for a file"""
        try:
            return self.client.storage.from_(self.bucket_name).get_public_url(file_path)
        except Exception as e:
            logger.error(f"Error getting file URL for {file_path}: {e}")
            raise
    
    def get_file_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a file"""
        try:
            result = self.client.storage.from_(self.bucket_name).list(
                os.path.dirname(file_path) or "."
            )
            
            for file_info in result:
                if file_info.get('name') == os.path.basename(file_path):
                    return file_info
            return None
            
        except Exception as e:
            logger.error(f"Error getting metadata for {file_path}: {e}")
            return None
    
    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type based on file extension"""
        mime_types = {
            '.pdf': 'application/pdf',
            '.doc': 'application/msword',
            '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            '.xls': 'application/vnd.ms-excel',
            '.xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            '.txt': 'text/plain',
            '.md': 'text/markdown',
            '.markdown': 'text/markdown'
        }
        
        ext = Path(file_path).suffix.lower()
        return mime_types.get(ext, 'application/octet-stream')
    
    def check_storage_usage(self) -> Dict[str, Any]:
        """Check storage usage and limits"""
        try:
            # This would require custom implementation as Supabase doesn't provide direct storage usage API
            # For now, return placeholder data
            return {
                "used": 0,  # Would need to calculate from file metadata
                "limit": 150 * 1024 * 1024 * 1024,  # 150GB in bytes
                "available": 150 * 1024 * 1024 * 1024
            }
        except Exception as e:
            logger.error(f"Error checking storage usage: {e}")
            return {"used": 0, "limit": 0, "available": 0}

    def get_download_url(self, file_path: str, expires_in: int = 3600) -> str:
        """Get secure download URL for a file with expiration"""
        try:
            # Create a signed URL that expires
            result = self.client.storage.from_(self.bucket_name).create_signed_url(
                path=file_path,
                expires_in=expires_in
            )
            return result
        except Exception as e:
            logger.error(f"Error creating signed URL for {file_path}: {e}")
            # Fallback to public URL if available
            try:
                return self.get_file_url(file_path)
            except:
                return ""
    
    def get_public_download_url(self, file_path: str) -> str:
        """Get public download URL for a file (if bucket is public)"""
        try:
            return self.client.storage.from_(self.bucket_name).get_public_url(file_path)
        except Exception as e:
            logger.error(f"Error getting public URL for {file_path}: {e}")
            return ""


# Global instance
supabase_service = SupabaseService()
