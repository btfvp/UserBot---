import asyncio
import time
from datetime import datetime
from io import BytesIO
from PIL import Image
from hydrogram import Client, filters
from hydrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from clients import ataraxis
from config import user_id
from utils.quote import generate_quote_image, generate_quote_animation

_AVATAR_CACHE: dict[int, tuple[bytes, float]] = {}
_CACHE_TTL = 900


async def _get_cached_or_download_avatar(client: Client, entity_id: int) -> bytes | None:
    now = time.time()
    if entity_id in _AVATAR_CACHE:
        cached_bytes, cached_at = _AVATAR_CACHE[entity_id]
        if now - cached_at < _CACHE_TTL:
            return cached_bytes

    avatar_bytes = None
    try:
        async for photo in client.get_chat_photos(entity_id, limit=1):
            avatar_file = await client.download_media(photo.file_id, in_memory=True)
            avatar_bytes = avatar_file.getvalue()
            _AVATAR_CACHE[entity_id] = (avatar_bytes, now)
            break
    except Exception:
        pass
    return avatar_bytes


def _is_quote_trigger(_, __, m: Message) -> bool:
    text = (m.text or m.caption or "").strip()
    if not text:
        return False
    parts = text.split()
    first_word = parts[0].lower() if parts else ""
    if "@" in first_word:
        first_word = first_word.split("@")[0]

    prefixed_cmds = {
        p + cmd
        for p in ["/", "!", "."]
        for cmd in ["ц", "цитата", "quote", "гиф", "gif", "г"]
    }
    if first_word in prefixed_cmds:
        cmd_clean = first_word.lstrip("/!.")
        m.command = [cmd_clean] + parts[1:]
        return True

    if m.reply_to_message and first_word in ["ц", "цитата", "quote", "гиф", "gif", "г"]:
        m.command = [first_word] + parts[1:]
        return True

    return False


