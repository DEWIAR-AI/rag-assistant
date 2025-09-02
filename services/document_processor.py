import asyncio
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from database.database import SessionLocal
from database.models import Document, DocumentChunk
from services.document_parser import document_parser
from services.embedding_service import embedding_service
from services.vector_service import vector_service
from services.supabase_service import supabase_service
from config import settings
import os

logger = logging.getLogger(__name__)


class DocumentProcessor:
    """Handles the complete document processing pipeline"""
    
    def __init__(self):
        self.processing_queue = asyncio.Queue()
        self.is_processing = False
    
    def get_db_session(self):
        """Get a database session"""
        return SessionLocal()
    
    async def process_document_async(self, document_id: int, file_path: str, file_type: str, section: str, access_level: str):
        """Process document asynchronously with enhanced error handling"""
        try:
            logger.info(f"🚀 Starting async processing for document {document_id}")
            
            # Get document from database
            db = self.get_db_session()
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if not document:
                    logger.error(f"Document {document_id} not found in database")
                    return
                logger.info(f"Found document: {document.title} in section {section}")
            finally:
                db.close()
            
            # Step 1: Download file from Supabase
            local_file_path = await self._download_document_file(file_path, document_id)
            if not local_file_path:
                return
            
            # Step 2: Parse document
            parse_result = await self._parse_document(local_file_path, document_id, document.mime_type)
            if not parse_result:
                return
            
            # Step 3: Create chunks
            chunks = await self._create_chunks_from_content(parse_result, document_id, section, access_level)
            if not chunks:
                return
            
            # Step 4: Store in vector database
            success = await self._store_chunks_in_vector_db(chunks)
            if not success:
                return
            
            # Step 5: Mark as processed
            await self._mark_document_processed(document_id, parse_result.get('metadata', {}), len(chunks))
            
            logger.info(f"✅ Document {document_id} processing completed successfully with {len(chunks)} chunks")
            
        except Exception as e:
            logger.error(f"❌ Document processing failed for {document_id}: {e}")
            await self._mark_document_error(document_id, f"Processing failed: {e}")
        finally:
            # Cleanup temporary files
            try:
                if 'local_file_path' in locals() and local_file_path and local_file_path != file_path:
                    if os.path.exists(local_file_path):
                        os.remove(local_file_path)
                        logger.info(f"🧹 Cleaned up temporary file: {local_file_path}")
            except Exception as cleanup_error:
                logger.warning(f"Cleanup failed: {cleanup_error}")
    
    async def _download_document_file(self, file_path: str, document_id: int) -> Optional[str]:
        """Download document file from Supabase storage"""
        try:
            # Check if it's already a local path
            if os.path.exists(file_path):
                logger.info(f"File already exists locally: {file_path}")
                return file_path
            
            # Download from Supabase
            try:
                # Use the async method that downloads to temp location
                local_file_path = await supabase_service.download_file_to_temp(file_path)
                logger.info(f"✅ Downloaded file to: {local_file_path}")
                return local_file_path
                
            except Exception as e:
                logger.error(f"Failed to download from Supabase: {e}")
                await self._mark_document_error(document_id, f"Failed to download from Supabase: {e}")
                return None
                
        except Exception as e:
            logger.error(f"File download failed: {e}")
            await self._mark_document_error(document_id, f"File download failed: {e}")
            return None
    
    async def _parse_document(self, local_file_path: str, document_id: int, mime_type: str) -> Optional[Dict]:
        """Parse document using enhanced parser"""
        try:
            logger.info(f"🔍 Parsing document: {local_file_path}")
            
            # Use the enhanced parser with automatic type detection
            parse_result = document_parser.parse_document(local_file_path, mime_type)
            
            if not parse_result.get('success', True) and 'error' in parse_result:
                raise Exception(f"Parser error: {parse_result['error']}")
            
            logger.info(f"✅ Document parsed successfully: {parse_result.get('type_detection', {}).get('detected_type', 'unknown')}")
            logger.info(f"📄 Extracted {len(parse_result.get('content', []))} content sections")
            
            return parse_result
            
        except Exception as parse_error:
            logger.error(f"❌ Document parsing failed: {parse_error}")
            await self._mark_document_error(document_id, f"Parsing failed: {parse_error}")
            return None
    
    async def _create_chunks_from_content(self, parse_result: Dict, document_id: int, section: str, access_level: str) -> Optional[List[Dict]]:
        """Create chunks from parsed content with proper metadata"""
        try:
            # Get document info from database for proper naming
            db = self.get_db_session()
            document_title = ""
            original_filename = ""
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if document:
                    document_title = document.title or document.original_filename or f"Документ {document_id}"
                    original_filename = document.original_filename or document.filename
            finally:
                db.close()
            
            content = parse_result.get('content', [])
            if not content:
                logger.warning(f"No content to chunk for document {document_id}")
                return None
            
            chunks = []
            chunk_index = 0
            MAX_CHUNKS_PER_DOCUMENT = 200  # Safety limit to prevent too many chunks
            
            for content_item in content:
                if chunk_index >= MAX_CHUNKS_PER_DOCUMENT:
                    logger.warning(f"⚠️ Reached safety limit of {MAX_CHUNKS_PER_DOCUMENT} chunks for document {document_id}, stopping chunk creation")
                    break
                    
                content_text = content_item.get('content', '')
                section_name = content_item.get('section_name', '')
                
                if not content_text.strip():
                    continue
                
                # Split content into smaller chunks if needed
                text_chunks = self._split_text_into_chunks(content_text)
                
                for i, text_chunk in enumerate(text_chunks):
                    if chunk_index >= MAX_CHUNKS_PER_DOCUMENT:
                        break
                        
                    if not text_chunk.strip():
                        continue
                    
                    # Generate embedding for chunk
                    try:
                        embedding = await embedding_service.get_embeddings_async(text_chunk)
                        
                        chunk_data = {
                    'document_id': document_id,
                            'chunk_id': f"{document_id}_{chunk_index}",
                            'content': text_chunk,
                    'section': section,
                    'access_level': access_level,
                            'chunk_type': content_item.get('type', 'text'),
                            'section_name': section_name,
                            'chunk_index': chunk_index,
                            'embedding': embedding,
                            'page_number': content_item.get('page'),
                            'sheet_name': content_item.get('sheet_name', ''),
                            'metadata': {
                                'original_filename': original_filename,
                                'content_type': content_item.get('type', 'text'),
                                'section_name': section_name,
                                'chunk_sub_index': i,
                                'document_title': document_title,
                                'file_type': parse_result.get('metadata', {}).get('file_type', ''),
                                'processing_timestamp': datetime.now().isoformat()
                            }
                        }
                        
                        chunks.append(chunk_data)
                        chunk_index += 1
                        
                    except Exception as e:
                        logger.error(f"Failed to generate embedding for chunk {chunk_index}: {e}")
                        continue
            
            logger.info(f"✅ Created {len(chunks)} chunks for document {document_id}")
            return chunks
            
        except Exception as e:
            logger.error(f"❌ Chunk creation failed: {e}")
            await self._mark_document_error(document_id, f"Chunk creation failed: {e}")
            return None
    
    def _split_text_into_chunks(self, text: str, max_chunk_size: int = 500, overlap: int = 50) -> List[str]:
        """Split text into overlapping chunks"""
        if len(text) <= max_chunk_size:
            return [text]
        
        chunks = []
        start = 0
        
        while start < len(text):
            end = start + max_chunk_size
            
            # Try to break at sentence boundaries
            if end < len(text):
                # Look for sentence endings
                for i in range(end, max(start + max_chunk_size - 100, start), -1):
                    if text[i] in '.!?':
                        end = i + 1
                        break
                
                # If no sentence boundary found, look for paragraph breaks
                if end == start + max_chunk_size:
                    for i in range(end, max(start + max_chunk_size - 100, start), -1):
                        if text[i] == '\n':
                            end = i + 1
                            break
            
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            
            # Move start position with overlap
            start = end - overlap
            if start >= len(text):
                break
        
        return chunks
    
    async def _store_chunks_in_vector_db(self, chunks: List[Dict]) -> bool:
        """Store chunks in vector database with safety limits"""
        try:
            # Safety limit: prevent too many chunks from being processed
            MAX_CHUNKS_FOR_VECTOR_DB = 100
            if len(chunks) > MAX_CHUNKS_FOR_VECTOR_DB:
                logger.warning(f"⚠️ Too many chunks ({len(chunks)}), limiting to {MAX_CHUNKS_FOR_VECTOR_DB} for safety")
                chunks = chunks[:MAX_CHUNKS_FOR_VECTOR_DB]
            
            logger.info(f"💾 Storing {len(chunks)} chunks in vector database...")
            
            # Prepare embeddings for vector service
            embeddings_data = []
            for chunk in chunks:
                embedding_data = {
                    'document_id': chunk['document_id'],
                    'chunk_id': chunk['chunk_id'],
                    'content': chunk['content'],
                    'section': chunk['section'],
                    'access_level': chunk['access_level'],
                    'chunk_type': chunk['chunk_type'],
                    'section_name': chunk.get('section_name', ''),
                    'chunk_index': chunk['chunk_index'],
                    'embedding': chunk['embedding'],
                    'metadata': chunk.get('metadata', {}),
                    'file_type': chunk.get('metadata', {}).get('file_type', ''),
                    'document_name': chunk.get('metadata', {}).get('document_title', ''),
                    'page_number': chunk.get('page_number'),
                    'sheet_name': chunk.get('sheet_name', ''),
                    'uploaded_at': datetime.now().isoformat(),
                    'processing_timestamp': datetime.now().isoformat()
                }
                embeddings_data.append(embedding_data)
            
            # Store in vector database
            vector_service.add_embeddings(embeddings_data)
            
            logger.info(f"✅ Successfully stored {len(chunks)} chunks in vector database")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to store chunks in vector database: {e}")
            return False
    
    async def _mark_document_processed(self, document_id: int, metadata: Dict, chunk_count: int):
        """Mark document as processed in database"""
        try:
            db = self.get_db_session()
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if document:
                    document.is_processed = True
                    document.processed_at = datetime.now()
                    document.text_content = str(metadata.get('title', ''))
                    document.extracted_metadata = metadata
                    document.processing_error = None
                    
                    db.commit()
                    logger.info(f"✅ Document {document_id} marked as processed with {chunk_count} chunks")
                    
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"❌ Failed to mark document as processed: {e}")
    
    async def _mark_document_error(self, document_id: int, error_message: str):
        """Mark document as having processing error"""
        try:
            db = self.get_db_session()
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if document:
                    document.processing_error = error_message
                    document.is_processed = False
                    
                    db.commit()
                    logger.info(f"❌ Document {document_id} marked with error: {error_message}")
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Failed to mark document error: {e}")
    
    async def _store_chunks_in_db(self, document_id: int, chunks: List[Dict[str, Any]]) -> List[DocumentChunk]:
        """Store document chunks in database"""
        try:
            db_chunks = []
            
            for i, chunk in enumerate(chunks):
                db_chunk = DocumentChunk(
                    document_id=document_id,
                    chunk_index=i,
                    content=chunk['content'],
                    content_length=len(chunk['content']),
                    page_number=chunk.get('page'),
                    section_name=chunk.get('sheet_name'),
                    chunk_type=chunk.get('type', 'text')
                )
                
                # Get database session
                from database.database import get_db_session
                db = get_db_session()
                try:
                    db.add(db_chunk)
                    db.commit()
                    db.refresh(db_chunk)
                    db_chunks.append(db_chunk)
                finally:
                    db.close()
            
            return db_chunks
            
        except Exception as e:
            logger.error(f"Error storing chunks in database: {e}")
            raise
    
    async def _update_chunk_embedding_ids(self, db_chunks: List[DocumentChunk], 
                                        embedding_ids: List[str]) -> None:
        """Update chunk records with embedding IDs"""
        try:
            from database.database import get_db_session
            db = get_db_session()
            try:
                for chunk, embedding_id in zip(db_chunks, embedding_ids):
                    chunk.embedding_id = embedding_id
                
                db.commit()
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error updating chunk embedding IDs: {e}")
            raise
    
    async def _update_document_status(self, document_id: int, is_processed: bool, 
                                    error: Optional[str] = None, 
                                    parsed_content: Optional[Dict[str, Any]] = None) -> None:
        """Update document processing status"""
        try:
            from database.database import get_db_session
            db = get_db_session()
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if document:
                    document.is_processed = is_processed
                    document.processing_error = error
                    document.processed_at = datetime.now() if is_processed else None
                    
                    if parsed_content:
                        document.has_images = parsed_content.get('has_images', False)
                        document.text_content = self._extract_text_summary(parsed_content)
                        document.extracted_metadata = parsed_content.get('metadata', {})
                    
                    db.commit()
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error updating document status: {e}")
            raise
    
    def _extract_text_summary(self, parsed_content: Dict[str, Any]) -> str:
        """Extract a summary of the text content"""
        try:
            text_parts = []
            for item in parsed_content.get('content', []):
                if item.get('type') == 'text' and item.get('content'):
                    text_parts.append(item['content'][:200])  # First 200 chars of each text section
            
            return " ".join(text_parts)[:1000]  # Limit to 1000 chars total
        except Exception as e:
            logger.warning(f"Error extracting text summary: {e}")
            return ""
    
    async def reprocess_document(self, document_id: int) -> Dict[str, Any]:
        """Reprocess a document that failed previously"""
        try:
            logger.info(f"🔄 Reprocessing document {document_id}")
            
            # Get document from database
            db = self.get_db_session()
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if not document:
                    return {'success': False, 'error': 'Document not found'}
                
                # Clear previous error
                document.processing_error = None
                document.is_processed = False
                db.commit()
                    
            finally:
                db.close()
                
            # Start reprocessing
            asyncio.create_task(
                self.process_document_async(
                    document_id, 
                    document.file_path, 
                    document.file_type, 
                    document.section, 
                    document.access_level
                )
            )
            
            return {'success': True, 'message': f'Document {document_id} reprocessing started'}
                
        except Exception as e:
            logger.error(f"❌ Failed to start reprocessing for document {document_id}: {e}")
            return {'success': False, 'error': str(e)}
    
    async def _delete_document_data(self, document_id: int) -> None:
        """Delete all data associated with a document"""
        try:
            # Delete from vector database
            vector_service.delete_document_embeddings(document_id)
            
            # Delete from database
            from database.database import get_db_session
            db = get_db_session()
            try:
                # Delete chunks
                db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
                
                # Reset document status
                document = db.query(Document).filter(Document.id == document_id).first()
                if document:
                    document.is_processed = False
                    document.processing_error = None
                    document.processed_at = None
                    document.has_images = False
                    document.text_content = None
                    document.extracted_metadata = None
                
                db.commit()
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error deleting document data: {e}")
            raise
    
    async def _delete_document_data_with_session(self, document_id: int, db_session) -> None:
        """Delete all data associated with a document using an existing session"""
        try:
            # Delete from vector database
            vector_service.delete_document_embeddings(document_id)
            
            # Delete from database using existing session
            # Delete chunks
            db_session.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
            
            # Reset document status
            document = db_session.query(Document).filter(Document.id == document_id).first()
            if document:
                document.is_processed = False
                document.processing_error = None
                document.processed_at = None
                document.has_images = False
                document.text_content = None
                document.extracted_metadata = None
            
            db_session.commit()
                
        except Exception as e:
            logger.error(f"Error deleting document data with session: {e}")
            raise
    
    async def get_processing_status(self, document_id: int) -> Dict[str, Any]:
        """Get the processing status of a document"""
        try:
            db = self.get_db_session()
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if not document:
                    return {'error': 'Document not found'}
                
                return {
                    'id': document.id,
                    'title': document.title,
                    'is_processed': document.is_processed,
                    'processing_error': document.processing_error,
                    'uploaded_at': document.uploaded_at.isoformat() if document.uploaded_at else None,
                    'processed_at': document.processed_at.isoformat() if document.processed_at else None,
                    'status': 'processed' if document.is_processed else 'error' if document.processing_error else 'processing'
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to get processing status: {e}")
            return {'error': str(e)}

    async def delete_document_completely(self, document_id: int) -> Dict[str, Any]:
        """Delete a document completely from storage, database, and vector store"""
        try:
            logger.info(f"🗑️ Начинаем полное удаление документа {document_id}")
            
            # Get document info first
            db = self.get_db_session()
            try:
                document = db.query(Document).filter(Document.id == document_id).first()
                if not document:
                    return {'success': False, 'error': 'Document not found'}
                
                document_info = {
                    'id': document.id,
                    'filename': document.filename,
                    'original_filename': document.original_filename,
                    'section': document.section,
                    'file_path': document.file_path
                }
                
            finally:
                db.close()
            
            # Step 1: Delete from Supabase Storage
            try:
                if document_info['file_path']:
                    from services.supabase_service import supabase_service
                    # Используем file_path (полный путь) вместо filename
                    storage_result = supabase_service.delete_file(document_info['file_path'])
                    if storage_result:
                        logger.info(f"✅ Файл удален из Supabase Storage: {document_info['file_path']}")
                    else:
                        logger.warning(f"⚠️ Не удалось удалить файл из Storage: {document_info['file_path']}")
                elif document_info['filename']:
                    # Fallback: пробуем удалить по filename, если file_path пустой
                    from services.supabase_service import supabase_service
                    # Строим путь: section/filename
                    full_path = f"{document_info['section']}/{document_info['filename']}"
                    storage_result = supabase_service.delete_file(full_path)
                    if storage_result:
                        logger.info(f"✅ Файл удален из Supabase Storage (fallback): {full_path}")
                    else:
                        logger.warning(f"⚠️ Не удалось удалить файл из Storage (fallback): {full_path}")
                else:
                    logger.info("ℹ️ Путь к файлу не найден, пропускаем удаление из Storage")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при удалении из Storage: {e}")
            
            # Step 2: Delete from vector database
            try:
                from services.vector_service import vector_service
                vector_result = vector_service.delete_document_embeddings(document_id)
                if vector_result:
                    logger.info(f"✅ Векторы удалены из Qdrant: {document_id}")
                else:
                    logger.warning(f"⚠️ Не удалось удалить векторы: {document_id}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при удалении векторов: {e}")
            
            # Step 3: Delete from database completely
            try:
                db = self.get_db_session()
                try:
                    # Delete chunks first (foreign key constraint)
                    chunks_deleted = db.query(DocumentChunk).filter(
                        DocumentChunk.document_id == document_id
                    ).delete()
                    
                    # Delete the document itself
                    document_deleted = db.query(Document).filter(
                        Document.id == document_id
                    ).delete()
                    
                    db.commit()
                    
                    logger.info(f"✅ Удалено из БД: {chunks_deleted} чанков, {document_deleted} документ")
                    
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"❌ Ошибка при удалении из БД: {e}")
                return {'success': False, 'error': f'Database deletion failed: {e}'}
            
            # Step 4: Clean up local file if exists
            try:
                if document_info['file_path'] and os.path.exists(document_info['file_path']):
                    os.remove(document_info['file_path'])
                    logger.info(f"✅ Локальный файл удален: {document_info['file_path']}")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось удалить локальный файл: {e}")
            
            logger.info(f"🎉 Документ {document_id} полностью удален")
            return {
                'success': True,
                'message': f"Document {document_id} deleted completely",
                'deleted_info': document_info
            }
            
        except Exception as e:
            logger.error(f"❌ Ошибка при полном удалении документа {document_id}: {e}")
            return {'success': False, 'error': str(e)}


# Global instance
document_processor = DocumentProcessor()
