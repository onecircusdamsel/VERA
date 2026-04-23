import os
import json
import time
import logging
import requests
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from supabase import create_client, Client

# =========================
# Загрузка переменных
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client | None = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("Supabase подключен успешно ✅")
    except Exception as e:
        print("Ошибка подключения Supabase:", e)
        supabase = None


# =========================
# Логирование
# =========================
logging.basicConfig(
    filename="errors.log",
    level=logging.ERROR,
    format="%(asctime)s | %(levelname)s | %(message)s",
    encoding="utf-8"
)

# =========================
# Локальная память как резерв
# =========================
user_data_store = {}

RELIGION_BUTTONS = ["Христианство", "Ислам", "Буддизм", "Иудаизм"]

RELIGION_EMOJI = {
    "Христианство": "✝️",
    "Ислам": "☪️",
    "Буддизм": "☸️",
    "Иудаизм": "✡️",
}

CONTROVERSIAL_KEYWORDS = [
    "какая религия лучше",
    "какая религия правильная",
    "кто прав",
    "кто неправильный",
    "чья вера истинная",
    "какая вера истинная",
    "чья религия лучше",
    "почему одна религия лучше другой",
    "какая религия самая правильная",
]


# =========================
# Supabase helper functions
# =========================
def db_enabled() -> bool:
    return supabase is not None


def db_get_or_create_user(telegram_user_id: int, first_name: str | None, username: str | None):
    if not db_enabled():
        return None

    try:
        result = supabase.rpc(
            "get_or_create_bot_user",
            {
                "p_telegram_user_id": telegram_user_id,
                "p_first_name": first_name,
                "p_username": username,
            }
        ).execute()
        return result.data
    except Exception as e:
        logging.error("Supabase get_or_create_bot_user error: %s", str(e))
        return None


def db_set_user_religion(telegram_user_id: int, religion: str | None):
    if not db_enabled():
        return

    try:
        supabase.rpc(
            "set_user_religion",
            {
                "p_telegram_user_id": telegram_user_id,
                "p_religion": religion,
            }
        ).execute()
    except Exception as e:
        logging.error("Supabase set_user_religion error: %s", str(e))


def db_set_last_question(telegram_user_id: int, question: str):
    if not db_enabled():
        return

    try:
        supabase.rpc(
            "set_last_question",
            {
                "p_telegram_user_id": telegram_user_id,
                "p_question": question,
            }
        ).execute()
    except Exception as e:
        logging.error("Supabase set_last_question error: %s", str(e))


def db_add_question_history(telegram_user_id: int, question: str):
    if not db_enabled():
        return

    try:
        supabase.rpc(
            "add_question_history",
            {
                "p_telegram_user_id": telegram_user_id,
                "p_question": question,
            }
        ).execute()
    except Exception as e:
        logging.error("Supabase add_question_history error: %s", str(e))


def db_increment_questions_count(telegram_user_id: int):
    if not db_enabled():
        return

    try:
        supabase.rpc(
            "increment_questions_count",
            {
                "p_telegram_user_id": telegram_user_id,
            }
        ).execute()
    except Exception as e:
        logging.error("Supabase increment_questions_count error: %s", str(e))


def db_increment_compare_count(telegram_user_id: int):
    if not db_enabled():
        return

    try:
        supabase.rpc(
            "increment_compare_count",
            {
                "p_telegram_user_id": telegram_user_id,
            }
        ).execute()
    except Exception as e:
        logging.error("Supabase increment_compare_count error: %s", str(e))


def db_increment_mode_usage(telegram_user_id: int, mode: str):
    if not db_enabled():
        return

    try:
        supabase.rpc(
            "increment_mode_usage",
            {
                "p_telegram_user_id": telegram_user_id,
                "p_mode": mode,
            }
        ).execute()
    except Exception as e:
        logging.error("Supabase increment_mode_usage error: %s", str(e))


def db_reset_user_state(telegram_user_id: int):
    if not db_enabled():
        return

    try:
        supabase.rpc(
            "reset_user_state",
            {
                "p_telegram_user_id": telegram_user_id,
            }
        ).execute()
    except Exception as e:
        logging.error("Supabase reset_user_state error: %s", str(e))


