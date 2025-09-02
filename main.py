#!/usr/bin/env python3
"""
RAG System - Restaurant Management AI Assistant

ВРЕМЕННЫЕ ИЗМЕНЕНИЯ (для заказчиков):
- 🔓 Отключены ограничения по ролям для /chat эндпоинта
- ✅ Все роли могут обращаться ко всем разделам (restaurant_ops, procedures, standards)
- 🔒 Ограничения на загрузку документов СОХРАНЕНЫ
- 📝 Эндпоинт /documents/upload-smart по-прежнему проверяет права доступа

ПРИМЕЧАНИЕ: Это временное решение до готовности системы разделения по ролям у заказчиков
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Depends, status, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
# from fastapi.staticfiles import StaticFiles  # Убрали, не нужен
import uvicorn
from typing import List, Optional, Dict, Any
import os
import uuid
import asyncio
from datetime import datetime, timedelta
import json

from config import settings
from database.database import SessionLocal
from database.models import Document, AccessToken, Conversation, ConversationMessage
from services import (
    rag_service,
    vector_service,
    supabase_service,
    document_processor,
    auth_service,
    admin_service,
    session_context_service,
    embedding_service
)
from services.source_linker import source_linker
from services.rate_limiter import check_rate_limit_middleware
from services.auth_dependencies import get_current_token, get_admin_token
from services.cache_cleanup_router import router as cache_cleanup_router
from services.document_viewer_router import router as document_viewer_router
from schemas import (
    DocumentCreate, DocumentResponse, DocumentList, DocumentUpdate,
    ChatRequest, ChatResponse, ConversationCreate, ConversationResponse,
    AccessTokenCreate, AccessTokenResponse, TokenValidation, DocumentSearchRequest,
    DocumentSearchResult, UserRegister, UserLogin, AuthResponse
)
from sqlalchemy import text

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)





# Security moved to auth_dependencies.py

# Database
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_db_session():
    """Get a single database session (not a generator)"""
    return SessionLocal()

# Lifespan context manager
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown events"""
    # Startup
    try:
        logger.info("🚀 Запускаем RAG Систему...")
        
        # Check if running in demo mode
        if settings.demo_mode:
            logger.info("🎭 Запуск в демо-режиме - пропускаем проверки базы данных")
        else:
            # Test database connection
            db = get_db_session()
            try:
                db.execute(text("SELECT 1"))
                logger.info("✅ Подключение к базе данных успешно")
            except Exception as e:
                logger.error(f"❌ Подключение к базе данных не удалось: {e}")
                raise
            finally:
                db.close()
            
            # Test Supabase connection
            try:
                # Test by checking storage usage
                storage_info = supabase_service.check_storage_usage()
                logger.info("✅ Подключение к Supabase успешно")
            except Exception as e:
                logger.error(f"❌ Подключение к Supabase не удалось: {e}")
                raise
        
        # Test OpenAI connection
        try:
            # Simple test - just check if the key is valid format
            if not settings.openai_api_key or len(settings.openai_api_key) < 20:
                raise ValueError("Неверный формат ключа OpenAI API")
            logger.info("✅ Конфигурация OpenAI валидна")
        except Exception as e:
            logger.error(f"❌ Конфигурация OpenAI не удалась: {e}")
            raise
        
        # Mount static files - УБИРАЕМ, НЕ НУЖЕН ДЛЯ API
        # app.mount("/static", StaticFiles(directory="static"), name="static")
        
        # Запускаем сервис автоматической очистки кэша
        try:
            from services.cache_cleanup_service import cache_cleanup_service
            cache_cleanup_service.start()
            logger.info("🧹 Сервис автоматической очистки кэша запущен")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось запустить сервис очистки кэша: {e}")
        
        logger.info("🚀 RAG Система успешно запущена!")
        
    except Exception as e:
        logger.error(f"❌ Запуск не удался: {e}")
        raise
    
    yield
    
    # Shutdown
    logger.info("🔄 Выключаем RAG Систему...")
    
    # Останавливаем сервис очистки кэша
    try:
        from services.cache_cleanup_service import cache_cleanup_service
        if cache_cleanup_service.is_running:
            cache_cleanup_service.stop()
            logger.info("🧹 Сервис очистки кэша остановлен")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось остановить сервис очистки кэша: {e}")

# Main FastAPI application
app = FastAPI(
    title="RAG System API",
    description="Retrieval Augmented Generation System for Document Processing and AI Chat",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include cache cleanup router
app.include_router(cache_cleanup_router)

# Include document viewer router
app.include_router(document_viewer_router)

# ============================================================================
# AUTHENTICATION
# ============================================================================

# ============================================================================
# AUTHENTICATION ENDPOINTS (Public Access)
# ============================================================================

@app.post("/auth/register", response_model=dict)
async def register_user(
    user_data: UserRegister
):
    """Регистрация нового пользователя"""
    try:
        from services.user_auth_service import user_auth_service
        
        result = user_auth_service.register_user(
            username=user_data.username,
            email=user_data.email,
            password=user_data.password,
            subscription_type=user_data.subscription_type,
            company_name=user_data.company_name
        )
        
        if result['success']:
            return {
                "message": "Пользователь успешно зарегистрирован",
                "user_id": result['user_id'],
                "username": result['username'],
                "subscription_type": result['subscription_type']
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result['error']
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при регистрации: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера"
        )


@app.post("/auth/login", response_model=AuthResponse)
async def login_user(
    user_data: UserLogin
):
    """Аутентификация пользователя"""
    try:
        from services.user_auth_service import user_auth_service
        
        result = user_auth_service.authenticate_user(user_data.username, user_data.password)
        
        if result['success']:
            return {
                "message": "Успешная аутентификация",
                "access_token": result['access_token'],
                "refresh_token": result['refresh_token'],
                "user_info": result['user_info']
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=result['error']
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при аутентификации: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Внутренняя ошибка сервера"
        )


@app.post("/auth/refresh")
async def refresh_token(
    refresh_token: str = Form(...)
):
    """Обновление access токена"""
    try:
        from services.user_auth_service import user_auth_service
        
        result = user_auth_service.refresh_access_token(refresh_token)
        
        if result['success']:
            return {
                "message": "Токен обновлен",
                "access_token": result['access_token']
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=result['error']
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Ошибка при обновлении токена: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Ошибка при обновлении токена"
        )

@app.get("/auth/get-token", include_in_schema=False)
async def get_token_info(token: TokenValidation = Depends(get_current_token)):
    """Информация о токене и правах доступа пользователя"""
    # Import access control service
    from services.access_control_service import access_control_service
    
    # Get detailed access information
    detailed_access = access_control_service.get_detailed_access_info(token.access_level)
    access_summary = access_control_service.get_access_summary(token.access_level)
    
    return {
        "user_info": {
            "user_id": token.id,
            "access_level": token.access_level,
            "allowed_sections": token.allowed_sections
        },
        "detailed_access": detailed_access,
        "access_summary": access_summary,
        "message": "Детальная информация о ваших правах доступа",
        "note": "Используйте access_token в заголовке Authorization: Bearer <token> для доступа к API"
    }


# ============================================================================
# PUBLIC API ENDPOINTS (Client Access)
# ============================================================================

@app.post("/documents/upload-smart", response_model=DocumentResponse)
async def upload_document_smart(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    section: str = Form(...),
    token: TokenValidation = Depends(get_current_token)
):
    """Smart document upload - automatically detects access level from token"""
    try:
        # Validate token
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        # Auto-detect access level from token
        access_level = token.access_level
        
        # Import access control service
        from services.access_control_service import access_control_service
        
        # Validate access to section using detailed access control
        if not access_control_service.can_upload_to_section(token.access_level, section):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Доступ к загрузке в раздел '{section}' запрещен для вашего типа подписки '{token.access_level}'. Обратитесь к администратору для получения прав."
            )
        
        # Validate file type
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in settings.supported_formats:
            raise HTTPException(
                status_code=400,
                detail=f"Неподдерживаемый тип файла: {file_ext}. Поддерживаемые: {', '.join(settings.supported_formats)}"
            )
        
        # Validate file size
        if file.size > settings.max_file_size:
            raise HTTPException(
                status_code=400,
                detail=f"Файл слишком большой. Максимальный размер: {settings.max_file_size / (1024*1024)}MB"
            )
        
        # Generate unique filename
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        local_path = f"uploads/{unique_filename}"
        
        # Save file locally
        os.makedirs("uploads", exist_ok=True)
        with open(local_path, "wb") as f:
            content = await file.read()
            f.write(content)
        
        # Upload to Supabase
        supabase_path = f"{section}/{unique_filename}"
        public_url = supabase_service.upload_file(local_path, supabase_path)
        
        # Save document metadata to database
        db = get_db_session()
        try:
            document = Document(
                filename=unique_filename,
                original_filename=file.filename,
                file_path=supabase_path,
                file_size=file.size,
                file_type=file_ext,
                mime_type=file.content_type or "application/octet-stream",
                title=title or file.filename,
                description=description or f"Документ загружен в раздел {section}",
                section=section,
                access_level=access_level,
                is_processed=False,
                has_images=False
            )
            
            db.add(document)
            db.commit()
            db.refresh(document)
            
            # Start async document processing
            # Pass the Supabase path (file_path) instead of local_path for processing
            asyncio.create_task(
                document_processor.process_document_async(
                    document.id, document.file_path, file_ext, section, access_level
                )
            )
            
            # Clean up local file
            os.remove(local_path)
            
            return DocumentResponse(
                id=document.id,
                filename=document.filename,
                original_filename=document.original_filename,
                file_path=document.file_path,
                file_size=document.file_size,
                file_type=document.file_type,
                mime_type=document.mime_type,
                title=document.title,
                description=document.description,
                section=document.section,
                access_level=document.access_level,
                is_processed=document.is_processed,
                processing_error=getattr(document, 'processing_error', None),
                has_images=document.has_images,
                text_content=getattr(document, 'text_content', None),
                extracted_metadata=getattr(document, 'extracted_metadata', None),
                uploaded_at=document.uploaded_at.isoformat() if document.uploaded_at else None,
                processed_at=document.processed_at.isoformat() if document.processed_at else None
            )
            
        except Exception as e:
            logger.error(f"Загрузка документа не удалась: {e}")
            raise HTTPException(status_code=500, detail=str(e))
        finally:
            db.close()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Загрузка документа не удалась: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat", response_model=ChatResponse)
