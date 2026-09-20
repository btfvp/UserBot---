import os
import json
from hydrogram import Client, filters
from hydrogram.types import Message
from config import admin_id

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
settings_path = os.path.join(BASE_DIR, "settings.json")

DEFAULT_HELP_TEXT = """Команды цитирования:
Ответьте (Reply) на любое сообщение:
• /цитата (или /ц, /quote) — создать цитату
• /гиф (или /gif, /г) — создать анимированную гиф-цитату

Настройки (только для админа):
• /ф — установить фон (ответом на фото/гиф)
• /б <проценты> — настроить блюр (например, /б 50 или /б 0)
• /бс — сбросить блюр к дефолтному (25%)
• /helpp <текст> — настроить текст этой справки

Инлайн-режим:
Напишите в любом чате:
@имя_бота <текст цитаты>"""


def get_help_text() -> str:
    try:
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("help_text", DEFAULT_HELP_TEXT)
    except Exception:
        pass
    return DEFAULT_HELP_TEXT


def set_help_text(text: str) -> None:
    data = {}
    try:
        if os.path.isfile(settings_path):
            with open(settings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
    except Exception:
        data = {}
    data["help_text"] = text
    try:
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERROR saving help text]: {e}")


def register(app: Client):
    @app.on_message(filters.command("start", prefixes=["/", "!", "."]))
    async def start_handler(client: Client, message: Message):
        await message.reply("Привет.\nДля команд пиши /help")

    @app.on_message(filters.command("help", prefixes=["/", "!", "."]))
    async def help_handler(client: Client, message: Message):
        text = get_help_text()
        await message.reply(text)

    @app.on_message(filters.command("helpp", prefixes=["/", "!", "."]) & filters.user(admin_id))
    async def set_help_handler(client: Client, message: Message):
        new_text = ""
        if message.reply_to_message and (message.reply_to_message.text or message.reply_to_message.caption):
            new_text = (message.reply_to_message.text or message.reply_to_message.caption).strip()
        elif message.text:
            parts = message.text.split(maxsplit=1)
            if len(parts) > 1:
                new_text = parts[1].strip()

        if not new_text:
            await message.reply(
                "⚠️ Укажите текст после команды `/helpp <текст>` или ответьте командой `/helpp` на сообщение с текстом."
            )
            return

        set_help_text(new_text)
        await message.reply("✅ Текст команды /help успешно обновлен!")