def db_add_error_log(
    telegram_user_id: int | None,
    error_place: str,
    error_type: str,
    error_message: str,
    message_text: str | None = None,
):
    if not db_enabled():
        return

    try:
        supabase.rpc(
            "add_error_log",
            {
                "p_telegram_user_id": telegram_user_id,
                "p_error_place": error_place,
                "p_error_type": error_type,
                "p_error_message": error_message,
                "p_message_text": message_text,
            }
        ).execute()
    except Exception as e:
        logging.error("Supabase add_error_log error: %s", str(e))


def db_get_user_full_data(telegram_user_id: int):
    if not db_enabled():
        return None

    try:
        result = (
            supabase.table("user_profile_view")
            .select("*")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]
        return None
    except Exception as e:
        logging.error("Supabase db_get_user_full_data error: %s", str(e))
        return None


def db_get_question_history(telegram_user_id: int):
    if not db_enabled():
        return []

    try:
        user_result = (
            supabase.table("bot_users")
            .select("id")
            .eq("telegram_user_id", telegram_user_id)
            .limit(1)
            .execute()
        )

        if not user_result.data:
            return []

        user_id = user_result.data[0]["id"]

        history_result = (
            supabase.table("question_history")
            .select("question_text, created_at")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(5)
            .execute()
        )

        return history_result.data or []
    except Exception as e:
        logging.error("Supabase db_get_question_history error: %s", str(e))
        return []


# =========================
# Общие функции
# =========================
def log_error(error_place: str, error: Exception, update: Update = None):
    user_info = "Неизвестно"
    message_text = "Нет текста"
    telegram_user_id = None

    try:
        if update and update.effective_user:
            user = update.effective_user
            telegram_user_id = user.id
            user_info = f"id={user.id}, name={user.first_name}"

        if update and update.message and update.message.text:
            message_text = update.message.text
    except Exception:
        pass

    logging.error(
        f"Место: {error_place} | "
        f"Пользователь: {user_info} | "
        f"Сообщение: {message_text} | "
        f"Ошибка: {type(error).__name__}: {error}"
    )

    db_add_error_log(
        telegram_user_id=telegram_user_id,
        error_place=error_place,
        error_type=type(error).__name__,
        error_message=str(error),
        message_text=message_text,
    )


def get_main_keyboard():
    keyboard = [
        ["Христианство", "Ислам"],
        ["Буддизм", "Иудаизм"],
        ["Сравнить ответы", "Перезапуск бота"],
        ["История вопросов", "Статистика"],
        ["Помощь", "О проекте"],
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)


def get_user_state(user_id: int):
    if user_id not in user_data_store:
        user_data_store[user_id] = {
            "last_question": None,
            "selected_religion": None,
            "history": [],
            "stats": {
                "questions_count": 0,
                "compare_count": 0,
                "mode_usage": {
                    "Христианство": 0,
                    "Ислам": 0,
                    "Буддизм": 0,
                    "Иудаизм": 0,
                    "Общий": 0,
                }
            }
        }
    return user_data_store[user_id]


def add_question_to_history(state: dict, question: str):
    history = state["history"]
    if question in history:
        history.remove(question)
    history.insert(0, question)
    state["history"] = history[:5]


def is_controversial_question(text: str) -> bool:
    lower_text = text.lower()
    return any(keyword in lower_text for keyword in CONTROVERSIAL_KEYWORDS)


def format_answer(mode: str | None, answer: str) -> str:
    answer = answer.replace("*", "").strip()
    answer = answer.replace("\r\n", "\n")

    while "\n\n\n" in answer:
        answer = answer.replace("\n\n\n", "\n\n")

    if mode:
        emoji = RELIGION_EMOJI.get(mode, "📘")
        return f"Текущий режим: {emoji} {mode}\n\n{answer}"

    return answer


def format_history(history: list[str]) -> str:
    if not history:
        return "История вопросов пока пуста."

    lines = ["Ваши последние вопросы:"]
    for i, q in enumerate(history, start=1):
        lines.append(f"{i}. {q}")
    return "\n".join(lines)


def format_stats(state: dict) -> str:
    stats = state["stats"]
    m = stats["mode_usage"]

    return (
        "Статистика использования:\n\n"
        f"Всего вопросов: {stats['questions_count']}\n"
        f"Сравнений: {stats['compare_count']}\n\n"
        "Режимы:\n"
        f"✝️ Христианство: {m['Христианство']}\n"
        f"☪️ Ислам: {m['Ислам']}\n"
        f"☸️ Буддизм: {m['Буддизм']}\n"
        f"✡️ Иудаизм: {m['Иудаизм']}\n"
        f"📘 Общий: {m['Общий']}"
    )