async def chat_with_ai(
    request: ChatRequest,
    token: TokenValidation = Depends(get_current_token)
):
    """Enhanced chat with AI based on uploaded documents using section-based search and session context"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        # ВРЕМЕННО: отключаем ограничения по ролям для /chat
        # Все роли могут обращаться ко всем разделам для чтения
        logger.info(f"🔓 ВРЕМЕННО: отключены ограничения по ролям для /chat")
        logger.info(f"👤 Пользователь: {token.access_level}")
        
        # ВРЕМЕННО: даем доступ ко всем разделам для чтения
        user_sections = ["restaurant_ops", "procedures", "standards"]
        logger.info(f"✅ ВРЕМЕННО: пользователь имеет доступ ко ВСЕМ разделам: {user_sections}")
        
        # Generate or retrieve session ID
        session_id = request.session_id or f"session_{token.id}_{uuid.uuid4()}"
        
        # Get or create conversation
        conversation = await session_context_service.get_or_create_conversation(
            session_id=session_id,
            user_id=token.id,  # Используем id из токена (который содержит user_id)
            initial_context=request.context
        )
        
        # ВРЕМЕННО: разрешаем доступ к любой секции для чтения
        if request.section:
            if request.section in user_sections:
                await session_context_service.update_conversation_section(session_id, request.section)
                logger.info(f"✅ ВРЕМЕННО: доступ к секции '{request.section}' разрешен для всех ролей")
            else:
                logger.warning(f"⚠️ Запрошена неизвестная секция: {request.section}")
                # ВРЕМЕННО: все равно разрешаем доступ
                await session_context_service.update_conversation_section(session_id, request.section)
                logger.info(f"✅ ВРЕМЕННО: доступ к секции '{request.section}' разрешен (временное решение)")
        
        # Process images if provided
        image_analysis = {}
        enhanced_message = request.message
        
        # Логируем входящие данные
        logger.info(f"📝 Входящее сообщение: {request.message}")
        logger.info(f"🖼️ Изображения в запросе: {request.images}")
        logger.info(f"🔍 Тип изображений: {type(request.images)}")
        if request.images:
            logger.info(f"🔍 Количество изображений: {len(request.images)}")
            for i, img in enumerate(request.images):
                logger.info(f"🔍 Изображение {i}: тип={img.image_type}, описание={img.description}, данные={len(img.image_data)} символов")
        
        if request.images:
            logger.info(f"🖼️ Обрабатываем {len(request.images)} изображений")
            logger.info(f"🔍 Тип изображений: {type(request.images)}")
            logger.info(f"🔍 Первое изображение: {request.images[0] if request.images else 'None'}")
            
            from services.image_processing_service import image_processing_service
            
            # Обрабатываем изображения
            logger.info(f"🔍 Начинаем обработку изображений...")
            image_analysis = image_processing_service.process_chat_images(request.images)
            logger.info(f"📊 Результат обработки изображений: {image_analysis}")
            
            # Улучшаем сообщение с информацией об изображениях
            enhanced_message = image_processing_service.enhance_chat_context(
                request.message, image_analysis
            )
            
            logger.info(f"✅ Обработано изображений: {image_analysis.get('processed_images', 0)}")
            logger.info(f"📝 Извлеченный текст: {image_analysis.get('extracted_text', [])}")
            logger.info(f"🔍 Улучшенное сообщение: {enhanced_message[:200]}...")
        else:
            logger.info("📝 Изображения не предоставлены")
        
        # Check if we should use existing context (for clarifying questions)
        # BUT only if no specific section is requested or if section matches
        use_existing_context = False
        existing_documents = []
        context_strategy = "new_search"
        
        if request.section:
            # If specific section is requested, NEVER reuse old context
            logger.info(f"🎯 Запрошена конкретная секция '{request.section}', принудительно выполняем новый поиск")
            use_existing_context = False
            
            # Clear old context for this section to ensure fresh search
            try:
                await session_context_service.clear_document_context(session_id)
                logger.info(f"🧹 Очищен старый контекст для секции '{request.section}'")
            except Exception as e:
                logger.warning(f"⚠️ Не удалось очистить контекст: {e}")
        else:
            # Check if we can reuse existing context
            use_existing_context, existing_documents, context_strategy = await session_context_service.should_use_existing_context(
                session_id, enhanced_message  # Используем улучшенное сообщение
            )
        
        search_results = []
        search_strategy = context_strategy
        
        if use_existing_context:
            if context_strategy == "context_reuse":
                logger.info(f"🔄 Используем существующий контекст для уточняющего вопроса в сессии {session_id}")
                # Convert existing documents to search result format
                for doc in existing_documents:
                    search_results.append({
                        'document_id': doc.get('document_id'),
                        'chunk_id': f"context_{doc.get('document_id')}",
                        'content': doc.get('content', ''),
                        'section': doc.get('section', ''),
                        'access_level': token.access_level,
                        'score': doc.get('score', 0.9),  # High score for context reuse
                        'metadata': {'context_reused': True, 'original_query': doc.get('query')}
                    })
            elif context_strategy == "hybrid_context":
                logger.info(f"🔄 Используем гибридный подход к контексту в сессии {session_id}")
                # Use existing context as base, but also perform a focused search
                base_context = existing_documents
                
                # Perform focused search with existing context as guidance
                # BUT respect the requested section if specified
                target_section = request.section or session_context.get('current_section')
                if request.section:
                    logger.info(f"🎯 Гибридный поиск с принудительной секцией: {target_section}")
                
                focused_results = await search_documents_internal(
                    query=request.message,
                    section=target_section,
                    access_level=token.access_level,
                    limit=6,  # Fewer results for focused search
                    score_threshold=0.6,  # Higher threshold for focused search
                    user_sections=user_sections,
                    strict_section_search=bool(request.section)  # Strict search if section specified
                )
                
                # Merge existing context with new focused results
                merged_context = await session_context_service.merge_contexts(
                    base_context, 
                    [{'document_id': r.document_id, 'content': r.content, 'section': r.section, 'score': r.score, 'query': request.message} for r in focused_results],
                    max_context_size=25
                )
                
                # Convert merged context to search result format
                for doc in merged_context:
                    search_results.append({
                        'document_id': doc.get('document_id'),
                        'chunk_id': f"hybrid_{doc.get('document_id')}",
                        'content': doc.get('content', ''),
                        'section': doc.get('section', ''),
                        'access_level': doc.get('access_level'),
                        'score': doc.get('score', 0.8),
                        'metadata': {'context_reused': True, 'hybrid_search': True, 'original_query': doc.get('query')}
                    })
        else:
            # Perform new search
            logger.info(f"🔍 Выполняем новый поиск для сессии {session_id}")
            
            # Determine search strategy based on request
            target_section = None
            logger.info(f"🔍 DEBUG: request.section = {request.section}")
            logger.info(f"🔍 DEBUG: user_sections = {user_sections}")
            logger.info(f"🔍 DEBUG: request.section in user_sections = {request.section in user_sections if request.section else 'None'}")
            
            if request.section:
                # ВРЕМЕННО: разрешаем доступ к любой секции
                target_section = request.section
                search_strategy = "section_specific"
                logger.info(f"🎯 ВРЕМЕННО: поиск по запрошенной секции: {target_section}")
            elif request.context and request.context in user_sections:
                target_section = request.context
                search_strategy = "section_specific"
                logger.info(f"🎯 Используем поиск по контексту: {target_section}")
            else:
                logger.info(f"🌐 Поиск по всем доступным секциям")
                # ВРЕМЕННО: не предупреждаем о недоступных секциях
            
            # Perform enhanced search with smart filtering
            # Если есть изображения, добавляем извлеченный текст к запросу
            search_query = enhanced_message if image_analysis.get('combined_text') else request.message
            
            # ВРЕМЕННО: упрощаем логику поиска
            logger.info(f"🔍 DEBUG: request.section = {request.section}")
            logger.info(f"🔍 DEBUG: target_section = {target_section}")
            logger.info(f"🔍 DEBUG: user_sections = {user_sections}")
            
            # Определяем стратегию поиска
            if request.section:
                # ВРЕМЕННО: используем более точный поиск для любой секции
                strict_search = False  # Всегда гибкий поиск
                score_threshold = 0.5  # Сниженный порог для лучшего баланса
                limit = 8  # Меньше результатов, но лучшего качества
                logger.info(f"🎯 ВРЕМЕННО: поиск по секции '{request.section}' (сбалансированный режим, threshold={score_threshold})")
            else:
                strict_search = False  # Всегда используем гибкий поиск
                score_threshold = 0.6  # Сниженный порог для общего поиска
                limit = 6  # Меньше результатов, но лучшего качества
                logger.info(f"🌐 Общий поиск: используем score_threshold={score_threshold}, limit={limit}")
            
            search_results = await search_documents_internal(
                query=search_query,
                section=target_section,
                access_level=token.access_level,
                limit=limit,
                score_threshold=score_threshold,
                user_sections=user_sections,
                strict_section_search=strict_search
            )
        
        if not search_results:
            # Вместо возврата пустого ответа, используем гибридный режим
            logger.info(f"🔍 Документы не найдены, переключаемся на гибридный режим")
            
            # Add user message to conversation
            await session_context_service.add_message_to_conversation(
                conversation_id=conversation['id'],  # Use dictionary access
                role="user",
                content=request.message
            )
            
            # Генерируем ответ используя общие знания (гибридный режим)
            try:
                logger.info(f"🤖 Генерируем ответ в гибридном режиме (без документов)")
                ai_response = rag_service.generate_response(
                    query=request.message,
                    context_chunks=[],  # Пустой контекст документов
                    conversation_history=[],
                    session_context={'document_context': [], 'messages': []}
                )
                
                return ChatResponse(
                    response=ai_response['response'],
                    session_id=session_id,
                    sources=[],
                    context_chunks_used=0,
                    timestamp=datetime.now().isoformat(),
                    follow_up_questions=ai_response.get('follow_up_questions', []),
                    response_strategy=ai_response.get('response_strategy', 'general_knowledge'),
                    question_analysis=ai_response.get('question_analysis', {})
                )
                
            except Exception as e:
                logger.error(f"❌ Гибридный режим не удался: {e}")
                
                # Fallback к простому ответу
                # ВРЕМЕННО: все секции доступны, упрощаем сообщения
                if request.section:
                    response_message = f"В секции '{request.section}' не найдено релевантной информации для ответа на ваш вопрос. Пожалуйста, попробуйте перефразировать вопрос или обратитесь к другой секции."
                else:
                    response_message = "Я не смог найти релевантную информацию в ваших документах для ответа на этот вопрос. Пожалуйста, попробуйте перефразировать свой вопрос или загрузите более релевантные документы."
                
                return ChatResponse(
                    response=response_message,
                    session_id=session_id,
                    sources=[],
                    context_chunks_used=0,
                    timestamp=datetime.now().isoformat(),
                    follow_up_questions=[]
                )
        
        # Get session context for enhanced RAG
        session_context = await session_context_service.get_conversation_context(session_id)
        logger.info(f"📋 Получен контекст сессии: {len(session_context.get('messages', []))} сообщений, {len(session_context.get('document_context', []))} документов")
        
        # Debug: Log session context structure
        try:
            logger.info(f"🔍 Структура контекста сессии: {json.dumps(session_context, default=str)[:500]}...")
        except Exception as e:
            logger.warning(f"⚠️ Не удалось сериализовать контекст сессии: {e}")
        
        # Build context from search results
        context_chunks = []
        for result in search_results:
            # Handle both SearchResult objects and dict objects
            if hasattr(result, 'content'):
                # SearchResult object
                context_chunks.append({
                    'content': result.content,
                    'document_id': result.document_id,
                    'chunk_id': result.chunk_id,
                    'section': result.section,
                    'access_level': result.access_level,
                    'score': result.score,
                    'metadata': result.metadata or {}
                })
            else:
                # Dict object (from context reuse)
                context_chunks.append({
                    'content': result.get('content', ''),
                    'document_id': result.get('document_id'),
                    'chunk_id': result.get('chunk_id'),
                    'section': result.get('section'),
                    'access_level': result.get('access_level'),
                    'score': result.get('score', 0.0),
                    'metadata': result.get('metadata', {})
                })
        
        logger.info(f"🔍 Построены {len(context_chunks)} частей контекста для RAG (стратегия: {search_strategy})")
        
        # Generate AI response using enhanced RAG with session context
        try:
            logger.info(f"🤖 Начинаем генерацию ответа AI...")
            ai_response = rag_service.generate_response(
                query=request.message,
                context_chunks=context_chunks,
                conversation_history=session_context.get('messages', []),
                session_context=session_context
            )
            logger.info(f"✅ Ответ AI сгенерирован успешно")
            
        except Exception as e:
            logger.error(f"❌ Генерация ответа AI не удалась: {e}")
            logger.error(f"Ключи контекста сессии: {list(session_context.keys()) if session_context else 'None'}")
            logger.error(f"Тип документа контекста: {type(session_context.get('document_context')) if session_context else 'None'}")
            if session_context and session_context.get('document_context'):
                logger.error(f"Длина документа контекста: {len(session_context['document_context'])}")
                if session_context['document_context']:
                    logger.error(f"Первый тип документа: {type(session_context['document_context'][0])}")
            raise HTTPException(status_code=500, detail=f"Не удалось сгенерировать ответ AI: {str(e)}")
        
        # Add user message to conversation
        await session_context_service.add_message_to_conversation(
            conversation_id=conversation['id'],  # Use dictionary access
            role="user",
            content=request.message,
            search_context={
                'query': request.message,
                'results': context_chunks,
                'sections': [result.section if hasattr(result, 'section') else result.get('section') for result in search_results],
                'relevance_score': sum(result.score if hasattr(result, 'score') else result.get('score', 0) for result in search_results) / len(search_results) if search_results else 0,
                'source_chunks': [result.chunk_id if hasattr(result, 'chunk_id') else result.get('chunk_id') for result in search_results],
                'source_documents': [result.document_id if hasattr(result, 'document_id') else result.get('document_id') for result in search_results]
            }
        )
        
        # Add assistant response to conversation
        await session_context_service.add_message_to_conversation(
            conversation_id=conversation['id'],  # Use dictionary access
            role="assistant",
            content=ai_response['response']
        )
        
        # Extract source information
        sources = []
        for result in search_results:
            # Validate result before processing
            if not result:
                logger.warning(f"⚠️ Пропускаем пустой результат")
                continue
                
            # Handle both SearchResult objects and dict objects
            if hasattr(result, 'content'):
                # SearchResult object
                if not hasattr(result, 'document_id') or not result.document_id:
                    logger.warning(f"⚠️ Пропускаем результат без document_id: {result}")
                    continue
                    
                source_info = await get_document_info(result.document_id)
                document_name = get_better_document_name(source_info, result.document_id)
                
                # Добавляем логирование для отладки
                logger.info(f"🔍 Создаем источник для документа {result.document_id}:")
                logger.info(f"   - source_info: {source_info}")
                logger.info(f"   - document_name: {document_name}")
                
                # Проверяем, что document_name не равен "string"
                if document_name == "string":
                    logger.error(f"❌ document_name равен 'string' для документа {result.document_id}")
                    # Используем fallback
                    document_name = f"Документ {result.document_id}"
                
                # Дополнительная проверка на пустые значения
                if not document_name or document_name.strip() == "":
                    logger.error(f"❌ document_name пустой для документа {result.document_id}")
                    document_name = f"Документ {result.document_id}"
                
                logger.info(f"✅ Финальный document_name для документа {result.document_id}: '{document_name}'")
                
                sources.append({
                    "document_id": result.document_id,
                    "chunk_id": result.chunk_id,
                    "section": result.section,
                    "access_level": result.access_level,
                    "document_title": document_name,
                    "document_name": document_name,
                    "chunk_type": result.chunk_type,
                    "page_number": result.page_number,
                    "section_name": result.section_name,
                    "metadata": result.metadata or {},
                    "context_reused": result.metadata.get('context_reused', False) if result.metadata else False
                })
            else:
                # Dict object (from context reuse)
                doc_id = result.get('document_id')
                if not doc_id:
                    logger.warning(f"⚠️ Пропускаем результат без document_id: {result}")
                    continue
                    
                source_info = await get_document_info(doc_id)
                document_name = get_better_document_name(source_info, doc_id)
                
                # Добавляем логирование для отладки
                logger.info(f"🔍 Создаем источник для документа {doc_id} (context reuse):")
                logger.info(f"   - source_info: {source_info}")
                logger.info(f"   - document_name: {document_name}")
                
                # Проверяем, что document_name не равен "string"
                if document_name == "string":
                    logger.error(f"❌ document_name равен 'string' для документа {doc_id} (context reuse)")
                    # Используем fallback
                    document_name = f"Документ {doc_id}"
                
                # Дополнительная проверка на пустые значения
                if not document_name or document_name.strip() == "":
                    logger.error(f"❌ document_name пустой для документа {doc_id} (context reuse)")
                    document_name = f"Документ {doc_id}"
                
                logger.info(f"✅ Финальный document_name для документа {doc_id} (context reuse): '{document_name}'")
                
                sources.append({
                    "document_id": doc_id,
                    "chunk_id": result.get('chunk_id'),
                    "section": result.get('section'),
                    "access_level": result.get('access_level'),
                    "document_title": document_name,
                    "document_name": document_name,
                    "chunk_type": "context_reuse",
                    "page_number": None,
                    "section_name": result.get('section'),
                    "metadata": result.get('metadata', {}),
                    "context_reused": result.get('metadata', {}).get('context_reused', False)
                })
        
        # Дедупликация источников по document_id и chunk_id
        unique_sources = []
        seen_combinations = set()
        
        # Сортируем источники по document_id для лучшей группировки
        sorted_sources = sorted(sources, key=lambda x: (x.get('document_id', 0), x.get('chunk_id', 0)))
        
        for source in sorted_sources:
            # Создаем уникальный ключ для комбинации document_id и chunk_id
            unique_key = (source.get('document_id'), source.get('chunk_id'))
            
            if unique_key not in seen_combinations:
                seen_combinations.add(unique_key)
                unique_sources.append(source)
                logger.info(f"✅ Добавляем уникальный источник: document_id={source.get('document_id')}, chunk_id={source.get('chunk_id')}")
            else:
                logger.info(f"🔄 Пропускаем дубликат: document_id={source.get('document_id')}, chunk_id={source.get('chunk_id')}")
        
        logger.info(f"📊 Источники после дедупликации: {len(unique_sources)} из {len(sources)}")
        
        # Дополнительная группировка по document_id для лучшего отображения
        document_groups = {}
        for source in unique_sources:
            doc_id = source.get('document_id')
            if doc_id not in document_groups:
                document_groups[doc_id] = []
            document_groups[doc_id].append(source)
        
        logger.info(f"📚 Сгруппировано по {len(document_groups)} документам: {list(document_groups.keys())}")
        for doc_id, doc_sources in document_groups.items():
            logger.info(f"   📄 Документ {doc_id}: {len(doc_sources)} чанков")
        
        # Создаем компактные источники - по одному на документ
        compact_sources = []
        for doc_id, doc_sources in document_groups.items():
            if doc_sources:
                # Берем первый источник как представитель документа
                representative_source = doc_sources[0].copy()
                
                # Добавляем информацию о количестве чанков
                representative_source['total_chunks'] = len(doc_sources)
                representative_source['chunk_ids'] = [s.get('chunk_id') for s in doc_sources]
                
                # Убеждаемся, что у нас есть mime_type и file_type для создания ссылок
                if 'mime_type' not in representative_source or 'file_type' not in representative_source:
                    logger.warning(f"⚠️ В источнике отсутствуют mime_type или file_type: {representative_source}")
                    # Попробуем получить из базы данных
                    try:
                        doc_info = await get_document_info(doc_id)
                        if doc_info:
                            representative_source['mime_type'] = doc_info.get('mime_type', '')
                            representative_source['file_type'] = doc_info.get('file_type', '')
                            logger.info(f"✅ Добавлены mime_type и file_type для документа {doc_id}: {representative_source.get('mime_type')}, {representative_source.get('file_type')}")
                    except Exception as e:
                        logger.error(f"❌ Не удалось получить информацию о документе {doc_id}: {e}")
                
                compact_sources.append(representative_source)
                logger.info(f"📄 Создан компактный источник для документа {doc_id}: {len(doc_sources)} чанков")
        
        logger.info(f"📊 Компактные источники: {len(compact_sources)} из {len(unique_sources)}")
        
        # 🔍 УМНАЯ ФИЛЬТРАЦИЯ ИСТОЧНИКОВ
        # Показываем только те документы, которые действительно содержат информацию для ответа
        filtered_sources = await _filter_relevant_sources(compact_sources, ai_response['response'], context_chunks)
        logger.info(f"🎯 Отфильтровано релевантных источников: {len(filtered_sources)} из {len(compact_sources)}")
        
        # Форматируем ответ с отфильтрованными источниками через source_linker
        formatted_response = source_linker.format_response_with_sources(ai_response['response'], filtered_sources)
        
        return ChatResponse(
            response=formatted_response,  # Используем отформатированный ответ
            session_id=session_id,
            sources=filtered_sources,  # Используем отфильтрованные источники
            context_chunks_used=len(context_chunks),
            timestamp=ai_response['timestamp'],
            follow_up_questions=ai_response.get('follow_up_questions', []),
            image_analysis=image_analysis if image_analysis else None
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Чат не удался: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search")
async def search_documents(
    request: DocumentSearchRequest,
    token: TokenValidation = Depends(get_current_token)
):
    """Search through uploaded documents"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        # Import access control service
        from services.access_control_service import access_control_service
        
        # Get user's allowed sections using detailed access control
        user_sections = access_control_service.get_user_sections(token.access_level)
        
        # Perform search with optional strict section filtering
        strict_search = request.strict_section_search or bool(request.section)  # Use explicit flag or infer from section
        search_results = await search_documents_internal(
            query=request.query,
            section=request.section,
            access_level=request.access_level or token.access_level,
            limit=request.limit,
            score_threshold=request.score_threshold,
            user_sections=user_sections,
            strict_section_search=strict_search
        )
        
        # Format results
        formatted_results = []
        for result in search_results:
            # Validate result before processing
            if not result or not hasattr(result, 'document_id') or not result.document_id:
                logger.warning(f"⚠️ Пропускаем некорректный результат: {result}")
                continue
                
            source_info = await get_document_info(result.document_id)
            formatted_results.append({
                "document_id": result.document_id,
                "chunk_id": result.chunk_id,
                "content": result.content,
                "score": result.score,
                "section": result.section,
                "access_level": result.access_level,
                "document_title": source_info.get("title", f"Документ {result.document_id}") if source_info else f"Документ {result.document_id}",
                "document_name": source_info.get("title", f"Документ {result.document_id}") if source_info else f"Документ {result.document_id}",
                "chunk_type": result.chunk_type,
                "page_number": result.page_number,
                "section_name": result.section_name,
                "metadata": result.metadata
            })
        
        return {
            "query": request.query,
            "results": formatted_results,
            "total_results": len(formatted_results),
            "search_parameters": {
                "section": request.section,
                "access_level": request.access_level or token.access_level,
                "limit": request.limit,
                "score_threshold": request.score_threshold
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Поиск не удался: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/search/section")
async def search_documents_by_section_endpoint(
    request: DocumentSearchRequest,
    token: TokenValidation = Depends(get_current_token)
):
    """Search through documents in a specific section with enhanced precision"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        if not request.section:
                raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Параметр раздела обязателен для поиска по разделу"
                )
            
        # Import access control service
        from services.access_control_service import access_control_service
        
        # Check if user has access to this section using detailed access control
        if not access_control_service.check_section_access(token.access_level, request.section, "read_only"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Доступ к разделу '{request.section}' запрещен для вашего типа подписки '{token.access_level}'"
            )
        
        # Perform section-specific search with strict section filtering
        search_results = await search_documents_internal(
            query=request.query,
            section=request.section,
            access_level=request.access_level or token.access_level,
            limit=request.limit,
            score_threshold=request.score_threshold or 0.5,
            user_sections=[request.section],  # Only search in the specified section
            strict_section_search=True  # Enable strict section search
        )
        
        # Format results
        formatted_results = []
        for result in search_results:
            # Validate result before processing
            if not result or not hasattr(result, 'document_id') or not result.document_id:
                logger.warning(f"⚠️ Пропускаем некорректный результат: {result}")
                continue
                
            source_info = await get_document_info(result.document_id)
            formatted_results.append({
                "document_id": result.document_id,
                "chunk_id": result.chunk_id,
                "content": result.content,
                "score": result.score,
                "section": result.section,
                "access_level": result.access_level,
                "document_title": source_info.get("title", f"Документ {result.document_id}") if source_info else f"Документ {result.document_id}",
                "document_name": source_info.get("title", f"Документ {result.document_id}") if source_info else f"Документ {result.document_id}",
                "chunk_type": result.chunk_type,
                "page_number": result.page_number,
                "section_name": result.section_name,
                "metadata": result.metadata
            })
        
        return {
            "query": request.query,
            "target_section": request.section,
            "results": formatted_results,
            "total_results": len(formatted_results),
            "search_parameters": {
                "section": request.section,
                "access_level": request.access_level or token.access_level,
                "limit": request.limit,
                "score_threshold": request.score_threshold or 0.5,
                "search_type": "section_specific"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Поиск по разделу не удался: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sessions/{session_id}/context")
async def get_session_context(
    session_id: str,
    token: TokenValidation = Depends(get_current_token)
):
    """Get the context and history of a specific session"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен доступа"
            )
        
        # Get session context
        context = await session_context_service.get_conversation_context(session_id)
        
        if not context.get('conversation_id'):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Сессия не найдена"
            )
        
        return {
            "session_id": session_id,
            "context": context
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось получить контекст сессии: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    token: TokenValidation = Depends(get_current_token)
):
    """Delete a specific session and its context"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен доступа"
            )
        
        # Get conversation
        db = get_db_session()
        try:
            conversation = db.query(Conversation).filter(
                Conversation.session_id == session_id
            ).first()
            
            if not conversation:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Сессия не найдена"
                )
            
            # Delete conversation (cascade will delete messages)
            db.delete(conversation)
            db.commit()
            
            logger.info(f"🗑️ Удалена сессия: {session_id}")
            return {"message": f"Сессия {session_id} удалена успешно"}
            
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось удалить сессию: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions")
async def list_user_sessions(
    token: TokenValidation = Depends(get_current_token)
):
    """List all sessions for the current user"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен доступа"
            )
        
        # Get user's conversations
        db = get_db_session()
        try:
            conversations = db.query(Conversation).filter(
                Conversation.access_token_id == token.id
            ).order_by(Conversation.last_activity.desc()).all()
            
            sessions = []
            for conv in conversations:
                # Get message count
                message_count = db.query(ConversationMessage).filter(
                    ConversationMessage.conversation_id == conv.id
                ).count()
                
                sessions.append({
                    "session_id": conv.session_id,
                    "title": conv.title,
                    "current_section": conv.current_section,
                    "message_count": message_count,
                    "created_at": conv.created_at.isoformat(),
                    "last_activity": conv.last_activity.isoformat()
                })
            
            return {"sessions": sessions}
            
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось получить список сессий: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# INTERNAL/ADMIN ENDPOINTS (Hidden from Public Docs)
# ============================================================================

