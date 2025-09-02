import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from database.database import SessionLocal
from database.models import Conversation, ConversationMessage, Document
from services.embedding_service import embedding_service
import json
import re

logger = logging.getLogger(__name__)


class SessionContextService:
    """Manages session context and conversational memory for RAG system"""
    
    def __init__(self):
        self.session_cache = {}  # In-memory cache for active sessions
    
    def get_db_session(self):
        """Get a database session"""
        return SessionLocal()
    
    async def get_or_create_conversation(self, session_id: str, user_id: int, 
                                       initial_context: Optional[str] = None) -> Dict[str, Any]:
        """Get existing conversation or create new one - returns plain dict, not SQLAlchemy object"""
        try:
            db = self.get_db_session()
            try:
                # Try to find existing conversation
                conversation = db.query(Conversation).filter(
                    Conversation.session_id == session_id
                ).first()
                
                if conversation:
                    # Update last activity
                    conversation.last_activity = datetime.now()
                    db.commit()
                    logger.info(f"📝 Retrieved existing conversation: {session_id}")
                    
                    # Return as plain dict to avoid session binding issues
                    return {
                        'id': conversation.id,
                        'session_id': conversation.session_id,
                        'user_id': conversation.user_id,  # Используем user_id вместо access_token_id
                        'title': conversation.title,
                        'user_context': conversation.user_context,
                        'current_section': conversation.current_section,
                        'document_context': conversation.document_context or [],
                        'search_context': conversation.search_context or [],
                        'created_at': conversation.created_at,
                        'last_activity': conversation.last_activity
                    }
                else:
                    # Create new conversation
                    conversation = Conversation(
                        session_id=session_id,
                        user_id=user_id,  # Используем user_id
                        title="New Conversation",
                        user_context=initial_context,
                        document_context=[],
                        search_context=[],
                        current_section=None
                    )
                    db.add(conversation)
                    db.commit()
                    db.refresh(conversation)
                    logger.info(f"🆕 Created new conversation: {session_id}")
                    
                    # Return as plain dict
                    return {
                        'id': conversation.id,
                        'session_id': conversation.session_id,
                        'user_id': conversation.user_id,  # Используем user_id вместо access_token_id
                        'title': conversation.title,
                        'user_context': conversation.user_context,
                        'current_section': conversation.current_section,
                        'document_context': conversation.document_context or [],
                        'search_context': conversation.search_context or [],
                        'created_at': conversation.created_at,
                        'last_activity': conversation.last_activity
                    }
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Failed to get/create conversation: {e}")
            raise
    
    def _clean_text_for_database(self, text: str) -> str:
        """Очищает текст от некорректных Unicode символов для безопасного сохранения в БД"""
        if not text:
            return text
        
        try:
            # Удаляем NULL символы и другие проблемные символы
            cleaned = text.replace('\u0000', '')  # NULL символ
            cleaned = cleaned.replace('\u0001', '')  # START OF HEADING
            cleaned = cleaned.replace('\u0002', '')  # START OF TEXT
            cleaned = cleaned.replace('\u0003', '')  # END OF TEXT
            cleaned = cleaned.replace('\u0004', '')  # END OF TRANSMISSION
            cleaned = cleaned.replace('\u0005', '')  # ENQUIRY
            cleaned = cleaned.replace('\u0006', '')  # ACKNOWLEDGE
            cleaned = cleaned.replace('\u0007', '')  # BELL
            cleaned = cleaned.replace('\u0008', '')  # BACKSPACE
            cleaned = cleaned.replace('\u0009', '')  # HORIZONTAL TAB
            cleaned = cleaned.replace('\u000A', '')  # LINE FEED
            cleaned = cleaned.replace('\u000B', '')  # VERTICAL TAB
            cleaned = cleaned.replace('\u000C', '')  # FORM FEED
            cleaned = cleaned.replace('\u000D', '')  # CARRIAGE RETURN
            cleaned = cleaned.replace('\u000E', '')  # SHIFT OUT
            cleaned = cleaned.replace('\u000F', '')  # SHIFT IN
            
            # Удаляем другие проблемные символы
            cleaned = cleaned.replace('\u0010', '')  # DATA LINK ESCAPE
            cleaned = cleaned.replace('\u0011', '')  # DEVICE CONTROL ONE
            cleaned = cleaned.replace('\u0012', '')  # DEVICE CONTROL TWO
            cleaned = cleaned.replace('\u0013', '')  # DEVICE CONTROL THREE
            cleaned = cleaned.replace('\u0014', '')  # DEVICE CONTROL FOUR
            cleaned = cleaned.replace('\u0015', '')  # NEGATIVE ACKNOWLEDGE
            cleaned = cleaned.replace('\u0016', '')  # SYNCHRONOUS IDLE
            cleaned = cleaned.replace('\u0017', '')  # END OF TRANSMISSION BLOCK
            cleaned = cleaned.replace('\u0018', '')  # CANCEL
            cleaned = cleaned.replace('\u0019', '')  # END OF MEDIUM
            cleaned = cleaned.replace('\u001A', '')  # SUBSTITUTE
            cleaned = cleaned.replace('\u001B', '')  # ESCAPE
            cleaned = cleaned.replace('\u001C', '')  # FILE SEPARATOR
            cleaned = cleaned.replace('\u001D', '')  # GROUP SEPARATOR
            cleaned = cleaned.replace('\u001E', '')  # RECORD SEPARATOR
            cleaned = cleaned.replace('\u001F', '')  # UNIT SEPARATOR
            
            # Удаляем символы DEL и выше 0x7F (не-ASCII)
            cleaned = ''.join(char for char in cleaned if ord(char) < 0x7F or ord(char) > 0x9F)
            
            # Удаляем множественные пробелы и переносы строк
            import re
            cleaned = re.sub(r'\s+', ' ', cleaned)
            cleaned = cleaned.strip()
            
            return cleaned
        except Exception as e:
            logger.warning(f"⚠️ Ошибка очистки текста: {e}")
            # Возвращаем безопасную версию
            return text[:1000] if text else ""  # Ограничиваем длину
    
    def _clean_search_results(self, search_results: Any) -> Any:
        """Очищает результаты поиска от некорректных символов"""
        if not search_results:
            return search_results
        
        try:
            if isinstance(search_results, str):
                # Если это JSON строка, парсим и очищаем
                import json
                try:
                    parsed = json.loads(search_results)
                    return self._clean_search_results(parsed)
                except:
                    # Если не JSON, очищаем как обычный текст
                    return self._clean_text_for_database(search_results)
            
            elif isinstance(search_results, list):
                cleaned_list = []
                for item in search_results:
                    if isinstance(item, dict):
                        cleaned_item = {}
                        for key, value in item.items():
                            if key == 'content' and isinstance(value, str):
                                cleaned_item[key] = self._clean_text_for_database(value)
                            else:
                                cleaned_item[key] = value
                        cleaned_list.append(cleaned_item)
                    else:
                        cleaned_list.append(item)
                return cleaned_list
            
            elif isinstance(search_results, dict):
                cleaned_dict = {}
                for key, value in search_results.items():
                    if key == 'content' and isinstance(value, str):
                        cleaned_dict[key] = self._clean_text_for_database(value)
                    else:
                        cleaned_dict[key] = value
                return cleaned_dict
            
            else:
                return search_results
                
        except Exception as e:
            logger.warning(f"⚠️ Ошибка очистки результатов поиска: {e}")
            return []
    
    async def add_message_to_conversation(self, conversation_id: int, role: str, content: str,
                                        search_context: Optional[Dict] = None) -> ConversationMessage:
        """Add a message to the conversation with search context"""
        try:
            db = self.get_db_session()
            try:
                # Очищаем данные перед сохранением в БД
                cleaned_content = self._clean_text_for_database(content)
                cleaned_search_query = self._clean_text_for_database(search_context.get('query') if search_context else None)
                cleaned_search_results = self._clean_search_results(search_context.get('results') if search_context else None)
                cleaned_used_sections = search_context.get('sections') if search_context else None
                
                message = ConversationMessage(
                    conversation_id=conversation_id,
                    role=role,
                    content=cleaned_content,
                    search_query=cleaned_search_query,
                    search_results=cleaned_search_results,
                    used_sections=cleaned_used_sections,
                    context_relevance_score=search_context.get('relevance_score') if search_context else None,
                    source_chunks=search_context.get('source_chunks') if search_context else None,
                    source_documents=search_context.get('source_documents') if search_context else None
                )
                
                db.add(message)
                db.commit()
                db.refresh(message)
                
                # Update conversation last activity - use the same session
                try:
                    conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
                    if conversation:
                        conversation.last_activity = datetime.now()
                        db.commit()
                except Exception as e:
                    logger.warning(f"⚠️ Could not update conversation last activity: {e}")
                
                logger.info(f"💬 Added {role} message to conversation {conversation_id}")
                return message
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Failed to add message: {e}")
            raise
    
    async def get_conversation_context(self, session_id: str, 
                                     max_messages: int = 10) -> Dict[str, Any]:
        """Get conversation context including history and document memory"""
        try:
            db = self.get_db_session()
            try:
                conversation = db.query(Conversation).filter(
                    Conversation.session_id == session_id
                ).first()
                
                if not conversation:
                    return {
                        'session_id': session_id,
                        'messages': [],
                        'document_context': [],
                        'current_section': None,
                        'search_context': []
                    }
                
                # Get recent messages
                messages = db.query(ConversationMessage).filter(
                    ConversationMessage.conversation_id == conversation.id
                ).order_by(ConversationMessage.created_at.desc()).limit(max_messages).all()
                
                # Reverse to get chronological order
                messages = list(reversed(messages))
                
                # Extract document context from messages - convert to plain dicts
                document_context = []
                search_context = []
                
                for msg in messages:
                    if msg.search_results:
                        # Add document content from previous searches
                        # Convert SQLAlchemy objects to plain dicts
                        search_results = msg.search_results
                        if isinstance(search_results, str):
                            try:
                                import json
                                search_results = json.loads(search_results)
                            except:
                                search_results = []
                        
                        if isinstance(search_results, list):
                            for result in search_results:
                                if isinstance(result, dict) and 'content' in result:
                                    doc_info = {
                                        'content': result['content'],
                                        'document_id': result.get('document_id'),
                                        'section': result.get('section'),
                                        'score': result.get('score', 0.0),
                                        'timestamp': msg.created_at.isoformat(),
                                        'query': msg.search_query
                                    }
                                    document_context.append(doc_info)
                        
                        # Add search context
                        if msg.search_query:
                            used_sections = msg.used_sections
                            if isinstance(used_sections, str):
                                try:
                                    import json
                                    used_sections = json.loads(used_sections)
                                except:
                                    used_sections = []
                            
                            search_context.append({
                                'query': msg.search_query,
                                'sections': used_sections,
                                'timestamp': msg.created_at.isoformat()
                            })
                
                # Convert conversation to plain dict
                conversation_dict = {
                    'id': conversation.id,
                    'session_id': conversation.session_id,
                    'title': conversation.title,
                    'current_section': conversation.current_section,
                    'user_context': conversation.user_context,
                    'created_at': conversation.created_at.isoformat() if conversation.created_at else None,
                    'last_activity': conversation.last_activity.isoformat() if conversation.last_activity else None
                }
                
                return {
                    'session_id': session_id,
                    'conversation_id': conversation.id,
                    'messages': [
                        {
                            'role': msg.role,
                            'content': msg.content,
                            'timestamp': msg.created_at.isoformat()
                        } for msg in messages
                    ],
                    'document_context': document_context,
                    'current_section': conversation.current_section,
                    'search_context': search_context
                }
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Failed to get conversation context: {e}")
            return {
                'session_id': session_id,
                'messages': [],
                'document_context': [],
                'current_section': None,
                'search_context': []
            }
    
    async def update_conversation_section(self, session_id: str, section: str) -> bool:
        """Update the current section being discussed in the conversation"""
        try:
            db = self.get_db_session()
            try:
                conversation = db.query(Conversation).filter(
                    Conversation.session_id == session_id
                ).first()
                
                if conversation:
                    conversation.current_section = section
                    conversation.last_activity = datetime.now()
                    db.commit()
                    logger.info(f"🎯 Updated conversation {session_id} section to: {section}")
                    return True
                return False
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Failed to update conversation section: {e}")
            return False
    
    async def should_use_existing_context(self, session_id: str, new_query: str, 
                                        threshold: float = 0.6) -> Tuple[bool, List[Dict], str]:
        """Определить, следует ли использовать существующий контекст вместо нового поиска
        Возвращает: (использовать_существующий, данные_контекста, стратегия)"""
        try:
            context = await self.get_conversation_context(session_id)
            
            if not context['document_context']:
                logger.info("📭 Нет существующего контекста документов - выполняем новый поиск")
                return False, [], "new_search"
            
            # Проверить, связан ли новый запрос с предыдущим контекстом
            if len(context['messages']) < 2:
                logger.info("📝 Недостаточно истории сообщений - выполняем новый поиск")
                return False, [], "new_search"
            
            # Получить последнее сообщение пользователя
            last_user_message = None
            for msg in reversed(context['messages']):
                if msg['role'] == 'user':
                    last_user_message = msg['content']
                    break
            
            if not last_user_message:
                logger.info("📝 Не найдено предыдущее сообщение пользователя - выполняем новый поиск")
                return False, [], "new_search"
            
            # Расширенное обнаружение уточняющих вопросов
            is_clarifying = self._is_clarifying_question(new_query, last_user_message)
            
            if is_clarifying:
                logger.info(f"🔍 Обнаружен уточняющий вопрос: '{new_query}' -> '{last_user_message}'")
                logger.info(f"🔄 Используем существующий контекст для уточняющего вопроса")
                return True, context['document_context'], "context_reuse"
            
            # Вычислить семантическое сходство между запросами
            try:
                similarity = await self._calculate_query_similarity(last_user_message, new_query)
                logger.info(f"📊 Сходство запросов: {similarity:.3f} (порог: {threshold})")
                
                if similarity > threshold:
                    logger.info(f"🔄 Высокое сходство ({similarity:.3f}) - используем существующий контекст")
                    return True, context['document_context'], "context_reuse"
                elif similarity > 0.3:  # Среднее сходство - гибридный подход
                    logger.info(f"🔄 Среднее сходство ({similarity:.3f}) - используем гибридный контекст")
                    return True, context['document_context'], "hybrid_context"
                else:
                    logger.info(f"🆕 Низкое сходство ({similarity:.3f}) - выполняем новый поиск")
                    return False, [], "new_search"
                    
            except Exception as e:
                logger.warning(f"⚠️ Не удалось вычислить сходство: {e}")
                # Резервный вариант: если вычисление сходства не удалось, проверить паттерны уточнения
                if self._is_clarifying_question(new_query, last_user_message):
                    logger.info(f"🔄 Резервный вариант: Используем существующий контекст на основе паттернов уточнения")
                    return True, context['document_context'], "context_reuse"
                return False, [], "new_search"
                
        except Exception as e:
            logger.error(f"❌ Не удалось проверить релевантность контекста: {e}")
            return False, [], "new_search"
    
    async def _calculate_query_similarity(self, query1: str, query2: str) -> float:
        """Calculate semantic similarity between two queries"""
        try:
            # Get embeddings for both queries
            embedding1 = await embedding_service.get_embeddings_async(query1)
            embedding2 = await embedding_service.get_embeddings_async(query2)
            
            # Calculate cosine similarity
            import numpy as np
            
            # Convert to numpy arrays
            vec1 = np.array(embedding1)
            vec2 = np.array(embedding2)
            
            # Calculate cosine similarity
            dot_product = np.dot(vec1, vec2)
            norm1 = np.linalg.norm(vec1)
            norm2 = np.linalg.norm(vec2)
            
            if norm1 == 0 or norm2 == 0:
                return 0.0
            
            similarity = dot_product / (norm1 * norm2)
            return float(similarity)
            
        except Exception as e:
            logger.error(f"❌ Failed to calculate similarity: {e}")
            return 0.0
    
    async def merge_contexts(self, existing_context: List[Dict], new_results: List[Dict],
                            max_context_size: int = 20) -> List[Dict]:
        """Merge existing context with new search results"""
        try:
            # Combine contexts
            merged = existing_context + new_results
            
            # Remove duplicates based on document_id and content
            seen = set()
            unique_context = []
            
            for item in merged:
                key = (item.get('document_id'), item.get('content', '')[:100])
                if key not in seen:
                    seen.add(key)
                    unique_context.append(item)
            
            # Sort by relevance score and timestamp
            unique_context.sort(key=lambda x: (
                x.get('score', 0),
                x.get('timestamp', '')
            ), reverse=True)
            
            # Limit context size
            return unique_context[:max_context_size]
            
        except Exception as e:
            logger.error(f"❌ Failed to merge contexts: {e}")
            return new_results
    
    async def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """Clean up old inactive sessions"""
        try:
            db = self.get_db_session()
            try:
                cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
                
                # Find old conversations
                old_conversations = db.query(Conversation).filter(
                    Conversation.last_activity < cutoff_time
                ).all()
                
                deleted_count = 0
                for conv in old_conversations:
                    db.delete(conv)
                    deleted_count += 1
                
                db.commit()
                logger.info(f"🧹 Cleaned up {deleted_count} old sessions")
                return deleted_count
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old sessions: {e}")
            return 0

    async def clear_document_context(self, session_id: str) -> bool:
        """Очищает контекст документов для указанной сессии"""
        try:
            db = self.get_db_session()
            try:
                conversation = db.query(Conversation).filter(
                    Conversation.session_id == session_id
                ).first()
                
                if conversation:
                    conversation.document_context = []
                    conversation.search_context = []
                    db.commit()
                    logger.info(f"🧹 Очищен контекст документов для сессии {session_id}")
                    return True
                else:
                    logger.warning(f"⚠️ Сессия {session_id} не найдена для очистки контекста")
                    return False
                    
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ Ошибка при очистке контекста документов: {e}")
            return False

    def _is_clarifying_question(self, new_query: str, previous_query: str) -> bool:
        """Определить, является ли вопрос уточнением предыдущего"""
        try:
            # Конвертировать в нижний регистр для сопоставления паттернов
            new_lower = new_query.lower().strip()
            prev_lower = previous_query.lower().strip()
            
            # Паттерн 1: Начинается с уточняющих слов
            clarifying_starters = [
                'а что', 'а если', 'а как', 'а когда', 'а где', 'а почему',
                'а какая', 'а какие', 'а какой', 'а какое', 'а сколько',
                'что насчет', 'как насчет', 'расскажи подробнее', 'объясни',
                'что именно', 'что конкретно', 'что ты имеешь в виду',
                'а', 'но', 'однако', 'также', 'дополнительно', 'еще',
                'и что', 'и как', 'и когда', 'и где', 'и почему'
            ]
            
            for starter in clarifying_starters:
                if new_lower.startswith(starter):
                    logger.info(f"🔍 Обнаружен уточняющий стартер: '{starter}'")
                    return True
            
            # Паттерн 2: Содержит уточняющие местоимения, ссылающиеся на предыдущий контекст
            clarifying_pronouns = [
                'это', 'то', 'эти', 'те', 'оно', 'они', 'их',
                'вышеупомянутое', 'упомянутое', 'предыдущее', 'то же самое',
                'данный', 'данная', 'данное', 'данные'
            ]
            
            for pronoun in clarifying_pronouns:
                if pronoun in new_lower:
                    logger.info(f"🔍 Обнаружено уточняющее местоимение: '{pronoun}'")
                    return True
            
            # Паттерн 3: Очень короткие вопросы, которые, вероятно, являются уточнениями
            if len(new_lower.split()) <= 3 and any(word in new_lower for word in ['что', 'как', 'почему', 'когда', 'где', 'какой', 'какая', 'какое']):
                logger.info(f"🔍 Обнаружен короткий уточняющий вопрос: '{new_lower}'")
                return True
            
            # Паттерн 4: Вопросы, которые ссылаются на конкретные детали из предыдущего запроса
            # Извлечь ключевые существительные из предыдущего запроса
            prev_nouns = re.findall(r'\b\w+(?:\s+\w+)*\b', prev_lower)
            prev_nouns = [noun for noun in prev_nouns if len(noun) > 3 and noun not in ['что', 'когда', 'где', 'как', 'почему', 'о', 'с', 'от', 'в', 'во', 'на', 'за', 'под', 'над', 'перед', 'после', 'между', 'среди', 'через', 'вопреки', 'к', 'по', 'на']]
            
            # Проверить, содержит ли новый запрос любое из этих существительных
            for noun in prev_nouns[:5]:  # Проверить первые 5 существительных
                if noun in new_lower:
                    logger.info(f"🔍 Обнаружена ссылка на контекст: '{noun}' из предыдущего запроса")
                    return True
            
            # Паттерн 5: Вопросы, которые являются прямыми продолжениями
            follow_up_patterns = [
                (r'минимальная.*высота', r'высота.*потолка'),
                (r'требования.*помещения', r'высота.*потолка'),
                (r'безопасность.*продуктов', r'гигиенические.*практики'),
                (r'стандарты', r'конкретные.*практики'),
                (r'процедуры', r'детальные.*шаги'),
                (r'требования.*комнаты', r'высота.*потолка'),
                (r'стандарты.*безопасности', r'гигиенические.*меры')
            ]
            
            for prev_pattern, new_pattern in follow_up_patterns:
                if re.search(prev_pattern, prev_lower) and re.search(new_pattern, new_lower):
                    logger.info(f"🔍 Обнаружен паттерн продолжения: '{prev_pattern}' -> '{new_pattern}'")
                    return True
            
            logger.info(f"🔍 Уточняющие паттерны не обнаружены для: '{new_lower}'")
            return False
            
        except Exception as e:
            logger.warning(f"⚠️ Ошибка в обнаружении уточняющего вопроса: {e}")
            return False


# Global instance
session_context_service = SessionContextService()