async def send_welcome_message(update: Update):
    first_name = update.effective_user.first_name or "друг"

    await update.message.reply_text(
        f"Здравствуйте, {first_name}! 👋\n"
        "Я FaithHelperBot — справочный бот по религиозной тематике.\n\n"
        "Возможности:\n"
        "— ответы на вопросы;\n"
        "— режимы по религиям;\n"
        "— сравнение ответов;\n"
        "— история вопросов;\n"
        "— статистика.\n\n"
        "Выберите режим кнопками ниже или просто задайте вопрос.\n"
        "Если режим не выбран, будет дан нейтральный общий ответ.",
        reply_markup=get_main_keyboard()
    )


# =========================
# Команды
# =========================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    db_get_or_create_user(
        telegram_user_id=user_id,
        first_name=update.effective_user.first_name,
        username=update.effective_user.username,
    )

    user_data_store[user_id] = {
        "last_question": None,
        "selected_religion": None,
        "history": [],
        "stats": {
            "questions_count": 0,
            "compare_count": 0,
            "mode_usage": {
                "Христианство": 0,
                "Ислам": 0,
                "Буддизм": 0,
                "Иудаизм": 0,
                "Общий": 0,
            }
        }
    }
    await send_welcome_message(update)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Как пользоваться ботом:\n\n"
        "1. Напишите вопрос.\n"
        "2. При желании выберите религию.\n"
        "3. Нажмите «Сравнить ответы».\n"
        "4. Используйте «История вопросов» и «Статистика».\n"
        "5. «Перезапуск бота» сбрасывает данные."
    )


async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "FaithHelperBot — Telegram-бот на Python с использованием OpenRouter API и Supabase."
    )


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db_data = db_get_user_full_data(update.effective_user.id)

    if db_data:
        text = (
            "Статистика использования:\n\n"
            f"Всего вопросов: {db_data.get('questions_count', 0)}\n"
            f"Сравнений: {db_data.get('compare_count', 0)}\n\n"
            "Режимы:\n"
            f"✝️ Христианство: {db_data.get('christianity_count', 0)}\n"
            f"☪️ Ислам: {db_data.get('islam_count', 0)}\n"
            f"☸️ Буддизм: {db_data.get('buddhism_count', 0)}\n"
            f"✡️ Иудаизм: {db_data.get('judaism_count', 0)}\n"
            f"📘 Общий: {db_data.get('general_count', 0)}"
        )
        await update.message.reply_text(text)
    else:
        state = get_user_state(update.effective_user.id)
        await update.message.reply_text(format_stats(state))


# =========================
# OpenRouter
# =========================
def build_system_prompt(mode: str | None) -> str:
    base = (
        "Ты религиозный справочный помощник. "
        "Отвечай только на русском языке. "
        "Не используй другие языки. "
        "Пиши понятно, вежливо и нейтрально. "
        "Обычно делай 2 абзаца: краткий ответ и пояснение. "
        "Не используй markdown и специальные символы форматирования. "
        "Если вопрос спорный или зависит от конфессии, укажи это спокойно и нейтрально."
    )

    if mode == "Христианство":
        return base + " Отвечай в контексте христианства."
    if mode == "Ислам":
        return base + " Отвечай в контексте ислама."
    if mode == "Буддизм":
        return base + " Отвечай в контексте буддизма."
    if mode == "Иудаизм":
        return base + " Отвечай в контексте иудаизма."

    return base