@app.get("/", include_in_schema=False)
async def root():
    """Root endpoint - API information"""
    return {
        "message": "🍽️ Culinary RAG AI API",
        "version": "1.0.0",
        "description": "API для работы с кулинарными документами и AI-чатом",
        "docs": "/docs",
        "how_to_use": "Используйте /docs для тестирования API. Получите токен через /auth/register или /auth/login"
    }



@app.get("/health", include_in_schema=False)
async def health_check():
    """Health check endpoint - hidden from public docs"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/documents/upload-options", include_in_schema=False)
async def get_upload_options(token: TokenValidation = Depends(get_current_token)):
    """Get upload options based on the user's token - hidden from public docs"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        return {
            "access_level": token.access_level,
            "allowed_sections": token.allowed_sections,
            "supported_formats": settings.supported_formats,
            "max_file_size_mb": settings.max_file_size / (1024*1024),
            "message": f"Ваш токен разрешает доступ к {token.access_level} с разделами: {', '.join(token.allowed_sections)}"
        }
        
    except Exception as e:
        logger.error(f"Не удалось получить параметры загрузки: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/documents/{document_id}/status", include_in_schema=False)
async def get_document_status(
    document_id: int,
    token: TokenValidation = Depends(get_current_token)
):
    """Get document processing status - hidden from public docs"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        # Get document status
        status_info = await document_processor.get_processing_status(document_id)
        
        if 'error' in status_info:
            raise HTTPException(status_code=404, detail=status_info['error'])
        
        return status_info
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось получить статус документа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/documents/{document_id}/reprocess", include_in_schema=False)
async def reprocess_document(
    document_id: int,
    token: TokenValidation = Depends(get_current_token)
):
    """Reprocess a document that failed previously - hidden from public docs"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        # Check if user has access to this document
        db = get_db_session()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise HTTPException(status_code=404, detail="Документ не найден")
            
            # Import access control service
            from services.access_control_service import access_control_service
            
            # Check access control using detailed access control
            if not access_control_service.check_section_access(token.access_level, document.section, "read_only"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Доступ к документу в разделе '{document.section}' запрещен для вашего типа подписки '{token.access_level}'"
                )
                
        finally:
            db.close()
        
        # Start reprocessing
        result = await document_processor.reprocess_document(document_id)
        
        if result['success']:
            return {"message": f"Переобработка документа {document_id} запущена", "result": result}
        else:
            raise HTTPException(status_code=500, detail=f"Переобработка не удалась: {result.get('error', 'Неизвестная ошибка')}")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось переобработать документ {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/clear-all")
async def clear_all_documents(
    token: TokenValidation = Depends(get_current_token)
):
    """Clear all documents for the current user (admin only)"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        # Check if user is admin or has special permissions
        if token.access_level not in ['admin', 'restaurant_management']:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для удаления всех документов"
            )
        
        # Only proceed if user has proper permissions
        db = get_db_session()
        try:
            # Get all documents
            documents = db.query(Document).all()
            
            total_documents = len(documents) if documents else 0
            deleted_count = 0
            
            # Удаляем документы из БД, если они есть
            if documents:
                for document in documents:
                    try:
                        # Delete document completely
                        result = await document_processor.delete_document_completely(document.id)
                        if result['success']:
                            deleted_count += 1
                        else:
                            logger.warning(f"Не удалось удалить документ {document.id}: {result.get('error')}")
                    except Exception as e:
                        logger.error(f"Ошибка при удалении документа {document.id}: {e}")
                
                logger.info(f"🗑️ Администратор {token.id} удалил {deleted_count}/{total_documents} документов")
            else:
                logger.info("ℹ️ Документов в БД не найдено, переходим к очистке Storage")
            
            # Дополнительная очистка: удаляем все файлы из Storage напрямую
            try:
                logger.info("🧹 Дополнительная очистка Storage...")
                from services.supabase_service import supabase_service
                
                # Очищаем все основные разделы
                sections_to_clean = ["procedures", "restaurant_ops", "standards", "recipes", "ingredients", "debug"]
                
                for section in sections_to_clean:
                    try:
                        section_files = supabase_service.list_files(section)
                        if section_files:
                            logger.info(f"🗑️ Найдено {len(section_files)} файлов в {section} для дополнительной очистки")
                            
                            for file_info in section_files:
                                file_name = file_info.get('name', '')
                                if file_name and file_name != '.emptyFolderPlaceholder':
                                    try:
                                        file_path = f"{section}/{file_name}"
                                        if supabase_service.delete_file(file_path):
                                            logger.info(f"✅ Дополнительно удален файл: {file_path}")
                                        else:
                                            logger.warning(f"⚠️ Не удалось дополнительно удалить: {file_path}")
                                    except Exception as e:
                                        logger.error(f"❌ Ошибка при дополнительном удалении {file_name}: {e}")
                        else:
                            logger.info(f"ℹ️ Раздел {section} пуст")
                            
                    except Exception as e:
                        logger.error(f"❌ Ошибка при очистке раздела {section}: {e}")
                        
            except Exception as e:
                logger.error(f"❌ Ошибка при дополнительной очистке Storage: {e}")
            
            return {
                "message": f"Удалено {deleted_count} из {total_documents} документов" if documents else "Storage очищен",
                "total_documents": total_documents,
                "deleted_documents": deleted_count
            }
            
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось удалить все документы: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/documents/{document_id}")
async def delete_document(
    document_id: int,
    token: TokenValidation = Depends(get_current_token)
):
    """Delete a document completely - removes from storage, database, and vector store"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        # Check if user has access to this document
        db = get_db_session()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise HTTPException(status_code=404, detail="Документ не найден")
            
            # Import access control service
            from services.access_control_service import access_control_service
            
            # Check access control using detailed access control
            if not access_control_service.can_delete_from_section(token.access_level, document.section):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Доступ к удалению документов в разделе '{document.section}' запрещен для вашего типа подписки '{token.access_level}'"
                )
                
            # Store document info for deletion
            document_info = {
                'id': document.id,
                'filename': document.filename,
                'original_filename': document.original_filename,
                'section': document.section
            }
                
        finally:
            db.close()
        
        # Delete document completely
        result = await document_processor.delete_document_completely(document_id)
        
        if result['success']:
            logger.info(f"🗑️ Документ {document_id} полностью удален пользователем {token.id}")
            return {
                "message": f"Документ '{document_info['original_filename']}' удален успешно",
                "deleted_document": document_info
            }
        else:
            raise HTTPException(
                status_code=500, 
                detail=f"Удаление не удалось: {result.get('error', 'Неизвестная ошибка')}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось удалить документ {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/conversations/clear-all")
