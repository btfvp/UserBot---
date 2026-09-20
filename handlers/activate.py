from hydrogram import Client
from hydrogram.types import Message
from config import user_id
from hydrogram import filters

def register(app: Client):
    @app.on_message(filters.command(["check", "ping", "p"], prefixes=["!", ".", "/"]) & (filters.user(user_id) | filters.me))
    async def activate_handler(client: Client, message: Message):
        await message.reply_text("**PONG!**")