def send_openrouter_request(data: dict) -> str:
    url = "https://openrouter.ai/api/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    max_retries = 3
    delay_seconds = 2

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=data,
                timeout=120
            )
            response.raise_for_status()

            result = response.json()

            if "choices" not in result or not result["choices"]:
                logging.error(
                    "Некорректный ответ API: %s",
                    json.dumps(result, ensure_ascii=False)
                )
                return "Не удалось получить корректный ответ от нейросети."

            return result["choices"][0]["message"]["content"].replace("*", "")

        except requests.exceptions.Timeout as e:
            logging.error("Timeout OpenRouter, попытка %s: %s", attempt, str(e))
            if attempt == max_retries:
                raise
            time.sleep(delay_seconds)

        except requests.exceptions.SSLError as e:
            logging.error("SSL ошибка OpenRouter, попытка %s: %s", attempt, str(e))
            if attempt == max_retries:
                raise
            time.sleep(delay_seconds)

        except requests.exceptions.ConnectionError as e:
            logging.error("ConnectionError OpenRouter, попытка %s: %s", attempt, str(e))
            if attempt == max_retries:
                raise
            time.sleep(delay_seconds)

        except requests.exceptions.RequestException as e:
            logging.error("RequestException OpenRouter, попытка %s: %s", attempt, str(e))
            if attempt == max_retries:
                raise
            time.sleep(delay_seconds)

    return "Не удалось получить ответ от нейросети."


def ask_ai(question: str, mode: str | None = None) -> str:
    data = {
        "model": "openai/gpt-oss-120b",
        "temperature": 0.2,
        "messages": [
            {"role": "system", "content": build_system_prompt(mode)},
            {"role": "user", "content": question}
        ]
    }

    return send_openrouter_request(data)


def ask_compare(question: str) -> str:
    data = {
        "model": "openai/gpt-oss-120b",
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Сравни вопрос в 4 контекстах: "
                    "христианство, ислам, буддизм, иудаизм. "
                    "Отвечай только на русском языке. "
                    "Коротко, нейтрально и понятно. "
                    "Сделай 4 отдельных коротких блока."
                )
            },
            {
                "role": "user",
                "content": question
            }
        ]
    }

    return send_openrouter_request(data)