async def clear_all_conversations(
    token: TokenValidation = Depends(get_current_token)
):
    """Clear all conversations and sessions for the current user"""
    try:
        if not token.is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Неверный токен"
            )
        
        db = get_db_session()
        try:
            # Get all conversations for this user
            conversations = db.query(Conversation).filter(Conversation.user_id == token.id).all()
            
            if not conversations:
                return {"message": "У вас нет активных чатов для удаления"}
            
            total_conversations = len(conversations)
            total_messages = 0
            
            for conversation in conversations:
                # Delete all messages in this conversation
                messages_deleted = db.query(ConversationMessage).filter(
                    ConversationMessage.conversation_id == conversation.id
                ).delete()
                total_messages += messages_deleted
                
                # Delete the conversation
                db.delete(conversation)
            
            db.commit()
            
            logger.info(f"🗑️ Пользователь {token.id} удалил {total_conversations} чатов и {total_messages} сообщений")
            
            return {
                "message": f"Удалено {total_conversations} чатов и {total_messages} сообщений",
                "deleted_conversations": total_conversations,
                "deleted_messages": total_messages
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Не удалось удалить чаты: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# ADMIN ENDPOINTS (Completely Hidden from Public)
# ============================================================================

# Admin token validation moved to auth_dependencies.py

@app.post("/admin/tokens", response_model=AccessTokenResponse, include_in_schema=False)
async def create_access_token(
    request: AccessTokenCreate,
    admin_token: str = Depends(get_admin_token)
):
    """Create access token - admin only, hidden from public docs"""
    try:
        db = get_db_session()
        try:
            # Generate token
            actual_token, token_hash = admin_service._generate_token_hash()
            
            # Create access token
            access_token = AccessToken(
                token_hash=token_hash,
                name=request.name,
                description=request.description,
                access_level=request.access_level,
                allowed_sections=request.allowed_sections,
                rate_limit_per_hour=request.rate_limit_per_hour,
                expires_at=datetime.fromisoformat(request.expires_at) if request.expires_at else None
            )
            
            db.add(access_token)
            db.commit()
            db.refresh(access_token)
            
            return AccessTokenResponse(
                id=access_token.id,
                token_hash=actual_token,  # Return the actual token, not the hash
                name=access_token.name,
                description=access_token.description,
                access_level=access_token.access_level,
                allowed_sections=access_token.allowed_sections,
                is_active=access_token.is_active,
                rate_limit_per_hour=access_token.rate_limit_per_hour,
                current_usage=access_token.current_usage,
                created_at=access_token.created_at.isoformat() if access_token.created_at else None,
                expires_at=access_token.expires_at.isoformat() if access_token.expires_at else None
            )
            
        finally:
            db.close()
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось создать токен доступа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/tokens", response_model=List[AccessTokenResponse], include_in_schema=False)
async def list_access_tokens(admin_token: str = Depends(get_admin_token)):
    """List access tokens - admin only, hidden from public docs"""
    try:
        db = get_db_session()
        try:
            tokens = db.query(AccessToken).all()
            return [
                AccessTokenResponse(
                id=token.id,
                    token_hash=token.token_hash,
                name=token.name,
                description=token.description,
                access_level=token.access_level,
                allowed_sections=token.allowed_sections,
                is_active=token.is_active,
                rate_limit_per_hour=token.rate_limit_per_hour,
                current_usage=token.current_usage,
                    created_at=token.created_at.isoformat() if token.created_at else None,
                    expires_at=token.expires_at.isoformat() if token.expires_at else None
                )
                for token in tokens
            ]
        finally:
            db.close()
    except Exception as e:
        logger.error(f"Не удалось получить список токенов доступа: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/admin/analytics", include_in_schema=False)
async def get_admin_analytics(admin_token: str = Depends(get_admin_token)):
    """Get system analytics (admin only)"""
    try:
        # Get basic statistics
        db = get_db_session()
        try:
            total_documents = db.query(Document).count()
            processed_documents = db.query(Document).filter(Document.is_processed == True).count()
            error_documents = db.query(Document).filter(Document.processing_error.isnot(None)).count()
            
            # Get recent uploads
            recent_documents = db.query(Document).order_by(Document.uploaded_at.desc()).limit(5).all()
            
            analytics = {
                "total_documents": total_documents,
                "processed_documents": processed_documents,
                "error_documents": error_documents,
                "processing_success_rate": (processed_documents / total_documents * 100) if total_documents > 0 else 0,
                "recent_documents": [
                    {
                        "id": doc.id,
                        "title": doc.title,
                        "section": doc.section,
                        "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
                        "is_processed": doc.is_processed,
                        "error": doc.processing_error
                    }
                    for doc in recent_documents
                ]
            }
            
            return analytics
            
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"Не удалось получить аналитику: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/admin/documents/{document_id}/reprocess", include_in_schema=False)
async def reprocess_document_admin(
    document_id: int,
    admin_token: str = Depends(get_admin_token)
):
    """Reprocess a document (admin only)"""
    try:
        # Get document info
        db = get_db_session()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if not document:
                raise HTTPException(status_code=404, detail="Документ не найден")
        finally:
            db.close()
        
        # Reprocess document
        result = await document_processor.reprocess_document(document_id)
        
        if result['success']:
            return {"message": f"Документ {document_id} переобработан успешно", "result": result}
        else:
            raise HTTPException(status_code=500, detail=f"Переобработка не удалась: {result.get('error', 'Неизвестная ошибка')}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Не удалось переобработать документ {document_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# INTERNAL HELPER FUNCTIONS
# ============================================================================

async def search_documents_internal(
    query: str,
    section: Optional[str] = None,
    access_level: Optional[str] = None,
    limit: int = 10,
    score_threshold: float = 0.7,
    user_sections: Optional[List[str]] = None,
    strict_section_search: bool = False
) -> List[DocumentSearchResult]:
    """Enhanced internal search function with section-based logic and intelligent fallback"""
    try:
        logger.info(f"🔍 Ищем: '{query}' в разделе: {section}, уровень доступа: {access_level}")
        logger.info(f"🔒 Строгий поиск: {strict_section_search}")
        logger.info(f"🎯 Пользовательские секции: {user_sections}")
        
        # Step 1: Section-specific search (if section is specified and user has access)
        section_results = []
        if section:
            logger.info(f"🎯 Запрошена секция: {section}")
            logger.info(f"🎯 Доступные секции пользователя: {user_sections}")
            
            if section in (user_sections or []):
                logger.info(f"✅ Пользователь имеет доступ к секции {section}, выполняем поиск")
                logger.info(f"🔒 Строгий поиск: {strict_section_search}")
                section_results = await _perform_section_search(
                    query=query,
                    target_section=section,
                    access_level=access_level,
                    limit=limit,
                    score_threshold=score_threshold
                )
                logger.info(f"🔍 Поиск по секции {section} вернул {len(section_results)} результатов")
            else:
                logger.warning(f"❌ Пользователь НЕ имеет доступа к секции {section}")
                if strict_section_search:
                    logger.info(f"🔒 Строгий поиск: возвращаем пустой результат для недоступной секции {section}")
                    return []
                else:
                    logger.info(f"🔄 Переключаемся на поиск по всем доступным разделам")
                    section = None  # Reset section to trigger fallback search
                    section_results = []
        
        # Check if the specified section is empty or has no relevant results
        if section and not section_results:
            logger.warning(f"⚠️ Раздел '{section}' пуст или не содержит релевантных результатов")
            if strict_section_search:
                logger.info(f"🔒 Строгий поиск: возвращаем пустой результат для пустого раздела '{section}'")
                return []
            else:
                logger.info(f"🔄 Переключаемся на поиск по всем доступным разделам")
                section = None  # Reset section to trigger fallback search
        elif section and section_results:
            # If strict section search is enabled, return only section results
            if strict_section_search:
                logger.info(f"🔒 Строгий поиск по разделу: возвращаем только результаты из {section}")
                return section_results[:limit]
            
            # If we found good results in the specified section, return them
            if any(result.score > score_threshold * 0.8 for result in section_results):
                logger.info(f"✅ Найдено {len(section_results)} хороших результатов в разделе {section}")
                return section_results[:limit]
            
            logger.info(f"⚠️ Поиск по конкретному разделу вернул {len(section_results)} результатов, пытаемся альтернативный подход")
        
        # Step 2: Fallback search across all user's allowed sections (only if not strict)
        if not strict_section_search and user_sections:
            logger.info(f"🌐 Выполняем альтернативный поиск по всем разрешенным разделам: {user_sections}")
            fallback_results = await _perform_fallback_search(
                query=query,
                access_level=access_level,
                limit=limit * 2,  # Get more results for fallback
                score_threshold=score_threshold * 0.6,  # Lower threshold for fallback
                user_sections=user_sections
            )
        else:
            fallback_results = []
            if strict_section_search:
                logger.info(f"🔒 Строгий поиск: пропускаем fallback поиск по всем секциям")
                # Если строгий поиск и секция недоступна, возвращаем пустой результат
                if section and section not in (user_sections or []):
                    logger.warning(f"🔒 Строгий поиск: секция '{section}' недоступна для пользователя")
                    return []
        
        # Step 3: Combine and rank results
        all_results = []
        if section_results:
            all_results.extend(section_results)
        
        # Only add fallback results if not strict section search
        if not strict_section_search:
            all_results.extend(fallback_results)
        else:
            logger.info(f"🔒 Строгий поиск: используем только результаты из указанной секции")
        
        # Remove duplicates and sort by score
        unique_results = {}
        for result in all_results:
            key = (result.document_id, result.chunk_id)
            if key not in unique_results or result.score > unique_results[key].score:
                unique_results[key] = result
        
        # Sort by score and return top results
        final_results = sorted(unique_results.values(), key=lambda x: x.score, reverse=True)
        logger.info(f"🎉 Финальный поиск вернул {len(final_results)} уникальных результатов")
        
        return final_results[:limit]
        
    except Exception as e:
        logger.error(f"❌ Улучшенный поиск не удался: {e}")
        return []

async def _perform_section_search(
    query: str,
    target_section: str,
    access_level: Optional[str] = None,
    limit: int = 10,
    score_threshold: float = 0.7
) -> List[DocumentSearchResult]:
    """Perform focused search within a specific section"""
    try:
        logger.info(f"🎯 Поиск по конкретному разделу в '{target_section}' для запроса: '{query}'")
        
        # Get embeddings for the query
        query_embedding = await embedding_service.get_embeddings_async(query)
        
        # Build strict filters for section-specific search
        filters = {
            'section': target_section
        }
        if access_level:
            filters['access_level'] = access_level
        
        # Use higher score threshold for section-specific search to ensure quality
        adjusted_score_threshold = max(score_threshold, 0.6)
        
        # Search in vector database with section-specific focus
        raw_results = vector_service.search_similar(
            query_embedding=query_embedding,
            limit=limit * 2,  # Get more results initially for better filtering
            score_threshold=adjusted_score_threshold,
            filters=filters
        )
        
        # Convert and filter results
        search_results = []
        for result in raw_results:
            search_result = DocumentSearchResult(
                document_id=result.get('document_id'),
                chunk_id=result.get('chunk_id'),
                content=result.get('content', ''),
                score=result.get('score', 0.0),
                section=result.get('section', ''),
                access_level=result.get('access_level', ''),
                chunk_type=result.get('chunk_type'),
                page_number=result.get('page_number'),
                section_name=result.get('section_name'),
                metadata=result.get('metadata', {})
            )
            search_results.append(search_result)
        
        # Sort by score and limit results
        search_results.sort(key=lambda x: x.score, reverse=True)
        logger.info(f"✅ Поиск по разделу нашел {len(search_results)} результатов в '{target_section}'")
        return search_results[:limit]
        
    except Exception as e:
        logger.error(f"❌ Поиск по конкретному разделу не удался: {e}")
        return []

async def _perform_fallback_search(
    query: str,
    access_level: Optional[str] = None,
    limit: int = 20,
    score_threshold: float = 0.5,
    user_sections: Optional[List[str]] = None
) -> List[DocumentSearchResult]:
    """Perform fallback search across all allowed sections"""
    try:
        logger.info(f"🌐 Альтернативный поиск по разделам: {user_sections}")
        
        # Get embeddings for the query
        query_embedding = await embedding_service.get_embeddings_async(query)
        
        # Build filters for fallback search
        filters = {}
        if access_level:
            filters['access_level'] = access_level
        
        # If user has specific sections, search in each one
        if user_sections:
            logger.info(f"🔍 Ищем в {len(user_sections)} пользовательских разделах: {user_sections}")
            all_results = []
            
            for section in user_sections:
                section_filters = filters.copy()
                section_filters['section'] = section
                
                try:
                    logger.info(f"🔍 Ищем в разделе: {section}")
                    section_results = vector_service.search_similar(
                        query_embedding=query_embedding,
                        limit=limit // len(user_sections),  # Distribute limit across sections
                        score_threshold=score_threshold,
                        filters=section_filters
                    )
                    
                    logger.info(f"📊 Раздел '{section}' вернул {len(section_results)} результатов")
                    
                    # Convert results
                    for result in section_results:
                        search_result = DocumentSearchResult(
                            document_id=result.get('document_id'),
                            chunk_id=result.get('chunk_id'),
                            content=result.get('content', ''),
                            score=result.get('score', 0.0),
                            section=result.get('section', ''),
                            access_level=result.get('access_level', ''),
                            chunk_type=result.get('chunk_type'),
                            page_number=result.get('page_number'),
                            section_name=result.get('section_name'),
                            metadata=result.get('metadata', {})
                        )
                        all_results.append(search_result)
                        
                except Exception as e:
                    logger.warning(f"⚠️ Поиск в разделе {section} не удался: {e}")
                    continue
            
            # Sort by score and return top results
            all_results.sort(key=lambda x: x.score, reverse=True)
            logger.info(f"✅ Альтернативный поиск нашел {len(all_results)} общих результатов по всем разделам")
            return all_results[:limit]
        
        else:
            # No specific sections, search globally
            logger.info("🌍 Выполняем глобальный поиск (без ограничений по разделам)")
            raw_results = vector_service.search_similar(
                query_embedding=query_embedding,
                limit=limit,
                score_threshold=score_threshold,
                filters=filters
            )
            
            # Convert results
            search_results = []
            for result in raw_results:
                search_result = DocumentSearchResult(
                    document_id=result.get('document_id'),
                    chunk_id=result.get('chunk_id'),
                    content=result.get('content', ''),
                    score=result.get('score', 0.0),
                    section=result.get('section', ''),
                    access_level=result.get('access_level', ''),
                    chunk_type=result.get('chunk_type'),
                    page_number=result.get('page_number'),
                    section_name=result.get('section_name'),
                    metadata=result.get('metadata', {})
                )
                search_results.append(search_result)
            
            logger.info(f"✅ Глобальный поиск нашел {len(search_results)} результатов")
            return search_results
        
    except Exception as e:
        logger.error(f"❌ Альтернативный поиск не удался: {e}")
        return []

async def search_documents_by_section(
    query: str,
    target_section: str,
    access_level: Optional[str] = None,
    limit: int = 10,
    score_threshold: float = 0.5
) -> List[DocumentSearchResult]:
    """Enhanced search function specifically for section-based queries"""
    try:
        # Get embeddings for the query
        query_embedding = await embedding_service.get_embeddings_async(query)
        
        # Build strict filters for section-specific search
        filters = {
            'section': target_section
        }
        if access_level:
            filters['access_level'] = access_level
        
        # Use higher score threshold for section-specific search to ensure quality
        adjusted_score_threshold = max(score_threshold, 0.6)
        
        # Search in vector database with section-specific focus
        raw_results = vector_service.search_similar(
            query_embedding=query_embedding,
            limit=limit * 2,  # Get more results initially for better filtering
            score_threshold=adjusted_score_threshold,
            filters=filters
        )
        
        # Convert and filter results
        search_results = []
        for result in raw_results:
            search_result = DocumentSearchResult(
                document_id=result.get('document_id'),
                chunk_id=result.get('chunk_id'),
                content=result.get('content', ''),
                score=result.get('score', 0.0),
                section=result.get('section', ''),
                access_level=result.get('access_level', ''),
                chunk_type=result.get('chunk_type'),
                page_number=result.get('page_number'),
                section_name=result.get('section_name'),
                metadata=result.get('metadata', {})
            )
            search_results.append(search_result)
        
        # Sort by score and limit results
        search_results.sort(key=lambda x: x.score, reverse=True)
        return search_results[:limit]
        
    except Exception as e:
        logger.error(f"Поиск по разделу не удался: {e}")
        return []

async def get_document_info(document_id: int) -> Optional[Dict[str, Any]]:
    """Get basic document information"""
    try:
        # Validate document_id
        if not document_id or document_id <= 0:
            logger.warning(f"⚠️ Некорректный document_id: {document_id}")
            return None
            
        db = get_db_session()
        try:
            document = db.query(Document).filter(Document.id == document_id).first()
            if document:
                logger.info(f"🔍 get_document_info для {document_id}:")
                logger.info(f"   - document.title: {document.title}")
                logger.info(f"   - document.original_filename: {document.original_filename}")
                logger.info(f"   - document.filename: {document.filename}")
                
                # Умная логика получения названия документа
                document_title = None
                
                # 1. Пробуем title (если не пустой и не "string")
                if document.title and document.title != "string" and document.title.strip():
                    document_title = document.title.strip()
                    logger.info(f"   ✅ Используем document.title: '{document_title}'")
                
                # 2. Если title не подходит, пробуем original_filename
                elif document.original_filename and document.original_filename != "string" and document.original_filename.strip():
                    document_title = document.original_filename.strip()
                    logger.info(f"   ✅ Используем document.original_filename: '{document_title}'")
                
                # 3. Если и это не подходит, пробуем filename
                elif document.filename and document.filename != "string" and document.filename.strip():
                    document_title = document.filename.strip()
                    logger.info(f"   ✅ Используем document.filename: '{document_title}'")
                
                # 4. Fallback к ID документа
                else:
                    document_title = f"Документ {document_id}"
                    logger.warning(f"   ⚠️ Все поля пустые или 'string', используем fallback: '{document_title}'")
                
                # Убираем расширение файла для лучшего отображения
                if document_title and '.' in document_title:
                    original_title = document_title
                    document_title = document_title.rsplit('.', 1)[0]
                    logger.info(f"   🔧 Убрали расширение: '{original_title}' → '{document_title}'")
                
                logger.info(f"   - итоговый document_title: '{document_title}'")
                
                return {
                    "id": document.id,
                    "title": document_title,
                    "section": document.section,
                    "access_level": document.access_level,
                    "filename": document.filename,
                    "original_filename": document.original_filename,
                    "mime_type": document.mime_type,
                    "file_type": document.file_type
                }
            else:
                logger.warning(f"⚠️ Документ с ID {document_id} не найден в базе данных")
                return None
        finally:
            db.close()
    except Exception as e:
        logger.error(f"❌ Не удалось получить информацию о документе {document_id}: {e}")
        return None

def get_better_document_name(source_info: Optional[Dict[str, Any]], document_id: int) -> str:
    """Get a better document name for display"""
    logger.info(f"🔍 get_better_document_name для {document_id}:")
    logger.info(f"   - source_info: {source_info}")
    
    if source_info and source_info.get("title"):
        title = source_info["title"]
        
        # Проверяем, что title не равен "string" и не пустой
        if not title or title == "string" or title.strip() == "":
            logger.error(f"❌ title равен 'string' или пустой для документа {document_id}")
            # Используем fallback
            fallback_name = f"Документ {document_id}"
            logger.info(f"   - используем fallback из-за 'string' или пустого: '{fallback_name}'")
            return fallback_name
        
        # Убираем расширение файла если есть
        if '.' in title:
            original_title = title
            title = title.rsplit('.', 1)[0]
            logger.info(f"   🔧 Убрали расширение: '{original_title}' → '{title}'")
        
        logger.info(f"   - используем title: '{title}'")
        return title
    
    # Fallback к более информативному названию
    fallback_name = f"Документ {document_id}"
    logger.info(f"   - используем fallback: '{fallback_name}'")
    return fallback_name


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler"""
    logger.error(f"Необработанная ошибка: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Внутренняя ошибка сервера"}
    )

async def _filter_relevant_sources(sources: List[Dict[str, Any]], ai_response: str, context_chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Умная фильтрация источников - показывает только те документы, 
    которые действительно содержат информацию, использованную в ответе
    """
    try:
        if not sources or not context_chunks:
            logger.info("🔍 Нет источников или контекста для фильтрации")
            return sources
        
        logger.info(f"🔍 Фильтруем {len(sources)} источников по релевантности к ответу")
        
        # Создаем словарь для отслеживания использования документов
        document_usage = {}
        
        # Анализируем каждый чанк контекста
        for chunk in context_chunks:
            doc_id = chunk.get('document_id')
            if doc_id:
                if doc_id not in document_usage:
                    document_usage[doc_id] = {
                        'chunks': [],
                        'total_score': 0,
                        'max_score': 0,
                        'content_length': 0
                    }
                
                # Добавляем информацию о чанке
                document_usage[doc_id]['chunks'].append(chunk)
                document_usage[doc_id]['total_score'] += chunk.get('score', 0)
                document_usage[doc_id]['max_score'] = max(document_usage[doc_id]['max_score'], chunk.get('score', 0))
                document_usage[doc_id]['content_length'] += len(chunk.get('content', ''))
        
        # Фильтруем источники по критериям релевантности
        filtered_sources = []
        for source in sources:
            doc_id = source.get('document_id')
            if doc_id in document_usage:
                usage_info = document_usage[doc_id]
                
                # Критерии релевантности (ужесточенные):
                # 1. Высокий максимальный score (> 0.7) ИЛИ
                # 2. Средний score (> 0.5) И достаточно контента (> 200 символов) И несколько чанков (> 1)
                is_relevant = (
                    usage_info['max_score'] > 0.7 or  # Высокая релевантность
                    (usage_info['max_score'] > 0.5 and  # Средняя релевантность
                     usage_info['content_length'] > 200 and  # Достаточно контента
                     len(usage_info['chunks']) > 1)  # Несколько чанков
                )
                
                if is_relevant:
                    # Добавляем информацию об использовании
                    source['usage_info'] = {
                        'chunks_used': len(usage_info['chunks']),
                        'max_score': usage_info['max_score'],
                        'total_content_length': usage_info['content_length']
                    }
                    filtered_sources.append(source)
                    logger.info(f"✅ Документ {doc_id} включен (score: {usage_info['max_score']:.2f}, чанков: {len(usage_info['chunks'])})")
                else:
                    logger.info(f"❌ Документ {doc_id} исключен (score: {usage_info['max_score']:.2f}, чанков: {len(usage_info['chunks'])})")
            else:
                # Если документ не найден в контексте, исключаем его
                logger.warning(f"⚠️ Документ {doc_id} не найден в контексте, исключаем")
        
        logger.info(f"🎯 Фильтрация завершена: {len(filtered_sources)} из {len(sources)} источников релевантны")
        
        # 🔄 FALLBACK: если все источники отфильтрованы, но есть контекст
        # показываем хотя бы один наиболее релевантный
        if not filtered_sources and sources and context_chunks:
            logger.info(f"⚠️ Все источники отфильтрованы, используем fallback логику")
            
            # Находим источник с наивысшим score
            best_source = max(sources, key=lambda s: document_usage.get(s.get('document_id', 0), {}).get('max_score', 0))
            best_doc_id = best_source.get('document_id')
            
            if best_doc_id and best_doc_id in document_usage:
                best_score = document_usage[best_doc_id]['max_score']
                logger.info(f"✅ Fallback: включаем документ {best_doc_id} с score {best_score:.2f}")
                
                # Добавляем информацию об использовании
                best_source['usage_info'] = {
                    'chunks_used': len(document_usage[best_doc_id]['chunks']),
                    'max_score': best_score,
                    'total_content_length': document_usage[best_doc_id]['content_length'],
                    'fallback_included': True
                }
                filtered_sources = [best_source]
        
        return filtered_sources
        
    except Exception as e:
        logger.error(f"❌ Ошибка при фильтрации источников: {e}")
        # В случае ошибки возвращаем все источники
        return sources

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    )
