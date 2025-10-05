# RAG Assistant

A comprehensive Retrieval-Augmented Generation (RAG) system for analyzing contracts, drawings, and various document formats.

## 🚀 Features

- **Multi-format Document Support**: PDF, DOC, DOCX, MD, TXT, Excel files
- **Advanced Search**: Hybrid search combining semantic and keyword matching
- **Multiple LLM Support**: Gemini, GPT-4, DeepSeek integration
- **Flexible Embeddings**: OpenAI and HuggingFace embedding models
- **Scalable Architecture**: Cloud and local deployment options
- **Web Interface**: Modern React-based UI
- **API Access**: RESTful API for integration

## 📋 Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- Docker (optional, for containerized deployment)

### Installation

1. **Clone the repository**
   ```bash
   git clone <your-repo-url>
   cd rag_gemini
   ```

2. **Set up Python environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp env.example .env
   # Edit .env with your API keys and settings
   ```

4. **Run the application**
   ```bash
   python -m uvicorn src.main:app --reload
   ```

5. **Access the application**
   - API: http://localhost:8000
   - API Documentation: http://localhost:8000/docs
   - Frontend: http://localhost:3000 (if running)

## 📁 Project Structure

```
rag_gemini/
├── src/
│   ├── api/           # FastAPI routes and dependencies
│   ├── core/          # Configuration and core services
│   ├── ingestion/     # Document parsing and processing
│   ├── retrieval/     # Vector search and retrieval
│   ├── generation/    # LLM integration and response generation
│   └── models/        # Data models and schemas
├── frontend/          # React/Next.js frontend
├── tests/            # Test files
├── docker/           # Docker configuration
├── docs/             # Documentation
└── scripts/          # Utility scripts
```

## 🔧 Configuration

### Environment Variables

Key configuration options in `.env`:

- `OPENAI_API_KEY`: OpenAI API key for embeddings and GPT models
- `GEMINI_API_KEY`: Google Gemini API key
- `DATABASE_URL`: Database connection string
- `VECTOR_STORE_TYPE`: Vector database type (chroma, weaviate)
- `EMBEDDING_PROVIDER`: Embedding service (huggingface, openai)
- `LLM_PROVIDER`: Primary LLM provider (gemini, openai)

### Supported File Formats

- PDF documents
- Microsoft Word (DOC, DOCX)
- Markdown files
- Plain text files
- Excel spreadsheets (XLS, XLSX)

## 🛠️ API Usage

### Upload Documents

```bash
curl -X POST "http://localhost:8000/api/v1/documents/upload" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@document.pdf"
```

### Search Documents

```bash
curl -X POST "http://localhost:8000/api/v1/search/" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "What are the main terms of this contract?",
    "top_k": 5,
    "filters": {"file_type": "pdf"}
  }'
```

### Chat with Assistant

```bash
curl -X POST "http://localhost:8000/api/v1/chat/" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain the key points from the uploaded documents",
    "top_k": 5
  }'
```

## 🏗️ Architecture

### Core Components

1. **Document Ingestion Pipeline**
   - File parsing and text extraction
   - Semantic chunking for optimal retrieval
   - Embedding generation and storage

2. **Retrieval System**
   - Vector similarity search
   - Keyword matching
   - Hybrid search fusion

3. **Generation Engine**
   - LLM integration (Gemini, GPT, DeepSeek)
   - Context management
   - Response generation

4. **Storage Layer**
   - Vector database (Chroma, Weaviate)
   - Document metadata storage
   - File system integration

### Data Flow

```
Documents → Parser → Chunker → Embedder → Vector Store
                                        ↓
Query → Embedder → Vector Search → LLM → Response
```

## 🚀 Deployment

### Docker Deployment

```bash
# Build and run with Docker Compose
docker-compose up -d

# Access services
# API: http://localhost:8000
# Frontend: http://localhost:3000
```

### Cloud Deployment

The system is designed for cloud deployment with:
- Containerized services
- Scalable vector databases
- Load balancing support
- Monitoring and logging

### Local Deployment

For on-premises deployment:
- Single-machine setup
- Client-specific configurations
- Data privacy compliance

## 📊 Performance Considerations

### Optimization Strategies

- **Caching**: Redis for query and response caching
- **Batch Processing**: Efficient document processing
- **Async Operations**: Non-blocking API endpoints
- **Vector Indexing**: Optimized similarity search

### Scalability

- Horizontal scaling with load balancers
- Database sharding for large datasets
- CDN integration for file storage
- Microservices architecture

## 🧪 Testing

```bash
# Run tests
pytest tests/

# Run with coverage
pytest --cov=src tests/

# Run specific test file
pytest tests/test_api.py
```

## 📈 Monitoring

### Key Metrics

- Document processing time
- Search response time
- LLM generation latency
- API endpoint performance
- Error rates and logs

### Tools

- Prometheus for metrics collection
- Grafana for visualization
- ELK stack for logging
- Health check endpoints

## 🔒 Security

### Security Features

- API authentication and authorization
- File upload validation
- Input sanitization
- Rate limiting
- Data encryption

### Best Practices

- Secure API key management
- Regular security updates
- Access control implementation
- Audit logging

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the documentation
- Review the API documentation at `/docs`

## 🗺️ Roadmap

### Planned Features

- [ ] Multi-language support
- [ ] Advanced document types (CAD, images)
- [ ] Real-time collaboration
- [ ] Advanced analytics
- [ ] Mobile application
- [ ] Enterprise integrations

### Current Version: 1.0.0

- Core RAG functionality
- Multi-format document support
- Web interface
- API access
- Docker deployment