def register(app: Client):
    @app.on_message(filters.create(_is_quote_trigger))
    async def quote_handler(client: Client, message: Message):
        try:
            print(f"[QUOTE TRIGGERED] Chat: {message.chat.id}, User: {message.from_user.id if message.from_user else 'None'}, Text: {message.text!r}", flush=True)
            target = message.reply_to_message
            if not target:
                print(f"[QUOTE] No reply_to_message in message {message.id}!", flush=True)
                await message.reply("⚠️ Ответьте (Reply) на сообщение, чтобы создать цитату.")
                return

            cmd = (message.command[0] if message.command else "").lower()
            args = [a.lower() for a in message.command[1:]] if message.command else []
            is_gif_cmd = cmd in ["гиф", "gif", "г"] or any(
                a in ["гиф", "gif", "-g", "--gif"] for a in args
            )

            text = (target.text or target.caption or "").strip()
            if not text:
                cmd_text = ""
                if message.text:
                    parts = message.text.split(maxsplit=1)
                    if len(parts) > 1:
                        possible_text = parts[1].strip()
                        if possible_text.lower() not in ["гиф", "gif", "-g", "--gif"]:
                            cmd_text = possible_text
                if cmd_text:
                    text = cmd_text
                else:
                    await message.reply("⚠️ В сообщении нет текста для цитаты.")
                    return

            author = None
            username = None
            avatar_bytes = None
            avatar_seed = None
            target_user_id = None
            timestamp_source = target.date

            if target.forward_sender_name:
                author = target.forward_sender_name
                username = None
                avatar_bytes = None
                avatar_seed = author
                if target.forward_date:
                    timestamp_source = target.forward_date

            elif target.forward_from:
                user = target.forward_from
                target_user_id = user.id
                author = user.first_name or "Unknown"
                if user.last_name:
                    author = f"{author} {user.last_name}"
                username = f"@{user.username}" if user.username else None
                avatar_seed = user.id
                if target.forward_date:
                    timestamp_source = target.forward_date

                avatar_bytes = await _get_cached_or_download_avatar(client, user.id)

            elif target.forward_from_chat:
                chat = target.forward_from_chat
                author = chat.title or "Unknown"
                username = f"@{chat.username}" if chat.username else None
                avatar_seed = chat.id
                if target.forward_date:
                    timestamp_source = target.forward_date

                avatar_bytes = await _get_cached_or_download_avatar(client, chat.id)

            elif target.sender_chat:
                chat = target.sender_chat
                author = chat.title or "Unknown"
                username = f"@{chat.username}" if chat.username else None
                avatar_seed = chat.id
                if target.date:
                    timestamp_source = target.date

                avatar_bytes = await _get_cached_or_download_avatar(client, chat.id)

            else:
                user = target.from_user
                if not user:
                    author = "Unknown"
                else:
                    target_user_id = user.id
                    author = user.first_name or "Unknown"
                    if user.last_name:
                        author = f"{author} {user.last_name}"
                    username = f"@{user.username}" if user.username else None
                    avatar_seed = user.id

                    avatar_bytes = await _get_cached_or_download_avatar(client, user.id)

            cover_bytes = None
            try:
                np = await asyncio.wait_for(ataraxis.get_my_now_playing(), timeout=0.5)
                if np.isPlaying and np.track and np.track.coverUrl:
                    cover_bytes = await asyncio.wait_for(
                        ataraxis.download_cover(np.track.coverUrl), timeout=1.0
                    )
            except Exception:
                pass

            media_obj = None
            is_known_animated = False

            if target.animation:
                media_obj = target.animation
                is_known_animated = True
            elif target.video:
                media_obj = target.video
                is_known_animated = True
            elif target.video_note:
                media_obj = target.video_note
                is_known_animated = True
            elif target.document:
                media_obj = target.document
                mime = (target.document.mime_type or "").lower()
                fname = (target.document.file_name or "").lower()
                if mime.startswith(("image/gif", "video/")) or fname.endswith(
                    (".gif", ".mp4", ".mov", ".webm", ".webp")
                ):
                    is_known_animated = True
            elif target.photo:
                media_obj = target.photo
                is_known_animated = False
            elif target.sticker and (target.sticker.is_animated or target.sticker.is_video):
                media_obj = target.sticker
                is_known_animated = True

            attachment_bytes = None
            if media_obj:
                try:
                    att_file = await client.download_media(media_obj, in_memory=True)
                    if att_file:
                        attachment_bytes = att_file.getvalue()
                except Exception as dl_err:
                    print(f"[WARN] Failed to download media: {dl_err}")

            is_attachment_animated = is_known_animated
            if attachment_bytes:
                if attachment_bytes.startswith((b"GIF87a", b"GIF89a")):
                    is_attachment_animated = True
                elif len(attachment_bytes) >= 12 and attachment_bytes[4:8] == b"ftyp":
                    is_attachment_animated = True
                elif attachment_bytes.startswith(b"\x1a\x45\xdf\xa3"):
                    is_attachment_animated = True
                elif not is_attachment_animated:
                    try:
                        test_im = Image.open(BytesIO(attachment_bytes))
                        if getattr(test_im, "is_animated", False) and getattr(test_im, "n_frames", 1) > 1:
                            is_attachment_animated = True
                    except Exception:
                        pass

            timestamp = (timestamp_source or datetime.now()).strftime("%d.%m.%Y %H:%M:%S")

            should_animate = is_gif_cmd or is_attachment_animated

            if should_animate:
                try:
                    anim_buffer = await asyncio.to_thread(
                        generate_quote_animation,
                        quote=text,
                        author=author,
                        username=username,
                        avatar_bytes=avatar_bytes,
                        background_bytes=cover_bytes,
                        attachment_bytes=attachment_bytes,
                        is_attachment_animated=is_attachment_animated,
                        timestamp=timestamp,
                        avatar_seed=avatar_seed,
                        user_id=target_user_id,
                    )

                    thumb = getattr(anim_buffer, "thumb", None)
                    duration = getattr(anim_buffer, "duration", 2)

                    try:
                        anim_buffer.seek(0)
                        if thumb:
                            thumb.seek(0)
                        await message.reply_animation(
                            animation=anim_buffer,
                            thumb=thumb,
                            duration=duration,
                            width=1280,
                            height=720,
                        )
                        return
                    except Exception as anim_err:
                        print(f"[WARN] reply_animation failed: {anim_err}, trying reply_video...")

                    try:
                        anim_buffer.seek(0)
                        if thumb:
                            thumb.seek(0)
                        await message.reply_video(
                            video=anim_buffer,
                            thumb=thumb,
                            duration=duration,
                            width=1280,
                            height=720,
                            supports_streaming=True,
                        )
                        return
                    except Exception as vid_err:
                        print(f"[WARN] reply_video failed: {vid_err}, trying reply_document...")

                    try:
                        anim_buffer.seek(0)
                        if thumb:
                            thumb.seek(0)
                        await message.reply_document(
                            document=anim_buffer,
                            thumb=thumb,
                        )
                        return
                    except Exception as doc_err:
                        print(f"[WARN] reply_document failed: {doc_err}")

                except Exception as gen_err:
                    print(f"[ERROR in quote animation]: {gen_err}")

            image = await asyncio.to_thread(
                generate_quote_image,
                quote=text,
                author=author,
                username=username,
                avatar_bytes=avatar_bytes,
                background_bytes=cover_bytes,
                attachment_bytes=attachment_bytes,
                timestamp=timestamp,
                avatar_seed=avatar_seed,
                user_id=target_user_id,
            )

            await message.reply_photo(photo=image)
        except Exception as e:
            print(f"[ERROR in quote_handler]: {e}")
            await message.reply(f"❌ Ошибка при создании цитаты: {e}")


