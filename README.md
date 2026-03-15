# FastAPI Project: сервис сокращения ссылок

Реализация домашнего задания из ноутбука `FastAPI_project.ipynb`.

## Что реализовано

### Обязательные функции
1. Создание / удаление / изменение / получение короткой ссылки:
   - `POST /links/shorten`
   - `GET /links/{short_code}`
   - `PUT /links/{short_code}`
   - `DELETE /links/{short_code}`
2. Статистика по ссылке:
   - `GET /links/{short_code}/stats`
3. Кастомный alias:
   - `POST /links/shorten` с полем `custom_alias`
4. Поиск по исходному URL:
   - `GET /links/search?original_url=...`
5. Время жизни ссылки:
   - `POST /links/shorten` с полем `expires_at` (точность до минуты)
   - Автоматическое удаление истекших ссылок:
     - фоновый cleanup-процесс
     - удаление при обращении к ссылке

### Регистрация и права доступа
- `POST /auth/register`
- `POST /auth/login`
- `PUT` / `DELETE` доступны только авторизованному владельцу ссылки.
- Анонимные ссылки можно создавать, но изменять/удалять нельзя.

### Кэширование
- Redis кэширует:
  - данные для редиректа (`/links/{short_code}`)
  - статистику (`/links/{short_code}/stats`)
- При `PUT` / `DELETE` кэш инвалидируется.

## Запуск через Docker

1. Скопировать пример окружения:
```bash
cp .env.example .env
```

2. Запустить:
```bash
docker compose up --build
```

3. Открыть документацию:
- `http://localhost:8000/docs`

## Локальный запуск (без Docker)

1. Установить зависимости:
```bash
pip install -r requirements.txt
```

2. Запустить приложение:
```bash
uvicorn app.main:app --reload
```

По умолчанию используется SQLite (`app.db`). Для PostgreSQL и Redis задайте переменные через `.env`.

## Примеры запросов

### Регистрация
```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"user1\",\"email\":\"user1@mail.com\",\"password\":\"secret123\"}"
```

### Логин
```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"user1@mail.com\",\"password\":\"secret123\"}"
```

### Создание короткой ссылки
```bash
curl -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d "{\"original_url\":\"https://example.com/very/long/path\"}"
```

### Создание с кастомным alias и сроком жизни
```bash
curl -X POST http://localhost:8000/links/shorten \
  -H "Content-Type: application/json" \
  -d "{\"original_url\":\"https://example.com\",\"custom_alias\":\"my_alias\",\"expires_at\":\"2026-12-31T23:59:00+00:00\"}"
```

### Редирект
```bash
curl -i http://localhost:8000/links/my_alias
```

### Статистика
```bash
curl http://localhost:8000/links/my_alias/stats
```

### Поиск по URL
```bash
curl "http://localhost:8000/links/search?original_url=https://example.com"
```

### Обновление ссылки (только владелец)
```bash
curl -X PUT http://localhost:8000/links/my_alias \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d "{\"original_url\":\"https://new-example.com\"}"
```

### Удаление ссылки (только владелец)
```bash
curl -X DELETE http://localhost:8000/links/my_alias \
  -H "Authorization: Bearer <TOKEN>"
```

## Описание БД

### Таблица `users`
- `id` (PK)
- `username` (unique)
- `email` (unique)
- `hashed_password`
- `created_at`

### Таблица `links`
- `id` (PK)
- `short_code` (unique)
- `original_url`
- `created_at`
- `updated_at`
- `expires_at`
- `visits`
- `last_used_at`
- `owner_id` (nullable FK на `users.id`)
