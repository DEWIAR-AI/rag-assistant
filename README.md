# RAG Restaurant Management System

Система управления и поиска по документам с использованием ИИ и векторной базы данных.

## Основные зависимости

* **Python 3.8+**
* **FastAPI**
* **PostgreSQL / Supabase** (рекомендуется Supabase)
* **Qdrant** (Vector DB, Qdrant Cloud)
* **OpenAI API**

## Переменные окружения

Для запуска необходимо указать следующие параметры в `.env`:

```env
# База данных (Supabase)
DATABASE_URL=postgresql://username:password@db.supabase.co:5432/postgres
SUPABASE_URL=https://<project-id>.supabase.co
SUPABASE_SERVICE_KEY=<your-service-key>

# OpenAI
OPENAI_API_KEY=your_openai_api_key

# Qdrant (Cloud)
QDRANT_URL=https://<cluster-id>.qdrant.io
QDRANT_API_KEY=your_qdrant_api_key
```

Остальные настройки (JWT ключи, DEBUG, порты) можно оставить по умолчанию для тестов.

## Установка и запуск

1. Клонировать репозиторий:

```bash
git clone https://github.com/DEWIAR-AI/rag-assistant
cd rag
```

2. Установить зависимости:

```bash
pip install -r requirements.txt
```

3. Запустить приложение:

```bash
python main.py
```

Приложение будет доступно на `http://localhost:8000/docs`

## Запуск в Docker (опционально, для production)

```bash
docker build -t rag-system .
docker-compose up -d
```

## Основные API endpoints

### Аутентификация

* `POST /auth/register` — регистрация
* `POST /auth/login` — вход (важно будет вручную вставить токен для входа)

### Документы

* `POST /documents/upload` — загрузка документа
* `GET /documents/search` — поиск по содержимому
* `GET /documents/{id}` — получить документ
* `DELETE /documents/{id}` — удалить документ

### Чат

* `POST /chat` — чат с документами
