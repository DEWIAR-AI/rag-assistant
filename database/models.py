from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class Document(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    file_type = Column(String(50), nullable=False)
    mime_type = Column(String(100), nullable=False)
    
    # Document metadata
    title = Column(String(255))
    description = Column(Text)
    section = Column(String(100), nullable=False)  # restaurant_ops, kitchen_ops, recipes, etc.
    access_level = Column(String(100), nullable=False)  # restaurant_management, kitchen_management, concepts_recipes
    
    # Processing status
    is_processed = Column(Boolean, default=False)
    processing_error = Column(Text)
    
    # OCR and content info
    has_images = Column(Boolean, default=False)
    text_content = Column(Text)
    extracted_metadata = Column(JSON)
    
    # Timestamps
    uploaded_at = Column(DateTime, default=func.now())
    processed_at = Column(DateTime)
    
    # Relationships
    chunks = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', section='{self.section}')>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    
    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    
    # Content
    content = Column(Text, nullable=False)
    content_length = Column(Integer, nullable=False)
    
    # Vector embedding
    embedding_id = Column(String(255))  # Qdrant vector ID
    
    # Metadata
    page_number = Column(Integer)
    section_name = Column(String(255))  # For Excel sheets, PDF sections, etc.
    chunk_type = Column(String(50))  # text, table, image_caption, etc.
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="chunks")
    
    def __repr__(self):
        return f"<DocumentChunk(id={self.id}, document_id={self.document_id}, chunk_index={self.chunk_index})>"


class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    
    # Subscription and company info
    subscription_type = Column(String(100), nullable=False)  # restaurant_management, kitchen_management, concepts_recipes
    company_name = Column(String(255))
    
    # Account status
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime)
    
    # Relationships
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', subscription_type='{self.subscription_type}')>"


class UserRole(Base):
    __tablename__ = "user_roles"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    role_name = Column(String(100), nullable=False)
    allowed_sections = Column(JSON, nullable=False)  # List of allowed sections
    detailed_access = Column(JSON, nullable=True)  # Detailed access control per section
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    user = relationship("User", back_populates="roles")
    
    def __repr__(self):
        return f"<UserRole(id={self.id}, user_id={self.user_id}, role_name='{self.role_name}')>"


class AccessToken(Base):
    __tablename__ = "access_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    token_hash = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    
    # Access control
    access_level = Column(String(100), nullable=False)
    allowed_sections = Column(JSON, nullable=False)  # List of allowed sections
    is_active = Column(Boolean, default=True)
    
    # Rate limiting
    rate_limit_per_hour = Column(Integer, default=1000)
    current_usage = Column(Integer, default=0)
    last_reset = Column(DateTime, default=func.now())
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    expires_at = Column(DateTime)
    
    def __repr__(self):
        return f"<AccessToken(id={self.id}, name='{self.name}', access_level='{self.access_level}')>"


class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String(255), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    
    # Conversation metadata
    title = Column(String(255))
    user_context = Column(Text)
    
    # Session context for RAG
    current_section = Column(String(100))  # Current section being discussed
    document_context = Column(JSON)  # Previously found documents and their content
    search_context = Column(JSON)  # Previous search queries and results
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    last_activity = Column(DateTime, default=func.now())
    
    # Relationships
    messages = relationship("ConversationMessage", back_populates="conversation", cascade="all, delete-orphan")
    user = relationship("User", back_populates="conversations")
    
    def __repr__(self):
        return f"<Conversation(id={self.id}, session_id='{self.session_id}')>"


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"
    
    id = Column(Integer, primary_key=True, index=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    
    # Message content
    role = Column(String(50), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    
    # RAG context
    source_chunks = Column(JSON)  # List of chunk IDs used for response
    source_documents = Column(JSON)  # List of document IDs used for response
    
    # Enhanced context for conversational memory
    search_query = Column(Text)  # The search query that was used
    search_results = Column(JSON)  # Full search results including document content
    used_sections = Column(JSON)  # Sections that were searched
    context_relevance_score = Column(Float)  # How relevant the context was
    
    # Metadata
    tokens_used = Column(Integer)
    processing_time = Column(Float)
    
    # Timestamps
    created_at = Column(DateTime, default=func.now())
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    
    def __repr__(self):
        return f"<ConversationMessage(id={self.id}, role='{self.role}', conversation_id={self.conversation_id})>"
