import asyncio
import os
import sys

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from hydrogram.types.user_and_chats.chat import Chat
from hydrogram import raw, enums

_orig_parse_chat = Chat._parse_chat

@staticmethod
def _safe_parse_chat(client, chat):
    if isinstance(chat, (raw.types.ChatForbidden, raw.types.ChannelForbidden)):
        return Chat(id=-getattr(chat, "id", 0), type=enums.ChatType.GROUP, client=client)
    return _orig_parse_chat(client, chat)

Chat._parse_chat = _safe_parse_chat

from clients import app
from handlers import register_all


async def main():
    for old_file in ["session.session", "session.session-journal"]:
        if os.path.isfile(old_file):
            try:
                os.remove(old_file)
                print(f"[+] Cleaned up obsolete {old_file}")
            except Exception:
                pass

    @app.on_message(group=-10)
    async def _log_all(client, msg):
        chat_name = getattr(msg.chat, "title", None) or getattr(msg.chat, "id", "unknown")
        user_name = getattr(msg.from_user, "first_name", None) or getattr(msg.from_user, "id", "unknown")
        print(f"[RECV] Chat: {chat_name} ({msg.chat.type}) | From: {user_name} | Text: {msg.text or msg.caption!r}", flush=True)

    register_all(app)
    await app.start()
    me = await app.get_me()
    print(f"\n[+] Telegram Bot @{me.username} ({me.first_name}) is active and listening for commands & inline queries!", flush=True)


    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        if getattr(app, "is_connected", False):
            loop.run_until_complete(app.stop())
        print("\n[-] Bot stopped.")