# =========================
# Основная логика
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_text = update.message.text.strip()
    user_id = update.effective_user.id
    state = get_user_state(user_id)

    # Создаём пользователя в БД при первом сообщении
    db_get_or_create_user(
        telegram_user_id=user_id,
        first_name=update.effective_user.first_name,
        username=update.effective_user.username,
    )

    if user_text == "Помощь":
        await help_command(update, context)
        return

    if user_text == "О проекте":
        await about_command(update, context)
        return

    if user_text == "История вопросов":
        db_history = db_get_question_history(user_id)

        if db_history:
            questions = [item["question_text"] for item in db_history]
            await update.message.reply_text(format_history(questions))
        else:
            await update.message.reply_text(format_history(state["history"]))
        return

    if user_text == "Статистика":
        db_data = db_get_user_full_data(user_id)

        if db_data:
            text = (
                "Статистика использования:\n\n"
                f"Всего вопросов: {db_data.get('questions_count', 0)}\n"
                f"Сравнений: {db_data.get('compare_count', 0)}\n\n"
                "Режимы:\n"
                f"✝️ Христианство: {db_data.get('christianity_count', 0)}\n"
                f"☪️ Ислам: {db_data.get('islam_count', 0)}\n"
                f"☸️ Буддизм: {db_data.get('buddhism_count', 0)}\n"
                f"✡️ Иудаизм: {db_data.get('judaism_count', 0)}\n"
                f"📘 Общий: {db_data.get('general_count', 0)}"
            )
            await update.message.reply_text(text)
        else:
            await update.message.reply_text(format_stats(state))
        return

    if user_text == "Перезапуск бота":
        await start(update, context)
        db_reset_user_state(user_id)
        return

    if user_text in RELIGION_BUTTONS:
        state["selected_religion"] = user_text
        state["stats"]["mode_usage"][user_text] += 1

        db_set_user_religion(user_id, user_text)
        db_increment_mode_usage(user_id, user_text)

        if state["last_question"]:
            try:
                msg = await update.message.reply_text("Думаю... 🤖")
                answer = ask_ai(state["last_question"], user_text)
                await msg.delete()
                await update.message.reply_text(format_answer(user_text, answer))

            except requests.exceptions.Timeout as e:
                log_error("change_mode_timeout", e, update)
                await update.message.reply_text(
                    "Сервер отвечает слишком долго. Попробуйте ещё раз через несколько секунд."
                )

            except requests.exceptions.SSLError as e:
                log_error("change_mode_ssl", e, update)
                await update.message.reply_text(
                    "Проблема с защищённым соединением. Попробуйте ещё раз чуть позже."
                )

            except requests.exceptions.ConnectionError as e:
                log_error("change_mode_connection", e, update)
                await update.message.reply_text(
                    "Не удалось подключиться к серверу. Проверьте интернет и попробуйте снова."
                )

            except Exception as e:
                log_error("change_mode", e, update)
                await update.message.reply_text("Не удалось получить ответ.")
        else:
            emoji = RELIGION_EMOJI[user_text]
            await update.message.reply_text(
                f"Выбран режим: {emoji} {user_text}\nТеперь задайте вопрос."
            )
        return

    if user_text == "Сравнить ответы":
        if not state["last_question"]:
            await update.message.reply_text("Сначала задайте вопрос.")
            return

        try:
            state["stats"]["compare_count"] += 1
            db_increment_compare_count(user_id)

            msg = await update.message.reply_text("Думаю... 🤖")
            answer = ask_compare(state["last_question"])
            await msg.delete()
            await update.message.reply_text(answer)

        except requests.exceptions.Timeout as e:
            log_error("compare_timeout", e, update)
            await update.message.reply_text(
                "Сравнение заняло слишком много времени. Попробуйте ещё раз через несколько секунд."
            )

        except requests.exceptions.SSLError as e:
            log_error("compare_ssl", e, update)
            await update.message.reply_text(
                "Возникла проблема с защищённым соединением при сравнении ответов. Попробуйте позже."
            )

        except requests.exceptions.ConnectionError as e:
            log_error("compare_connection", e, update)
            await update.message.reply_text(
                "Не удалось подключиться к серверу для сравнения ответов. Проверьте интернет."
            )

        except Exception as e:
            log_error("compare", e, update)
            await update.message.reply_text("Ошибка сравнения.")
        return

    if is_controversial_question(user_text):
        state["last_question"] = user_text
        add_question_to_history(state, user_text)
        state["stats"]["questions_count"] += 1

        db_set_last_question(user_id, user_text)
        db_add_question_history(user_id, user_text)
        db_increment_questions_count(user_id)

        await update.message.reply_text(
            "Этот вопрос может трактоваться по-разному в зависимости от религиозной традиции. "
            "Лучше рассматривать его в контексте конкретного учения."
        )
        return

    # Обычный вопрос
    state["last_question"] = user_text
    add_question_to_history(state, user_text)
    state["stats"]["questions_count"] += 1

    db_set_last_question(user_id, user_text)
    db_add_question_history(user_id, user_text)
    db_increment_questions_count(user_id)

    mode = state["selected_religion"]
    if mode:
        state["stats"]["mode_usage"][mode] += 1
        db_increment_mode_usage(user_id, mode)
    else:
        state["stats"]["mode_usage"]["Общий"] += 1
        db_increment_mode_usage(user_id, "Общий")

    try:
        msg = await update.message.reply_text("Думаю... 🤖")
        answer = ask_ai(user_text, mode)
        await msg.delete()
        await update.message.reply_text(format_answer(mode, answer))

    except requests.exceptions.Timeout as e:
        log_error("handle_message_timeout", e, update)
        await update.message.reply_text(
            "Сервер отвечает слишком долго. Попробуйте ещё раз через несколько секунд."
        )

    except requests.exceptions.SSLError as e:
        log_error("handle_message_ssl", e, update)
        await update.message.reply_text(
            "Возникла проблема с защищённым соединением. Попробуйте ещё раз чуть позже."
        )

    except requests.exceptions.ConnectionError as e:
        log_error("handle_message_connection", e, update)
        await update.message.reply_text(
            "Не удалось подключиться к серверу. Проверьте интернет и попробуйте снова."
        )

    except Exception as e:
        log_error("handle_message", e, update)
        await update.message.reply_text("Произошла временная ошибка.")


# =========================
# Глобальный error handler
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    try:
        log_error("telegram_global", context.error, update)
    except Exception:
        logging.error("Глобальная ошибка: %s", str(context.error))


# =========================
# Запуск
# =========================
def main():
    if not BOT_TOKEN:
        print("Ошибка: BOT_TOKEN не найден")
        return

    if not OPENROUTER_API_KEY:
        print("Ошибка: OPENROUTER_API_KEY не найден")
        return

    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .pool_timeout(30)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("about", about_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    print("Бот запущен...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log_error("startup", e)
        print("Ошибка запуска:", e)