from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, Range
from config import settings
from services.embedding_service import get_embedding_service
import logging
from typing import List, Dict, Any, Optional
import uuid
import numpy as np

logger = logging.getLogger(__name__)


class VectorService:
    def __init__(self):
        # Use Qdrant Cloud configuration
        qdrant_params = settings.qdrant_connection_params
        
        self.client = QdrantClient(
            url=qdrant_params["url"],
            api_key=qdrant_params["api_key"]
        )
        self.collection_name = qdrant_params["collection_name"]
        self.vector_size = qdrant_params["vector_size"]
        
        # Get embedding service for dynamic operations
        self.embedding_service = get_embedding_service()
        
        # Ensure collection exists
        self._ensure_collection_exists()
    
    def _ensure_collection_exists(self):
        """Ensure the collection exists, create if it doesn't"""
        try:
            collections = self.client.get_collections()
            collection_names = [col.name for col in collections.collections]
            
            if self.collection_name not in collection_names:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created collection: {self.collection_name}")
                
                # Create indexes for fields used in filters
                self._create_field_indexes()
            else:
                # Check if existing collection has correct vector size
                collection_info = self.client.get_collection(self.collection_name)
                existing_size = collection_info.config.params.vectors.size
                
                if existing_size != self.vector_size:
                    logger.warning(f"Vector size mismatch: collection has {existing_size}, need {self.vector_size}")
                    logger.info("Recreating collection with correct vector size...")
                    self._recreate_collection()
                else:
                    logger.info(f"Collection {self.collection_name} already exists with correct vector size")
                    
                    # Ensure indexes exist
                    self._ensure_field_indexes()
                
        except Exception as e:
            logger.error(f"Error ensuring collection exists: {e}")
            raise
    
    def _recreate_collection(self):
        """Recreate the collection with the correct vector size"""
        try:
            # Delete existing collection
            self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted collection: {self.collection_name}")
            
            # Create new collection with correct vector size
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=self.vector_size,
                    distance=Distance.COSINE
                )
            )
            logger.info(f"Recreated collection: {self.collection_name} with vector size: {self.vector_size}")
            
            # Create indexes for fields used in filters
            self._create_field_indexes()
            
        except Exception as e:
            logger.error(f"Error recreating collection: {e}")
            raise
    
    def _create_field_indexes(self):
        """Create indexes for fields used in filters"""
        try:
            # Create index for section field (used in most filters)
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="section",
                field_schema="keyword"
            )
            logger.info("Created index for 'section' field")
            
            # Create index for access_level field
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="access_level",
                field_schema="keyword"
            )
            logger.info("Created index for 'access_level' field")
            
            # Create index for document_id field
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="document_id",
                field_schema="integer"
            )
            logger.info("Created index for 'document_id' field")
            
            # Create index for chunk_type field
            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="chunk_type",
                field_schema="keyword"
            )
            logger.info("Created index for 'chunk_type' field")
            
            logger.info("✅ All field indexes created successfully")
            
        except Exception as e:
            logger.error(f"Error creating field indexes: {e}")
            # Don't raise here, as indexes are optional for basic functionality
    
    def _ensure_field_indexes(self):
        """Ensure that required field indexes exist"""
        try:
            # Try to create indexes if they don't exist
            self._create_field_indexes()
        except Exception as e:
            logger.warning(f"Could not ensure field indexes: {e}")
            # This is not critical, so we don't raise
    
    def add_embeddings(self, embeddings: List[Dict[str, Any]]) -> List[str]:
        """Add embeddings to the vector database with enhanced metadata"""
        try:
            points = []
            embedding_ids = []
            
            for emb in embeddings:
                embedding_id = str(uuid.uuid4())
                embedding_ids.append(embedding_id)
                
                # Prepare enhanced payload
                payload = {
                    'document_id': emb['document_id'],
                    'chunk_id': emb['chunk_id'],
                    'content': emb['content'],
                    'section': emb['section'],
                    'access_level': emb['access_level'],
                    'chunk_type': emb.get('chunk_type', 'text'),
                    'page_number': emb.get('page_number'),
                    'section_name': emb.get('section_name'),
                    'sheet_name': emb.get('sheet_name'),  # For Excel documents
                    'document_name': emb.get('document_name', ''),
                    'metadata': emb.get('metadata', {}),
                    'chunk_index': emb.get('chunk_index', 0),
                    'content_length': len(emb.get('content', '')),
                    'has_images': emb.get('has_images', False),
                    'file_type': emb.get('file_type', ''),
                    'uploaded_at': emb.get('uploaded_at', ''),
                    'processing_timestamp': emb.get('processing_timestamp', '')
                }
                
                # Remove None values
                payload = {k: v for k, v in payload.items() if v is not None}
                
                point = PointStruct(
                    id=embedding_id,
                    vector=emb['embedding'].tolist() if hasattr(emb['embedding'], 'tolist') else emb['embedding'],
                    payload=payload
                )
                points.append(point)
            
            # Insert points in batches
            batch_size = 100
            for i in range(0, len(points), batch_size):
                batch = points[i:i + batch_size]
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=batch
                )
            
            logger.info(f"Added {len(embeddings)} embeddings to vector database")
            return embedding_ids
            
        except Exception as e:
            logger.error(f"Error adding embeddings: {e}")
            raise
    
    def search_similar(self, query_embedding: np.ndarray, 
                       limit: int = 10, 
                       score_threshold: float = 0.7,
                       filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search for similar embeddings with enhanced filtering and smart ranking"""
        try:
            # Build filter
            search_filter = None
            if filters:
                conditions = []
                
                if 'section' in filters:
                    conditions.append(
                        FieldCondition(key="section", match=MatchValue(value=filters['section']))
                    )
                
                if 'access_level' in filters:
                    conditions.append(
                        FieldCondition(key="access_level", match=MatchValue(value=filters['access_level']))
                    )
                
                if 'chunk_type' in filters:
                    conditions.append(
                        FieldCondition(key="chunk_type", match=MatchValue(value=filters['chunk_type']))
                    )
                
                if 'file_type' in filters:
                    conditions.append(
                        FieldCondition(key="file_type", match=MatchValue(value=filters['file_type']))
                    )
                
                if 'sheet_name' in filters:
                    conditions.append(
                        FieldCondition(key="sheet_name", match=MatchValue(value=filters['sheet_name']))
                    )
                
                if 'document_id' in filters:
                    conditions.append(
                        FieldCondition(key="document_id", match=MatchValue(value=filters['document_id']))
                    )
                
                if 'min_content_length' in filters:
                    conditions.append(
                        FieldCondition(key="content_length", range=Range(gte=filters['min_content_length']))
                    )
                
                if 'max_content_length' in filters:
                    conditions.append(
                        FieldCondition(key="content_length", range=Range(lte=filters['max_content_length']))
                    )
                
                if conditions:
                    search_filter = Filter(must=conditions)
            
            # Умный поиск: сначала ищем больше результатов, потом фильтруем
            initial_limit = min(limit * 3, 50)  # Ищем в 3 раза больше для лучшей фильтрации
            
            # Perform search
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding.tolist() if hasattr(query_embedding, 'tolist') else query_embedding,
                limit=initial_limit,
                score_threshold=score_threshold * 0.8,  # Немного снижаем порог для начального поиска
                query_filter=search_filter,
                with_payload=True,
                with_vectors=False
            )
            
            # Умная фильтрация и ранжирование результатов
            filtered_results = self._smart_filter_and_rank_results(
                search_result, 
                limit, 
                score_threshold,
                filters
            )
            
            return filtered_results
            
        except Exception as e:
            logger.error(f"Error searching embeddings: {e}")
            raise
    
    def search_by_text(self, query: str, 
                       limit: int = 10, 
                       score_threshold: float = 0.7,
                       filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Search for similar chunks by text query with enhanced filtering"""
        try:
            # Build filter conditions
            filter_conditions = []
            
            if filters:
                # Access level filter
                if filters.get('access_level'):
                    filter_conditions.append(
                        FieldCondition(
                            key="access_level",
                            match=MatchValue(value=filters['access_level'])
                        )
                    )
                
                # Section filter
                if filters.get('section'):
                    filter_conditions.append(
                        FieldCondition(
                            key="section",
                            match=MatchValue(value=filters['section'])
                        )
                    )
                
                # Document type filter
                if filters.get('file_type'):
                    filter_conditions.append(
                        FieldCondition(
                            key="file_type",
                            match=MatchValue(value=filters['file_type'])
                        )
                    )
                
                # Chunk type filter
                if filters.get('chunk_type'):
                    filter_conditions.append(
                        FieldCondition(
                            key="chunk_type",
                            match=MatchValue(value=filters['chunk_type'])
                        )
                    )
                
                # Date range filter
                if filters.get('date_from') or filters.get('date_to'):
                    if filters.get('date_from'):
                        filter_conditions.append(
                            FieldCondition(
                                key="uploaded_at",
                                range=Range(gte=filters['date_from'])
                            )
                        )
                    if filters.get('date_to'):
                        filter_conditions.append(
                            FieldCondition(
                                key="uploaded_at",
                                range=Range(lte=filters['date_to'])
                            )
                        )
            
            # Create filter object if conditions exist
            search_filter = None
            if filter_conditions:
                search_filter = Filter(
                    must=filter_conditions
                )
            
            # Perform search with enhanced parameters
            search_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=self._get_query_embedding(query),
                limit=limit,
                score_threshold=score_threshold,
                query_filter=search_filter,
                with_payload=True,
                with_vectors=False  # Don't return vectors to save bandwidth
            )
            
            # Process and enhance results
            enhanced_results = []
            for result in search_results:
                enhanced_result = {
                    'id': result.id,
                    'score': result.score,
                    'document_id': result.payload.get('document_id'),
                    'chunk_id': result.payload.get('chunk_id'),
                    'content': result.payload.get('content', ''),
                    'section': result.payload.get('section', ''),
                    'access_level': result.payload.get('access_level', ''),
                    'chunk_type': result.payload.get('chunk_type', 'text'),
                    'page_number': result.payload.get('page_number'),
                    'section_name': result.payload.get('section_name', ''),
                    'sheet_name': result.payload.get('sheet_name', ''),
                    'document_name': result.payload.get('document_name', ''),
                    'file_type': result.payload.get('file_type', ''),
                    'chunk_index': result.payload.get('chunk_index', 0),
                    'content_length': result.payload.get('content_length', 0),
                    'has_images': result.payload.get('has_images', False),
                    'metadata': result.payload.get('metadata', {}),
                    'uploaded_at': result.payload.get('uploaded_at', ''),
                    'processing_timestamp': result.payload.get('processing_timestamp', '')
                }
                
                # Add enhanced metadata for better source linking
                if enhanced_result['sheet_name']:
                    enhanced_result['section_name'] = f"Sheet: {enhanced_result['sheet_name']}"
                elif enhanced_result['page_number']:
                    enhanced_result['section_name'] = f"Page {enhanced_result['page_number']}"
                
                enhanced_results.append(enhanced_result)
            
            logger.info(f"Found {len(enhanced_results)} relevant chunks for query: {query[:50]}...")
            return enhanced_results
            
        except Exception as e:
            logger.error(f"Error searching by text: {e}")
            raise
    
    def delete_embeddings(self, embedding_ids: List[str]) -> bool:
        """Delete embeddings by IDs"""
        try:
            if not embedding_ids:
                return True
            
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=embedding_ids
            )
            
            logger.info(f"Deleted {len(embedding_ids)} embeddings")
            return True
            
        except Exception as e:
            logger.error(f"Error deleting embeddings: {e}")
            return False
    
    def delete_document_embeddings(self, document_id: int) -> bool:
        """Delete all embeddings for a specific document"""
        try:
            # Search for embeddings with the document_id
            search_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                ),
                limit=1000,  # Adjust based on expected chunk count
                with_payload=False
            )
            
            if search_result[0]:  # Points found
                point_ids = [point.id for point in search_result[0]]
                if point_ids:
                    self.client.delete(
                        collection_name=self.collection_name,
                        points_selector=point_ids
                    )
                    logger.info(f"Deleted {len(point_ids)} embeddings for document {document_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error deleting document embeddings: {e}")
            return False
    
    def get_collection_info(self) -> Dict[str, Any]:
        """Get information about the vector collection"""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            
            # Get collection statistics
            stats = self.client.get_collection(self.collection_name)
            
            return {
                'name': self.collection_name,
                'vector_size': collection_info.config.params.vectors.size,
                'distance': collection_info.config.params.vectors.distance.value,
                'points_count': stats.points_count,
                'segments_count': stats.segments_count,
                'status': collection_info.status.value
            }
            
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return {}
    
    def update_vector_size(self, new_size: int):
        """Update vector size (requires recreating collection)"""
        try:
            # This is a destructive operation - should be used carefully
            logger.warning(f"Updating vector size from {self.vector_size} to {new_size}")
            
            # Get current collection info
            current_info = self.get_collection_info()
            
            # Create new collection with new size
            new_collection_name = f"{self.collection_name}_new"
            self.client.create_collection(
                collection_name=new_collection_name,
                vectors_config=VectorParams(
                    size=new_size,
                    distance=Distance.COSINE
                )
            )
            
            # Note: In production, you'd want to migrate data here
            logger.info(f"Created new collection {new_collection_name} with size {new_size}")
            
            # Update instance variable
            self.vector_size = new_size
            
        except Exception as e:
            logger.error(f"Error updating vector size: {e}")
            raise
    
    def get_document_chunks(self, document_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all chunks for a specific document"""
        try:
            search_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=document_id))]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            
            chunks = []
            for point in search_result[0]:
                chunk_data = {
                    'id': point.id,
                    'document_id': point.payload.get('document_id'),
                    'chunk_id': point.payload.get('chunk_id'),
                    'content': point.payload.get('content', ''),
                    'chunk_type': point.payload.get('chunk_type', 'text'),
                    'page_number': point.payload.get('page_number'),
                    'section_name': point.payload.get('section_name'),
                    'sheet_name': point.payload.get('sheet_name'),
                    'chunk_index': point.payload.get('chunk_index', 0),
                    'metadata': point.payload.get('metadata', {})
                }
                chunks.append(chunk_data)
            
            # Sort by chunk index
            chunks.sort(key=lambda x: x.get('chunk_index', 0))
            
            return chunks
            
        except Exception as e:
            logger.error(f"Error getting document chunks: {e}")
            return []
    
    def get_similar_chunks(self, chunk_id: int, limit: int = 5) -> List[Dict[str, Any]]:
        """Find chunks similar to a specific chunk"""
        try:
            # First get the chunk's vector
            chunk_result = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="chunk_id", match=MatchValue(value=chunk_id))]
                ),
                limit=1,
                with_payload=False,
                with_vectors=True
            )
            
            if not chunk_result[0]:
                return []
            
            chunk_vector = chunk_result[0][0].vector
            
            # Search for similar chunks (excluding the same chunk)
            search_result = self.client.search(
                collection_name=self.collection_name,
                query_vector=chunk_vector,
                limit=limit + 1,  # +1 to account for excluding the same chunk
                score_threshold=0.5,
                with_payload=True,
                with_vectors=False
            )
            
            similar_chunks = []
            for result in search_result:
                if result.payload.get('chunk_id') != chunk_id:
                    chunk_data = {
                        'id': result.id,
                        'score': result.score,
                        'document_id': result.payload.get('document_id'),
                        'chunk_id': result.payload.get('chunk_id'),
                        'content': result.payload.get('content', ''),
                        'chunk_type': result.payload.get('chunk_type', 'text'),
                        'section_name': result.payload.get('section_name'),
                        'sheet_name': result.payload.get('sheet_name')
                    }
                    similar_chunks.append(chunk_data)
            
            return similar_chunks[:limit]
            
        except Exception as e:
            logger.error(f"Error getting similar chunks: {e}")
            return []

    def _get_query_embedding(self, query: str) -> List[float]:
        """Get embedding for a text query"""
        try:
            embedding = self.embedding_service.get_embeddings(query)
            return embedding.tolist() if hasattr(embedding, 'tolist') else embedding
        except Exception as e:
            logger.error(f"Error getting query embedding: {e}")
            raise
    
    def _smart_filter_and_rank_results(self, search_result, limit: int, score_threshold: float, filters: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Умная фильтрация и ранжирование результатов поиска"""
        try:
            # Форматируем результаты
            results = []
            for result in search_result:
                result_data = {
                    'id': result.id,
                    'score': result.score,
                    'document_id': result.payload.get('document_id'),
                    'chunk_id': result.payload.get('chunk_id'),
                    'content': result.payload.get('content', ''),
                    'section': result.payload.get('section'),
                    'access_level': result.payload.get('access_level'),
                    'chunk_type': result.payload.get('chunk_type', 'text'),
                    'page_number': result.payload.get('page_number'),
                    'section_name': result.payload.get('section_name'),
                    'sheet_name': result.payload.get('sheet_name'),
                    'document_name': result.payload.get('document_name', ''),
                    'metadata': result.payload.get('metadata', {}),
                    'chunk_index': result.payload.get('chunk_index', 0),
                    'content_length': result.payload.get('content_length', 0),
                    'has_images': result.payload.get('has_images', False),
                    'file_type': result.payload.get('file_type', ''),
                    'uploaded_at': result.payload.get('uploaded_at', ''),
                    'processing_timestamp': result.payload.get('processing_timestamp', '')
                }
                
                # Remove None values
                result_data = {k: v for k, v in result_data.items() if v is not None}
                results.append(result_data)
            
            if not results:
                return []
            
            # 1. Фильтрация по качеству контента
            filtered_results = []
            for result in results:
                content = result.get('content', '')
                score = result.get('score', 0)
                
                # Отфильтровываем слишком короткие чанки
                if len(content.strip()) < 20:
                    continue
                
                # Отфильтровываем чанки с очень низким скором
                if score < score_threshold * 0.9:
                    continue
                
                # Отфильтровываем чанки с большим количеством специальных символов
                special_chars = sum(1 for c in content if not c.isalnum() and not c.isspace())
                if special_chars > len(content) * 0.3:  # Больше 30% специальных символов
                    continue
                
                filtered_results.append(result)
            
            # 2. Дублирование по документу - оставляем только лучшие чанки
            document_chunks = {}
            for result in filtered_results:
                doc_id = result.get('document_id')
                if doc_id not in document_chunks:
                    document_chunks[doc_id] = []
                document_chunks[doc_id].append(result)
            
            # Для каждого документа оставляем максимум 3 лучших чанка
            deduplicated_results = []
            for doc_id, chunks in document_chunks.items():
                # Сортируем чанки по скору и берем лучшие
                sorted_chunks = sorted(chunks, key=lambda x: x.get('score', 0), reverse=True)
                deduplicated_results.extend(sorted_chunks[:3])
            
            # 3. Сортировка по релевантности и качеству
            def calculate_quality_score(result):
                base_score = result.get('score', 0)
                content_length = result.get('content_length', 0)
                
                # Бонус за оптимальную длину контента (100-500 символов)
                length_bonus = 0
                if 100 <= content_length <= 500:
                    length_bonus = 0.1
                elif content_length > 500:
                    length_bonus = -0.05  # Штраф за слишком длинные чанки
                
                # Бонус за тип чанка (предпочитаем текст)
                type_bonus = 0.05 if result.get('chunk_type') == 'text' else 0
                
                # Бонус за наличие метаданных
                metadata_bonus = 0.02 if result.get('metadata') else 0
                
                return base_score + length_bonus + type_bonus + metadata_bonus
            
            # Сортируем по качеству
            deduplicated_results.sort(key=calculate_quality_score, reverse=True)
            
            # 4. Ограничиваем количество результатов
            final_results = deduplicated_results[:limit]
            
            # 5. Логируем результаты фильтрации
            logger.info(f"Smart filtering: {len(results)} -> {len(filtered_results)} -> {len(deduplicated_results)} -> {len(final_results)} final results")
            
            return final_results
            
        except Exception as e:
            logger.error(f"Error in smart filtering: {e}")
            # Fallback to original results
            return results[:limit] if 'results' in locals() else []


# Global instance
vector_service = VectorService()
