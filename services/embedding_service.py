from openai import OpenAI
from sentence_transformers import SentenceTransformer
from config import settings
import logging
from typing import List, Union, Optional
import numpy as np
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


class EmbeddingService:
    def __init__(self):
        self.openai_client = OpenAI(api_key=settings.openai_api_key)
        self.provider = settings.embedding_provider
        self.model_name = settings.embedding_model
        
        # Initialize SentenceTransformers if using local embeddings
        self.local_model = None
        if self.provider == "sentence_transformers":
            try:
                self.local_model = SentenceTransformer(self.model_name)
                logger.info(f"Loaded local embedding model: {self.model_name}")
            except Exception as e:
                logger.error(f"Error loading local embedding model: {e}")
                # Fallback to OpenAI
                self.provider = "openai"
                logger.info("Falling back to OpenAI embeddings")
        
        # Set vector size based on model
        self.vector_size = self._get_vector_size()
    
    def _get_vector_size(self) -> int:
        """Get vector size based on the embedding model"""
        if self.provider == "openai":
            return 1536  # text-embedding-3-small
        elif self.provider == "sentence_transformers":
            if "all-MiniLM-L6-v2" in self.model_name:
                return 384
            elif "all-mpnet-base-v2" in self.model_name:
                return 768
            else:
                return 384  # Default
        return 384
    
    def get_embeddings(self, texts: Union[str, List[str]], 
                       batch_size: int = 100) -> Union[np.ndarray, List[np.ndarray]]:
        """Get embeddings for text(s)"""
        if isinstance(texts, str):
            texts = [texts]
            single_text = True
        else:
            single_text = False
        
        try:
            if self.provider == "openai":
                embeddings = self._get_openai_embeddings(texts, batch_size)
            elif self.provider == "sentence_transformers":
                embeddings = self._get_local_embeddings(texts, batch_size)
            else:
                raise ValueError(f"Unsupported embedding provider: {self.provider}")
            
            if single_text:
                return embeddings[0]
            return embeddings
            
        except Exception as e:
            logger.error(f"Error getting embeddings: {e}")
            raise
    
    def _get_openai_embeddings(self, texts: List[str], batch_size: int) -> List[np.ndarray]:
        """Get embeddings using OpenAI API"""
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            try:
                response = self.openai_client.embeddings.create(
                    model=settings.embedding_openai_model,
                    input=batch
                )
                
                batch_embeddings = [np.array(data.embedding) for data in response.data]
                embeddings.extend(batch_embeddings)
                
                # Rate limiting
                if len(batch) > 1:
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Error getting OpenAI embeddings for batch {i//batch_size}: {e}")
                raise
        
        return embeddings
    
    def _get_local_embeddings(self, texts: List[str], batch_size: int) -> List[np.ndarray]:
        """Get embeddings using local SentenceTransformers model"""
        if not self.local_model:
            raise ValueError("Local embedding model not initialized")
        
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            
            try:
                batch_embeddings = self.local_model.encode(batch, convert_to_numpy=True)
                
                if len(batch) == 1:
                    embeddings.append(batch_embeddings)
                else:
                    embeddings.extend(batch_embeddings)
                    
            except Exception as e:
                logger.error(f"Error getting local embeddings for batch {i//batch_size}: {e}")
                raise
        
        return embeddings
    
    async def get_embeddings_async(self, texts: Union[str, List[str]], 
                                  batch_size: int = 100) -> Union[np.ndarray, List[np.ndarray]]:
        """Get embeddings asynchronously"""
        loop = asyncio.get_event_loop()
        
        with ThreadPoolExecutor() as executor:
            if isinstance(texts, str):
                texts = [texts]
                single_text = True
            else:
                single_text = False
            
            embeddings = await loop.run_in_executor(
                executor, 
                self.get_embeddings, 
                texts, 
                batch_size
            )
            
            if single_text:
                return embeddings[0]
            return embeddings
    
    def get_embedding_dimension(self) -> int:
        """Get the dimension of embeddings"""
        return self.vector_size
    
    def get_model_info(self) -> dict:
        """Get information about the embedding model"""
        return {
            "provider": self.provider,
            "model": self.model_name,
            "vector_size": self.vector_size,
            "batch_size": 100
        }
    
    def validate_embedding(self, embedding: np.ndarray) -> bool:
        """Validate that an embedding has the correct shape"""
        if embedding.shape[0] != self.vector_size:
            logger.error(f"Embedding dimension mismatch: expected {self.vector_size}, got {embedding.shape[0]}")
            return False
        return True
    
    def normalize_embedding(self, embedding: np.ndarray) -> np.ndarray:
        """Normalize embedding vector to unit length"""
        norm = np.linalg.norm(embedding)
        if norm > 0:
            return embedding / norm
        return embedding


# Global instance
embedding_service = EmbeddingService()

def get_embedding_service() -> EmbeddingService:
    """Get the global embedding service instance"""
    return embedding_service
