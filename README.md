# Telegram AI Bot 24/7

Облачный Telegram AI-бот на Python 3.11+, FastAPI, aiogram 3.x и OpenAI API. Бот работает через webhook, поэтому его можно держать на бесплатном serverless-хостинге Vercel Hobby, а домашний компьютер может быть выключен.

## Что умеет бот

- `/start` - кратко объясняет возможности
- `/ask вопрос` - общий AI-помощник
- `/post тема` - пост для Telegram, Threads или Facebook
- `/translate язык текст` - перевод на чешский, русский или украинский
- `/docs вопрос` - помощь по документам в Чехии
- `/help` - список команд
- `/status` - статус, только для админа из `ADMIN_TELEGRAM_IDS`

В группах бот экономит токены и отвечает только на команды, упоминание бота или ответ на сообщение бота. Сообщения других ботов игнорируются.

## 1. Создать Telegram-бота через BotFather

1. Откройте Telegram и найдите `@BotFather`.
2. Отправьте `/newbot`.
3. Выберите имя и username бота.
4. Сохраните токен. Это значение для `TELEGRAM_BOT_TOKEN`.

## 2. Переменные окружения

Добавьте на хостинге:

```env
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
OPENAI_API_KEY=your_openai_api_key
WEBHOOK_SECRET=random_secret_string
PUBLIC_URL=https://your-app.vercel.app
DATABASE_URL=sqlite:///bot.db
OPENAI_MODEL=gpt-5-mini
ADMIN_TELEGRAM_IDS=123456789
```

`ADMIN_TELEGRAM_IDS` - ваш Telegram user id или username. Можно указать несколько через запятую: `111,222,@viacheslav379`.

Важно: не коммитьте `.env`. В репозитории должен быть только `.env.example`.

## 3. Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

На Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Проверка:

```bash
curl http://localhost:8000/health
```

Ответ:

```json
{"status":"ok"}
```

## 4. Бесплатный deploy на Vercel

Vercel Hobby - основной бесплатный вариант для этого проекта: FastAPI официально поддерживается, webhook запускается как serverless function, а сервис не требует постоянно включенного домашнего компьютера.

Важные ограничения free-тарифа: это вариант для personal/hobby-проектов, есть лимиты на количество вызовов и длительность функций. Для Telegram-бота с умеренным трафиком этого достаточно для старта.

1. Загрузите проект в GitHub.
2. Откройте Vercel и создайте новый Project.
3. Выберите GitHub repository.
4. Vercel увидит `app.py` и `vercel.json`.
5. Framework Preset можно оставить `Other`.
6. Добавьте переменные окружения из раздела выше.
7. Нажмите Deploy.
8. После deploy скопируйте публичный домен вида `https://your-app.vercel.app`.
9. Укажите этот домен в `PUBLIC_URL`.
10. Проверьте healthcheck:

```bash
curl https://your-app.vercel.app/health
```

Ожидаемый ответ:

```json
{"status":"ok"}
```

На serverless-хостинге SQLite-память не подходит для надежного долгого хранения: файл может сбрасываться между деплоями и холодными стартами. Это не ломает бота, но он может потерять короткую историю диалогов. Для устойчивой памяти подключите внешний PostgreSQL и используйте его URL в `DATABASE_URL`.

## 5. Deploy на Koyeb

Koyeb технически подходит для Docker deploy, но в некоторых аккаунтах при onboarding может потребовать billing/Pro plan. Если Free Instance доступен, используйте Dockerfile deploy из GitHub и переменные окружения из раздела выше.

## 6. Deploy на Render

1. Загрузите проект в GitHub.
2. На Render создайте `New Web Service`.
3. Подключите GitHub-репозиторий.
4. Выберите Docker deploy. Render сам использует `Dockerfile`.
5. Добавьте переменные окружения из раздела выше.
6. Deploy.
7. Скопируйте публичный URL сервиса и укажите его в `PUBLIC_URL`.

Для free plan Render сервис может засыпать. Для настоящей работы 24/7 нужен paid instance или хостинг без sleep.

## 7. Deploy на Railway

1. Загрузите проект в GitHub.
2. В Railway создайте новый проект из GitHub repo.
3. Railway обнаружит `Dockerfile`.
4. Добавьте переменные окружения.
5. Убедитесь, что порт берется из Docker/uvicorn и сервис доступен по публичному домену.
6. Укажите этот домен в `PUBLIC_URL`.

## 8. Установка webhook

После deploy выполните:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<PUBLIC_URL>/webhook/<WEBHOOK_SECRET>"
```

Пример:

```bash
curl "https://api.telegram.org/bot123:ABC/setWebhook?url=https://your-app.onrender.com/webhook/my-secret"
```

Проверить webhook можно так:

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo"
```

## 9. Проверка в Telegram

1. Откройте своего бота в Telegram.
2. Отправьте `/start`.
3. Отправьте `/ask Придумай план на день`.
4. Для проверки статуса отправьте `/status` с аккаунта, id которого указан в `ADMIN_TELEGRAM_IDS`.

## 10. GitHub и Codex Cloud с телефона

1. Храните код в GitHub.
2. С телефона создавайте issue, pull request или задачу для Codex Cloud.
3. Codex Cloud меняет код в GitHub.
4. Vercel автоматически redeploy-ит сервис после push в основную ветку, если включен auto deploy.
5. Бот продолжает работать в облаке независимо от домашнего компьютера.

## Безопасность и лимиты

- `.env` добавлен в `.gitignore`.
- Ключи Telegram и OpenAI не логируются.
- В группах бот отвечает только когда его явно вызывают.
- Лимит AI-запросов: 5 в минуту на пользователя.
- В памяти хранится только `user_id`, `chat_id`, `username`, последние 5 сообщений и короткое резюме по `chat_id`.
- Ответ AI ограничен настройками промпта и `max_completion_tokens`.

## База данных

По умолчанию используется SQLite:

```env
DATABASE_URL=sqlite:///bot.db
```

Это самый быстрый вариант для старта. Для production с несколькими инстансами лучше перейти на PostgreSQL.
Если Render или Railway выдали PostgreSQL URL, укажите его в `DATABASE_URL`:

```env
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

В проекте уже есть простая поддержка PostgreSQL через `psycopg`.
