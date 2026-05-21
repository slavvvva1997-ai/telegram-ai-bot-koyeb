from datetime import datetime, timezone
from html import escape

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, Update, User

from app.config import Settings
from app.github_client import GitHubService
from app.openai_client import OpenAIService
from app.prompts import COMMAND_HELP
from app.storage import RateLimiter, Storage, compact_summary


router = Router()
STARTED_AT = datetime.now(timezone.utc)
storage: Storage | None = None
openai_service: OpenAIService | None = None
github_service: GitHubService | None = None
settings: Settings | None = None
rate_limiter = RateLimiter(max_requests=5, window_seconds=60)


def create_bot_and_dispatcher(app_settings: Settings) -> tuple[Bot, Dispatcher]:
    global storage, openai_service, github_service, settings
    settings = app_settings
    storage = Storage(app_settings.database_url)
    storage.connect()
    openai_service = OpenAIService(app_settings.openai_api_key, app_settings.openai_model)
    github_service = GitHubService(app_settings.github_token, app_settings.github_repo)

    bot = Bot(token=app_settings.telegram_bot_token, default=DefaultBotProperties(parse_mode="HTML"))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    return bot, dispatcher


async def feed_update(bot: Bot, dispatcher: Dispatcher, update_data: dict) -> None:
    update = Update.model_validate(update_data, context={"bot": bot})
    await dispatcher.feed_update(bot, update)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await remember_user(message)
    await message.answer(
        "Привет! Я облачный AI-бот: отвечаю на вопросы, пишу посты, перевожу и помогаю "
        "разобраться с документами в Чехии.\n\n" + COMMAND_HELP
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await remember_user(message)
    await message.answer(COMMAND_HELP)


@router.message(Command("ask"))
async def cmd_ask(message: Message, command: CommandObject) -> None:
    await handle_ai_command(message, command.args, "general", "Напишите вопрос после /ask.")


@router.message(Command("post"))
async def cmd_post(message: Message, command: CommandObject) -> None:
    await handle_ai_command(message, command.args, "content", "Напишите тему поста после /post.")


@router.message(Command("translate"))
async def cmd_translate(message: Message, command: CommandObject) -> None:
    await handle_ai_command(
        message,
        command.args,
        "translator",
        "Напишите целевой язык и текст после /translate. Например: /translate чешский Добрый день",
    )


@router.message(Command("docs"))
async def cmd_docs(message: Message, command: CommandObject) -> None:
    await handle_ai_command(message, command.args, "docs", "Напишите вопрос по документам после /docs.")


@router.message(Command("status"))
async def cmd_status(message: Message) -> None:
    await remember_user(message)
    if not is_admin(message.from_user):
        await message.answer("Команда /status доступна только администратору.")
        return

    assert storage is not None and settings is not None
    stats = storage.stats()
    uptime = datetime.now(timezone.utc) - STARTED_AT
    await message.answer(
        "\n".join(
            [
                "<b>Статус бота</b>",
                f"Модель: <code>{escape(settings.openai_model)}</code>",
                f"Uptime: <code>{str(uptime).split('.')[0]}</code>",
                f"Сообщений в памяти: <code>{stats['messages']}</code>",
                f"Пользователей: <code>{stats['users']}</code>",
                f"Чатов: <code>{stats['chats']}</code>",
                f"База данных: <code>{stats['mode']}</code>",
            ]
        )
    )


@router.message(Command("task"))
async def cmd_task(message: Message, command: CommandObject) -> None:
    await remember_user(message)
    if not is_admin(message.from_user):
        await message.answer("Команда /task доступна только администратору.")
        return

    task_text = (command.args or "").strip()
    if not task_text:
        await message.answer("Напишите задачу после /task. Например: /task добавь команду экспорта истории")
        return

    assert github_service is not None and settings is not None
    if not github_service.configured:
        await message.answer("GitHub bridge не настроен. Добавьте GITHUB_TOKEN и GITHUB_REPO в Vercel.")
        return

    username = message.from_user.username if message.from_user else None
    body = (
        "Task created from Telegram for Cursor/Background Agent.\n\n"
        f"From: @{username or 'unknown'}\n"
        f"Chat ID: {message.chat.id}\n\n"
        "Request:\n"
        f"{task_text}\n\n"
        "Suggested workflow:\n"
        "- Open this issue in Cursor or assign it to a Cursor Background Agent.\n"
        "- Implement in a branch and open a pull request.\n"
    )
    title = f"Cursor task: {task_text.splitlines()[0][:80]}"
    try:
        issue_url = await github_service.create_issue(title=title, body=body)
    except Exception as exc:
        await message.answer(f"Не получилось создать GitHub issue: {escape(str(exc))}")
        return

    await message.answer(f"Задача создана для Cursor:\n{issue_url}")


@router.message(F.text)
async def handle_text(message: Message, bot: Bot) -> None:
    if not await should_respond(message, bot):
        return
    text = message.text or ""
    if text.startswith("/"):
        return
    await handle_ai_command(message, text, "general", "")


async def handle_ai_command(message: Message, text: str | None, mode: str, empty_hint: str) -> None:
    await remember_user(message)
    cleaned = (text or "").strip()
    if not cleaned:
        await message.answer(empty_hint)
        return
    if not message.from_user:
        return
    if message.from_user.is_bot:
        return
    if not rate_limiter.allow(message.from_user.id):
        await message.answer("Слишком много AI-запросов. Лимит: 5 запросов в минуту на пользователя.")
        return

    assert storage is not None and openai_service is not None
    memory = storage.get_memory(message.chat.id)
    storage.add_message(message.chat.id, message.from_user.id, "user", cleaned)
    answer = await openai_service.answer(mode, cleaned, memory)
    storage.add_message(message.chat.id, 0, "assistant", answer)
    storage.update_summary(message.chat.id, compact_summary(memory.summary, cleaned, answer))
    await message.answer(answer[:4096])


async def should_respond(message: Message, bot: Bot) -> bool:
    if not message.from_user or message.from_user.is_bot:
        return False
    if message.chat.type == "private":
        return True
    text = message.text or ""
    if text.startswith("/"):
        return True
    me = await bot.get_me()
    if me.username and f"@{me.username}".lower() in text.lower():
        return True
    if message.reply_to_message and message.reply_to_message.from_user:
        return message.reply_to_message.from_user.id == me.id
    return False


async def remember_user(message: Message) -> None:
    if storage is None or not message.from_user:
        return
    storage.save_user(message.from_user.id, message.from_user.username)
    storage.ensure_chat(message.chat.id)


def is_admin(user: User | None) -> bool:
    if user is None or settings is None:
        return False
    if user.id in settings.admin_ids:
        return True
    allowed_usernames = {
        item.strip().lstrip("@").lower()
        for item in settings.admin_telegram_ids.split(",")
        if item.strip() and not item.strip().isdigit()
    }
    return bool(user.username and user.username.lower() in allowed_usernames)
