from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_community.vectorstores import Qdrant
from langchain_openai import OpenAIEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import settings
from services.source_linker import source_linker
import logging
from typing import List, Dict, Any, Optional
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class RAGService:
    def __init__(self):
        self.llm = ChatOpenAI(
            model=settings.openai_model,
            api_key=settings.openai_api_key,
            temperature=0.8,  # Увеличиваем для более креативных ответов
            max_tokens=3000   # Увеличиваем для более развернутых ответов
        )
        
        self.embeddings = OpenAIEmbeddings(
            model=settings.embedding_openai_model,
            openai_api_key=settings.openai_api_key
        )
        
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.chunk_size,
            chunk_overlap=settings.chunk_overlap,
            length_function=len,
            separators=["\n\n", "\n", " ", ""]
        )
        
        # Enhanced system prompt for hybrid responses
        self.system_prompt = """Ты - эксперт по кулинарным вопросам и ресторанному менеджменту. Твоя задача - вести естественный диалог с пользователями.

ВАЖНО: ВСЕГДА отвечай ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, независимо от языка вопроса пользователя.

РЕЖИМЫ ОТВЕТОВ:
1. **ДОКУМЕНТНЫЙ РЕЖИМ** - когда есть релевантная информация в документах
2. **ГИБРИДНЫЙ РЕЖИМ** - комбинируй документы с общими знаниями
3. **ОБЩИЙ РЕЖИМ** - используй общие знания для поддержания диалога

ПРАВИЛА ОТВЕТОВ:
1. Отвечай ТОЛЬКО на русском языке
2. Приоритет - найденным документам, но не ограничивайся только ими
3. Если информации недостаточно в документах - используй общие знания
4. Поддерживай естественный диалог и контекст разговора
5. Задавай уточняющие вопросы для лучшего понимания
6. Предлагай связанные темы для продолжения разговора

ФОРМАТ ОТВЕТА:
- Начинай с прямого ответа на вопрос
- Подкрепляй ответы данными из документов (если есть)
- Добавляй полезную информацию из общих знаний
- Завершай предложением для продолжения диалога

ПОМНИ: Ты не просто поисковик, а собеседник-эксперт!"""

    def generate_response(self, query: str, 
                         context_chunks: List[Dict[str, Any]], 
                         conversation_history: List[Dict[str, Any]] = None,
                         session_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Generate AI response using RAG with intelligent strategy selection"""
        try:
            # Analyze question type and determine response strategy
            question_analysis = self._analyze_question_type(query, context_chunks)
            
            # Prepare context from chunks
            context_text = self._prepare_context(context_chunks)
            
            # Prepare conversation messages with strategy-aware approach
            conversation_messages = self._prepare_conversation_messages(
                query, context_chunks, conversation_history, session_context, question_analysis
            )
            
            logger.info(f"🤖 Generating AI response with strategy: {question_analysis['suggested_strategy']}")
            
            # Generate response
            response = self.llm.invoke(conversation_messages)
            
            # Extract source information with enhanced metadata and document links
            sources = self._extract_sources(context_chunks)
            
            # Generate follow-up questions based on strategy
            follow_up_questions = self._generate_follow_up_questions(query, response.content, context_chunks)
            
            return {
                'response': response.content,  # Возвращаем НЕ отформатированный ответ
                'raw_response': response.content,  # Сохраняем оригинальный ответ
                'sources': sources,
                'context_chunks_used': len(context_chunks),
                'timestamp': datetime.now().isoformat(),
                'follow_up_questions': follow_up_questions,
                'session_context_used': session_context is not None,
                'has_document_links': len(sources) > 0,
                'question_analysis': question_analysis,  # Добавляем анализ вопроса
                'response_strategy': question_analysis['suggested_strategy']
            }
            
        except Exception as e:
            logger.error(f"❌ Error generating RAG response: {e}")
            logger.error(f"Query: {query}")
            logger.error(f"Context chunks: {len(context_chunks) if context_chunks else 0}")
            logger.error(f"Session context: {session_context is not None}")
            logger.error(f"Conversation history: {len(conversation_history) if conversation_history else 0}")
            raise
    
    def _prepare_context(self, context_chunks: List[Dict[str, Any]]) -> str:
        """Prepare context text from retrieved chunks with enhanced metadata"""
        context_parts = []
        
        for i, chunk in enumerate(context_chunks):
            chunk_info = f"Document {i+1}:\n"
            
            # Add document metadata
            if chunk.get('document_name'):
                chunk_info += f"Document: {chunk['document_name']}\n"
            if chunk.get('section_name'):
                chunk_info += f"Section: {chunk['section_name']}\n"
            if chunk.get('page_number'):
                chunk_info += f"Page: {chunk['page_number']}\n"
            if chunk.get('chunk_type'):
                chunk_info += f"Type: {chunk['chunk_type']}\n"
            if chunk.get('sheet_name'):
                chunk_info += f"Excel Sheet: {chunk['sheet_name']}\n"
            
            chunk_info += f"Content: {chunk['content']}\n"
            chunk_info += "-" * 50 + "\n"
            
            context_parts.append(chunk_info)
        
        return "\n".join(context_parts)
    
    def _prepare_conversation_messages(self, query: str, context_chunks: List[Dict], 
                                     conversation_history: List[Dict] = None,
                                     session_context: Optional[Dict[str, Any]] = None,
                                     question_analysis: Dict[str, Any] = None) -> List[Dict]:
        """Prepare conversation messages for the LLM with hybrid response support"""
        try:
            # Enhanced system prompt for hybrid responses
            enhanced_system_prompt = """Ты - эксперт по кулинарным вопросам и ресторанному менеджменту. Твоя задача - вести естественный диалог с пользователями.

ВАЖНО: ВСЕГДА отвечай ТОЛЬКО НА РУССКОМ ЯЗЫКЕ, независимо от языка вопроса пользователя.

РЕЖИМЫ ОТВЕТОВ:
1. **ДОКУМЕНТНЫЙ РЕЖИМ** - когда есть релевантная информация в документах
2. **ГИБРИДНЫЙ РЕЖИМ** - комбинируй документы с общими знаниями  
3. **ОБЩИЙ РЕЖИМ** - используй общие знания для поддержания диалога

СТРАТЕГИЯ ДИАЛОГА:
- Если вопрос связан с найденными документами - используй их как основу
- Если вопрос выходит за рамки документов - используй общие знания
- Если это продолжение диалога - поддерживай контекст и естественность
- Задавай уточняющие вопросы для лучшего понимания потребностей
- Предлагай связанные темы для углубления разговора

ПРАВИЛА ОТВЕТОВ:
1. Отвечай ТОЛЬКО на русском языке
2. Приоритет - найденным документам, но не ограничивайся только ими
3. Если информации недостаточно в документах - используй общие знания
4. Поддерживай естественный диалог и контекст разговора
5. Задавай уточняющие вопросы для лучшего понимания
6. Предлагай связанные темы для продолжения разговора

ФОРМАТ ОТВЕТА:
- Начинай с прямого ответа на вопрос
- Подкрепляй ответы данными из документов (если есть)
- Добавляй полезную информацию из общих знаний
- Завершай предложением для продолжения диалога

ПОМНИ: Ты не просто поисковик, а собеседник-эксперт!"""

            # Add session context if available
            if session_context and session_context.get('document_context'):
                try:
                    # Limit to last 5 documents to avoid overwhelming the context
                    recent_docs = session_context['document_context'][-5:]
                    enhanced_system_prompt += f"\n\nПРЕДЫДУЩИЙ КОНТЕКСТ СЕССИИ:\n"
                    enhanced_system_prompt += f"В этой сессии уже обсуждались следующие документы:\n"
                    
                    for i, doc in enumerate(recent_docs, 1):
                        doc_id = doc.get('document_id', 'Неизвестно')
                        section = doc.get('section', 'Неизвестно')
                        query_used = doc.get('query', 'Неизвестно')
                        enhanced_system_prompt += f"{i}. Документ {doc_id} (раздел: {section}) - найден по запросу: '{query_used}'\n"
                    
                    # Add current section focus
                    if session_context.get('current_section'):
                        enhanced_system_prompt += f"\nТЕКУЩИЙ ФОКУС РАЗДЕЛА: {session_context['current_section']}\n"
                        
                except Exception as e:
                    logger.warning(f"⚠️ Could not add session context to prompt: {e}")

            # Add conversation history if available
            if conversation_history:
                try:
                    # Limit to last 5 messages to avoid token overflow
                    recent_history = conversation_history[-5:]
                    enhanced_system_prompt += f"\n\nИСТОРИЯ ДИАЛОГА (последние {len(recent_history)} сообщений):\n"
                    
                    for msg in recent_history:
                        if msg['role'] == 'user':
                            enhanced_system_prompt += f"Пользователь: {msg['content']}\n"
                        else:
                            enhanced_system_prompt += f"Предыдущий ответ: {msg['content']}\n"
                            
                except Exception as e:
                    logger.warning(f"⚠️ Could not add conversation history to prompt: {e}")

            # Add current context with flexible approach
            if context_chunks:
                enhanced_system_prompt += f"\n\nТЕКУЩИЙ КОНТЕКСТ ДОКУМЕНТОВ:\n"
                enhanced_system_prompt += f"Вот найденные релевантные фрагменты документов (используй их как основу, но не ограничивайся только ими):\n\n"
            
            for i, chunk in enumerate(context_chunks, 1):
                enhanced_system_prompt += f"Фрагмент {i}:\n"
                enhanced_system_prompt += f"Содержание: {chunk['content']}\n"
                enhanced_system_prompt += f"Источник: Документ {chunk.get('document_id', 'Неизвестно')}, Раздел: {chunk.get('section', 'Неизвестно')}\n"
                enhanced_system_prompt += f"Релевантность: {chunk.get('score', 0):.2f}\n\n"
            else:
                enhanced_system_prompt += f"\n\nКОНТЕКСТ: В данный момент нет найденных документов по запросу. Используй общие знания для ответа и предложи, какие документы могут быть полезны."

            # Add the user's question with context analysis
            enhanced_system_prompt += f"ВОПРОС ПОЛЬЗОВАТЕЛЯ:\n{query}\n\n"
            
            # Add response strategy guidance based on question analysis
            if question_analysis:
                strategy = question_analysis['suggested_strategy']
                if strategy == 'document_heavy':
                    enhanced_system_prompt += f"\n\nСТРАТЕГИЯ ОТВЕТА: У тебя есть релевантные документы. Сделай акцент на них, но можешь дополнить общими знаниями для более полного ответа."
                elif strategy == 'context_aware':
                    enhanced_system_prompt += f"\n\nСТРАТЕГИЯ ОТВЕТА: Это продолжение диалога. Используй контекст предыдущих сообщений и найденные документы для связного ответа."
                elif strategy == 'general_knowledge':
                    enhanced_system_prompt += f"\n\nСТРАТЕГИЯ ОТВЕТА: Документов не найдено. Используй общие знания и предложи, как можно найти нужную информацию."
                else:  # hybrid
                    enhanced_system_prompt += f"\n\nСТРАТЕГИЯ ОТВЕТА: У тебя есть релевантные документы. Начни с них, но можешь дополнить общими знаниями для более полного ответа."
            else:
                # Default strategy guidance
                if context_chunks:
                    enhanced_system_prompt += f"\n\nСТРАТЕГИЯ ОТВЕТА: У тебя есть релевантные документы. Начни с них, но можешь дополнить общими знаниями для более полного ответа."
                else:
                    enhanced_system_prompt += f"\n\nСТРАТЕГИЯ ОТВЕТА: Документов не найдено. Используй общие знания и предложи, как можно найти нужную информацию."
            
            enhanced_system_prompt += f"\n\nОТВЕТ (обязательно на русском языке, поддерживай диалог):"

            # Add special instructions for follow-up questions
            if question_analysis and question_analysis.get('is_follow_up'):
                enhanced_system_prompt += f"\n\nОСОБЫЕ ИНСТРУКЦИИ ДЛЯ FOLLOW-UP ВОПРОСА:\n"
                enhanced_system_prompt += f"- Это продолжение диалога, поэтому поддерживай естественность\n"
                enhanced_system_prompt += f"- Ссылайся на предыдущие ответы и найденные документы\n"
                enhanced_system_prompt += f"- Если нужно, задавай уточняющие вопросы\n"
                enhanced_system_prompt += f"- Предлагай связанные темы для углубления разговора"
            
            # Add special instructions for clarification questions
            if question_analysis and question_analysis.get('is_clarification'):
                enhanced_system_prompt += f"\n\nОСОБЫЕ ИНСТРУКЦИИ ДЛЯ УТОЧНЯЮЩЕГО ВОПРОСА:\n"
                enhanced_system_prompt += f"- Объясни простыми и понятными словами\n"
                enhanced_system_prompt += f"- Используй примеры и аналогии\n"
                enhanced_system_prompt += f"- Разбивай сложные концепции на простые части\n"
                enhanced_system_prompt += f"- Проверяй понимание пользователя"
            
            # Add special instructions for practical questions
            if question_analysis and question_analysis.get('is_practical'):
                enhanced_system_prompt += f"\n\nОСОБЫЕ ИНСТРУКЦИИ ДЛЯ ПРАКТИЧЕСКОГО ВОПРОСА:\n"
                enhanced_system_prompt += f"- Давай пошаговые инструкции\n"
                enhanced_system_prompt += f"- Указывай важные детали и нюансы\n"
                enhanced_system_prompt += f"- Предупреждай о возможных проблемах\n"
                enhanced_system_prompt += f"- Предлагай альтернативные варианты"

            # Prepare messages for the LLM
            messages = [
                {"role": "system", "content": enhanced_system_prompt}
            ]

            logger.info(f"📝 Подготовлено {len(messages)} сообщений для RAG с {len(context_chunks)} фрагментами контекста")
            return messages

        except Exception as e:
            logger.error(f"❌ Ошибка при подготовке сообщений для RAG: {e}")
            # Fallback to simple prompt
            return [
                {"role": "system", "content": "Ты - эксперт по кулинарным вопросам. Отвечай ТОЛЬКО на русском языке. Используй документы если есть, иначе - общие знания."},
                {"role": "user", "content": f"Вопрос: {query}\n\nКонтекст: {[chunk['content'][:200] + '...' for chunk in context_chunks[:3]] if context_chunks else 'Документы не найдены'}"}
            ]
    
    def _extract_sources(self, context_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract source information with enhanced metadata and document links"""
        try:
            # Используем SourceLinker для генерации ссылок
            enhanced_chunks = source_linker.generate_document_links(context_chunks)
            
            sources = []
            for chunk in enhanced_chunks:
                source_info = {
                    'chunk_id': chunk.get('id'),
                    'document_id': chunk.get('document_id'),
                    'document_name': chunk.get('document_name', 'Неизвестный документ'),
                    'section_name': chunk.get('section_name', ''),
                    'page_number': chunk.get('page_number'),
                    'chunk_type': chunk.get('chunk_type', 'text'),
                    'relevance_score': chunk.get('score', 0.0),
                    'content_preview': chunk.get('content', '')[:200] + '...' if len(chunk.get('content', '')) > 200 else chunk.get('content', ''),
                    'metadata': {},
                    # Добавляем ссылки на документы
                    'document_link': chunk.get('document_link', {}),
                    'specific_link': chunk.get('specific_link', {}),
                    'display_info': chunk.get('display_info', {})
                }
                
                # Добавляем Excel-специфичные метаданные
                if chunk.get('sheet_name'):
                    source_info['metadata']['sheet_name'] = chunk['sheet_name']
                    source_info['section_name'] = f"Лист: {chunk['sheet_name']}"
                
                # Добавляем PDF-специфичные метаданные
                if chunk.get('page_number'):
                    source_info['metadata']['page_number'] = chunk['page_number']
                    if not source_info['section_name']:
                        source_info['section_name'] = f"Страница {chunk['page_number']}"
                
                # Добавляем тип документа
                if chunk.get('file_type'):
                    source_info['metadata']['file_type'] = chunk['file_type']
                
                # Добавляем уровень доступа для фильтрации
                if chunk.get('access_level'):
                    source_info['metadata']['access_level'] = chunk['access_level']
                
                sources.append(source_info)
            
            # Сортируем по релевантности
            sources.sort(key=lambda x: x['relevance_score'], reverse=True)
            
            logger.info(f"📚 Извлечено {len(sources)} источников с ссылками на документы")
            return sources
            
        except Exception as e:
            logger.error(f"❌ Ошибка при извлечении источников: {e}")
            # Fallback к базовому извлечению
            return self._extract_sources_fallback(context_chunks)
    
    def _extract_sources_fallback(self, context_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Fallback метод для извлечения источников без ссылок"""
        sources = []
        
        for chunk in context_chunks:
            source_info = {
                'chunk_id': chunk.get('id'),
                'document_id': chunk.get('document_id'),
                'document_name': chunk.get('document_name', 'Неизвестный документ'),
                'section_name': chunk.get('section_name', ''),
                'page_number': chunk.get('page_number'),
                'chunk_type': chunk.get('chunk_type', 'text'),
                'relevance_score': chunk.get('score', 0.0),
                'content_preview': chunk.get('content', '')[:200] + '...' if len(chunk.get('content', '')) > 200 else chunk.get('content', ''),
                'metadata': {}
            }
            
            # Добавляем Excel-специфичные метаданные
            if chunk.get('sheet_name'):
                source_info['metadata']['sheet_name'] = chunk['sheet_name']
                source_info['section_name'] = f"Лист: {chunk['sheet_name']}"
            
            # Добавляем PDF-специфичные метаданные
            if chunk.get('page_number'):
                source_info['metadata']['page_number'] = chunk['page_number']
                if not source_info['section_name']:
                    source_info['section_name'] = f"Страница {chunk['page_number']}"
            
            # Добавляем тип документа
            if chunk.get('file_type'):
                source_info['metadata']['file_type'] = chunk['file_type']
            
            # Добавляем уровень доступа для фильтрации
            if chunk.get('access_level'):
                source_info['metadata']['access_level'] = chunk['access_level']
            
            sources.append(source_info)
        
        # Сортируем по релевантности
        sources.sort(key=lambda x: x['relevance_score'], reverse=True)
        return sources
    
    def create_enhanced_prompt(self, query: str, 
                              context_chunks: List[Dict[str, Any]], 
                              user_context: str = "") -> str:
        """Create an enhanced prompt with better culinary context"""
        base_prompt = self.system_prompt
        
        if user_context:
            base_prompt += f"\n\nUser Context: {user_context}"
        
        context_text = self._prepare_context(context_chunks)
        
        enhanced_prompt = f"""{base_prompt}

Document Context:
{context_text}

User Question: {query}

Instructions:
1. Answer based on the provided documents
2. Cite specific sources (document names, sections, pages)
3. Provide practical culinary advice
4. If information is missing, acknowledge it
5. Suggest related topics or follow-up questions"""
        
        return enhanced_prompt
    
    def validate_response(self, response: str, context_chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Validate that the response is based on the provided context"""
        try:
            # Simple validation - check if response mentions document content
            context_keywords = set()
            for chunk in context_chunks:
                # Extract key terms from context
                words = chunk.get('content', '').lower().split()[:20]  # First 20 words
                context_keywords.update(words)
            
            response_words = set(response.lower().split())
            overlap = len(context_keywords.intersection(response_words))
            
            relevance_score = min(1.0, overlap / max(1, len(context_keywords)))
            
            return {
                'is_relevant': relevance_score > 0.1,
                'relevance_score': relevance_score,
                'context_keywords_found': overlap,
                'total_context_keywords': len(context_keywords)
            }
            
        except Exception as e:
            logger.error(f"Error validating response: {e}")
            return {'is_relevant': True, 'relevance_score': 0.5, 'error': str(e)}
    
    def get_conversation_summary(self, conversation_history: List[Dict[str, Any]]) -> str:
        """Generate a summary of the conversation"""
        try:
            if not conversation_history:
                return "No conversation history available."
            
            # Extract key topics from conversation
            topics = []
            for msg in conversation_history:
                if msg['role'] == 'user':
                    content = msg['content'].lower()
                    if 'recipe' in content:
                        topics.append('recipes')
                    if 'safety' in content or 'procedure' in content:
                        topics.append('safety procedures')
                    if 'kitchen' in content:
                        topics.append('kitchen operations')
                    if 'restaurant' in content:
                        topics.append('restaurant management')
            
            unique_topics = list(set(topics))
            
            summary = f"Conversation covered {len(unique_topics)} main topics: {', '.join(unique_topics)}. "
            summary += f"Total messages: {len(conversation_history)}"
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating conversation summary: {e}")
            return "Error generating conversation summary."
    
    def _generate_follow_up_questions(self, query: str, response: str, context_chunks: List[Dict]) -> List[str]:
        """Generate natural follow-up questions to maintain conversation flow"""
        try:
            # Enhanced follow-up generation with conversation flow
            follow_up_prompt = f"""На основе вопроса пользователя и твоего ответа, сгенерируй 3-5 естественных follow-up вопросов для продолжения диалога.

ВОПРОС ПОЛЬЗОВАТЕЛЯ: {query}
ТВОЙ ОТВЕТ: {response}

ПРАВИЛА ДЛЯ FOLLOW-UP ВОПРОСОВ:
1. Вопросы должны быть естественными и логичными продолжениями разговора
2. Используй найденные документы как основу для углубления темы
3. Предлагай связанные темы, которые могут заинтересовать пользователя
4. Задавай уточняющие вопросы для лучшего понимания потребностей
5. Предлагай практические советы и рекомендации

ГЕНЕРИРУЙ ВОПРОСЫ В СЛЕДУЮЩИХ КАТЕГОРИЯХ:
- Углубление в найденную тему
- Практические рекомендации
- Связанные темы и области
- Уточнение деталей
- Предложения для дальнейшего изучения

ФОРМАТ: Просто список вопросов, каждый с новой строки, без нумерации."""

            # Generate follow-up questions using LLM
            follow_up_messages = [
                {"role": "system", "content": "Ты - эксперт по генерации follow-up вопросов. Отвечай ТОЛЬКО на русском языке."},
                {"role": "user", "content": follow_up_prompt}
            ]
            
            follow_up_response = self.llm.invoke(follow_up_messages)
            
            # Parse the response into individual questions
            questions_text = follow_up_response.content.strip()
            questions = [q.strip() for q in questions_text.split('\n') if q.strip() and not q.startswith(('1.', '2.', '3.', '4.', '5.', '-', '•'))]
            
            # Limit to 5 questions and ensure quality
            questions = questions[:5]
            
            # Add some default questions if generation failed
            if not questions:
                questions = [
                    "Хотели бы вы узнать больше деталей по этой теме?",
                    "Есть ли у вас конкретные вопросы по практическому применению?",
                    "Какие аспекты вас интересуют больше всего?",
                    "Могу ли я помочь с чем-то еще по этой теме?"
                ]
            
            logger.info(f"🎯 Сгенерировано {len(questions)} follow-up вопросов")
            return questions
            
        except Exception as e:
            logger.error(f"❌ Ошибка при генерации follow-up вопросов: {e}")
            # Fallback questions
            return [
                "Хотели бы вы узнать больше по этой теме?",
                "Есть ли у вас дополнительные вопросы?",
                "Могу ли я помочь с чем-то еще?"
            ]

    def _analyze_question_type(self, query: str, context_chunks: List[Dict]) -> Dict[str, Any]:
        """Analyze question type and determine response strategy"""
        try:
            query_lower = query.lower()
            
            # Analyze question characteristics
            analysis = {
                'type': 'general',
                'requires_documents': False,
                'is_follow_up': False,
                'is_clarification': False,
                'is_practical': False,
                'suggested_strategy': 'hybrid'
            }
            
            # Check if it's a follow-up question
            follow_up_indicators = ['а что насчет', 'а как же', 'а если', 'а можно ли', 'а что если', 'расскажи подробнее', 'объясни детальнее']
            if any(indicator in query_lower for indicator in follow_up_indicators):
                analysis['is_follow_up'] = True
                analysis['suggested_strategy'] = 'context_aware'
            
            # Check if it's a clarification question
            clarification_indicators = ['что значит', 'как понять', 'объясни простыми словами', 'поясни', 'уточни']
            if any(indicator in query_lower for indicator in clarification_indicators):
                analysis['is_clarification'] = True
                analysis['suggested_strategy'] = 'hybrid'
            
            # Check if it's a practical question
            practical_indicators = ['как сделать', 'как приготовить', 'как организовать', 'пошагово', 'инструкция', 'рецепт']
            if any(indicator in query_lower for indicator in practical_indicators):
                analysis['is_practical'] = True
                analysis['requires_documents'] = True
                analysis['suggested_strategy'] = 'document_heavy'
            
            # Check if it requires specific document information
            if context_chunks and len(context_chunks) > 0:
                analysis['requires_documents'] = True
                if analysis['suggested_strategy'] == 'general':
                    analysis['suggested_strategy'] = 'hybrid'
            
            # Determine final strategy
            if analysis['requires_documents'] and analysis['is_practical']:
                analysis['suggested_strategy'] = 'document_heavy'
            elif analysis['is_follow_up']:
                analysis['suggested_strategy'] = 'context_aware'
            elif not analysis['requires_documents']:
                analysis['suggested_strategy'] = 'general_knowledge'
            
            logger.info(f"🔍 Анализ вопроса: {analysis}")
            return analysis
            
        except Exception as e:
            logger.error(f"❌ Ошибка при анализе типа вопроса: {e}")
            return {
                'type': 'general',
                'requires_documents': bool(context_chunks),
                'is_follow_up': False,
                'is_clarification': False,
                'is_practical': False,
                'suggested_strategy': 'hybrid'
            }


# Global instance
rag_service = RAGService()
