import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.database import get_db
from database.models import Conversation, ConversationMessage, AccessToken
from config import settings

logger = logging.getLogger(__name__)


class ConversationService:
    """Handles conversation persistence and management"""
    
    def __init__(self):
        pass
    
    def create_conversation(self, session_id: str, title: str = None, 
                           user_context: str = None, user_id: int = None) -> Conversation:
        """Create a new conversation"""
        try:
            db = next(get_db())
            try:
                conversation = Conversation(
                    session_id=session_id,
                    user_id=user_id,  # Используем user_id вместо access_token_id
                    title=title,
                    user_context=user_context,
                    created_at=datetime.now(),
                    last_activity=datetime.now()
                )
                
                db.add(conversation)
                db.commit()
                db.refresh(conversation)
                
                logger.info(f"Created conversation {conversation.id} with session {session_id}")
                return conversation
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error creating conversation: {e}")
            raise
    
    def add_message(self, conversation_id: int, role: str, content: str,
                    source_chunks: List[int] = None, source_documents: List[int] = None,
                    tokens_used: int = None, processing_time: float = None) -> ConversationMessage:
        """Add a message to a conversation"""
        try:
            db = next(get_db())
            try:
                message = ConversationMessage(
                    conversation_id=conversation_id,
                    role=role,
                    content=content,
                    source_chunks=source_chunks,
                    source_documents=source_documents,
                    tokens_used=tokens_used,
                    processing_time=processing_time,
                    created_at=datetime.now()
                )
                
                db.add(message)
                
                # Update conversation last activity
                conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
                if conversation:
                    conversation.last_activity = datetime.now()
                
                db.commit()
                db.refresh(message)
                
                logger.info(f"Added message {message.id} to conversation {conversation_id}")
                return message
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            raise
    
    def get_conversation(self, conversation_id: int) -> Optional[Conversation]:
        """Get conversation by ID"""
        try:
            db = next(get_db())
            try:
                return db.query(Conversation).filter(Conversation.id == conversation_id).first()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error getting conversation {conversation_id}: {e}")
            return None
    
    def get_conversation_by_session(self, session_id: str) -> Optional[Conversation]:
        """Get conversation by session ID"""
        try:
            db = next(get_db())
            try:
                return db.query(Conversation).filter(Conversation.session_id == session_id).first()
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error getting conversation by session {session_id}: {e}")
            return None
    
    def get_conversation_messages(self, conversation_id: int, limit: int = 50) -> List[ConversationMessage]:
        """Get messages for a conversation"""
        try:
            db = next(get_db())
            try:
                messages = db.query(ConversationMessage)\
                    .filter(ConversationMessage.conversation_id == conversation_id)\
                    .order_by(ConversationMessage.created_at.desc())\
                    .limit(limit)\
                    .all()
                
                # Return in chronological order
                return list(reversed(messages))
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error getting messages for conversation {conversation_id}: {e}")
            return []
    
    def get_conversation_history(self, conversation_id: int) -> Dict[str, Any]:
        """Get complete conversation history"""
        try:
            conversation = self.get_conversation(conversation_id)
            if not conversation:
                return {}
            
            messages = self.get_conversation_messages(conversation_id)
            
            return {
                'conversation_id': conversation.id,
                'session_id': conversation.session_id,
                'title': conversation.title,
                'user_context': conversation.user_context,
                'messages': [
                    {
                        'id': msg.id,
                        'role': msg.role,
                        'content': msg.content,
                        'source_chunks': msg.source_chunks,
                        'source_documents': msg.source_documents,
                        'tokens_used': msg.tokens_used,
                        'processing_time': msg.processing_time,
                        'created_at': msg.created_at.isoformat()
                    }
                    for msg in messages
                ],
                'total_messages': len(messages),
                'created_at': conversation.created_at.isoformat(),
                'last_activity': conversation.last_activity.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting conversation history {conversation_id}: {e}")
            return {}
    
    def update_conversation_title(self, conversation_id: int, title: str) -> bool:
        """Update conversation title"""
        try:
            db = next(get_db())
            try:
                conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
                if conversation:
                    conversation.title = title
                    conversation.last_activity = datetime.now()
                    db.commit()
                    return True
                return False
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error updating conversation title {conversation_id}: {e}")
            return False
    
    def delete_conversation(self, conversation_id: int) -> bool:
        """Delete a conversation and all its messages"""
        try:
            db = next(get_db())
            try:
                # Delete messages first (cascade should handle this, but explicit for safety)
                db.query(ConversationMessage).filter(ConversationMessage.conversation_id == conversation_id).delete()
                
                # Delete conversation
                result = db.query(Conversation).filter(Conversation.id == conversation_id).delete()
                db.commit()
                
                return result > 0
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error deleting conversation {conversation_id}: {e}")
            return False
    
    def get_user_conversations(self, access_token_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Get conversations for a specific access token"""
        try:
            db = next(get_db())
            try:
                conversations = db.query(Conversation)\
                    .filter(Conversation.access_token_id == access_token_id)\
                    .order_by(Conversation.last_activity.desc())\
                    .limit(limit)\
                    .all()
                
                result = []
                for conv in conversations:
                    # Get message count
                    message_count = db.query(ConversationMessage)\
                        .filter(ConversationMessage.conversation_id == conv.id)\
                        .count()
                    
                    result.append({
                        'id': conv.id,
                        'session_id': conv.session_id,
                        'title': conv.title,
                        'user_context': conv.user_context,
                        'message_count': message_count,
                        'created_at': conv.created_at.isoformat(),
                        'last_activity': conv.last_activity.isoformat()
                    })
                
                return result
                
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error getting user conversations: {e}")
            return []
    
    def cleanup_old_conversations(self, days_old: int = 30) -> int:
        """Clean up conversations older than specified days"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_old)
            
            db = next(get_db())
            try:
                # Find old conversations
                old_conversations = db.query(Conversation)\
                    .filter(Conversation.last_activity < cutoff_date)\
                    .all()
                
                deleted_count = 0
                for conv in old_conversations:
                    if self.delete_conversation(conv.id):
                        deleted_count += 1
                
                logger.info(f"Cleaned up {deleted_count} old conversations")
                return deleted_count
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error cleaning up old conversations: {e}")
            return 0


# Global instance
conversation_service = ConversationService()
