import asyncio
import time
import hashlib
from datetime import datetime
from io import BytesIO

from hydrogram import Client, raw, types
from hydrogram.types import (
    InlineQuery,
    InlineQueryResultArticle,
    InlineQueryResultCachedPhoto,
    InlineQueryResultCachedAnimation,
    InputTextMessageContent,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from utils.quote import (
    generate_quote_image,
    generate_quote_animation,
    get_blur_percent,
    get_blur_radius,
    DEFAULT_BLUR_PERCENT,
)
from handlers.help import get_help_text

_AVATAR_CACHE: dict[int, tuple[bytes | None, float]] = {}
_CACHE_TTL = 900

_INLINE_MEDIA_CACHE: dict[str, tuple[str | None, str | None, float]] = {}


async def _get_user_avatar(client: Client, user_id: int) -> bytes | None:
    now = time.time()
    if user_id in _AVATAR_CACHE:
        cached_bytes, cached_at = _AVATAR_CACHE[user_id]
        if now - cached_at < _CACHE_TTL:
            return cached_bytes

    avatar_bytes = None
    try:
        async for photo in client.get_chat_photos(user_id, limit=1):
            att = await client.download_media(photo.file_id, in_memory=True)
            if att:
                avatar_bytes = att.getvalue()
            break
    except Exception:
        pass

    _AVATAR_CACHE[user_id] = (avatar_bytes, now)
    return avatar_bytes


async def _upload_photo_file_id(client: Client, photo_buf: BytesIO) -> str | None:
    try:
        photo_buf.seek(0)
        file = await client.save_file(photo_buf)
        res = await client.invoke(
            raw.functions.messages.UploadMedia(
                peer=await client.resolve_peer("me"),
                media=raw.types.InputMediaUploadedPhoto(file=file),
            )
        )
        parsed = types.Photo._parse(client, res.photo)
        return parsed.file_id if parsed else None
    except Exception as e:
        print(f"[ERROR uploading inline photo]: {e}")
        return None


async def _upload_animation_file_id(
    client: Client, anim_buf: BytesIO, thumb_buf: BytesIO | None = None
) -> str | None:
    try:
        anim_buf.seek(0)
        file = await client.save_file(anim_buf)
        thumb = await client.save_file(thumb_buf) if thumb_buf else None
        res = await client.invoke(
            raw.functions.messages.UploadMedia(
                peer=await client.resolve_peer("me"),
                media=raw.types.InputMediaUploadedDocument(
                    mime_type="video/mp4",
                    file=file,
                    thumb=thumb,
                    attributes=[
                        raw.types.DocumentAttributeVideo(
                            supports_streaming=True,
                            duration=2,
                            w=1280,
                            h=720,
                        ),
                        raw.types.DocumentAttributeFilename(file_name="quote.mp4"),
                        raw.types.DocumentAttributeAnimated(),
                    ],
                ),
            )
        )
        parsed = types.Animation._parse(client, res.document)
        return parsed.file_id if parsed else None
    except Exception as e:
        print(f"[ERROR uploading inline animation]: {e}")
        return None


def register(app: Client):
    @app.on_inline_query()
    async def inline_quote_handler(client: Client, inline_query: InlineQuery):
        raw_query = (inline_query.query or "").strip()
        user = inline_query.from_user
        lower_query = raw_query.lower()

        if not raw_query:
            help_text = get_help_text()
            cur_p = get_blur_percent()
            cur_r = get_blur_radius()
            def_r = int(round(DEFAULT_BLUR_PERCENT * 0.4))
            blur_text = f"ℹ️ **Блюр карточки:** **{cur_p}%** ({cur_r} px) | Дефолт: **{DEFAULT_BLUR_PERCENT}%** ({def_r} px)"

            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="quote_tip",
                        title="💬 Создать цитату (Фото)",
                        description="Напишите: @tsitatbot <текст цитаты>",
                        input_message_content=InputTextMessageContent(
                            "💡 Чтобы создать фото-цитату, напишите:\n`@tsitatbot текст цитаты`"
                        ),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("✍️ Попробовать ввести цитату", switch_inline_query_current_chat="Моя первая цитата")]
                        ]),
                    ),
                    InlineQueryResultArticle(
                        id="gif_tip",
                        title="🎬 Создать анимированную цитату (GIF)",
                        description="Напишите: @tsitatbot гиф <текст цитаты>",
                        input_message_content=InputTextMessageContent(
                            "💡 Чтобы создать живую анимированную гифку, напишите:\n`@tsitatbot гиф текст цитаты`"
                        ),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🎬 Попробовать создать гифку", switch_inline_query_current_chat="гиф Живая цитата")]
                        ]),
                    ),
                    InlineQueryResultArticle(
                        id="help_cmd",
                        title="ℹ️ Справка по всем командам (/help)",
                        description="Показать список доступных команд и возможностей",
                        input_message_content=InputTextMessageContent(help_text),
                        reply_markup=InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("✍️ Цитата", switch_inline_query_current_chat=""),
                                InlineKeyboardButton("🎬 Гифка", switch_inline_query_current_chat="гиф "),
                            ]
                        ]),
                    ),
                    InlineQueryResultArticle(
                        id="blur_status",
                        title="⚙️ Статус блюра карточки (/б, /бс)",
                        description=f"Текущий блюр: {cur_p}% ({cur_r} px)",
                        input_message_content=InputTextMessageContent(blur_text),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔍 Проверить блюр", switch_inline_query_current_chat="б")]
                        ]),
                    ),
                    InlineQueryResultArticle(
                        id="bg_info",
                        title="🖼 Смена фона и аватарки (/ф)",
                        description="Команда /ф ответом на фото (только админ)",
                        input_message_content=InputTextMessageContent(
                            "🖼 **Смена фона:**\nОтправьте боту изображение или ответьте на фото/гифку командой `/ф`.\n*(Доступно администратору)*"
                        ),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🤖 Открыть диалог с ботом", url="https://t.me/tsitatbot")]
                        ]),
                    ),
                ],
                cache_time=5,
                is_personal=True,
                switch_pm_text="📖 Все команды и настройки",
                switch_pm_parameter="help",
            )
            return

        if lower_query in ["/help", "help", "справка", "помощь"]:
            help_text = get_help_text()
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="help_result",
                        title="ℹ️ Справка бота (/help)",
                        description="Отправить текст справки в чат",
                        input_message_content=InputTextMessageContent(help_text),
                        reply_markup=InlineKeyboardMarkup([
                            [
                                InlineKeyboardButton("✍️ Цитата", switch_inline_query_current_chat=""),
                                InlineKeyboardButton("🎬 Гифка", switch_inline_query_current_chat="гиф "),
                            ]
                        ]),
                    )
                ],
                cache_time=10,
                is_personal=True,
                switch_pm_text="📖 Открыть бота",
                switch_pm_parameter="help",
            )
            return

        if lower_query in ["/start", "start", "старт"]:
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="start_result",
                        title="👋 Приветствие (/start)",
                        description="Отправить стартовое сообщение",
                        input_message_content=InputTextMessageContent("Привет.\nДля команд пиши /help"),
                    )
                ],
                cache_time=10,
                is_personal=True,
            )
            return

        if lower_query in ["/б", "б", "/blur", "blur", "блюр", "/блюр"]:
            cur_p = get_blur_percent()
            cur_r = get_blur_radius()
            def_r = int(round(DEFAULT_BLUR_PERCENT * 0.4))
            blur_text = (
                f"ℹ️ **Блюр карточки:** **{cur_p}%** ({cur_r} px)\n"
                f"• По умолчанию: **{DEFAULT_BLUR_PERCENT}%** ({def_r} px)\n\n"
                f"💡 Чтобы изменить блюр (админ):\n"
                f"Напишите в чате с ботом: `/б <проценты>` (например `/б 40` или `/б 0`)\n"
                f"Для сброса: `/бс`"
            )
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="blur_info",
                        title=f"⚙️ Текущий блюр: {cur_p}% ({cur_r} px)",
                        description=f"Дефолт: {DEFAULT_BLUR_PERCENT}% ({def_r} px). Настройка: /б <проценты>",
                        input_message_content=InputTextMessageContent(blur_text),
                    )
                ],
                cache_time=5,
                is_personal=True,
            )
            return

        if lower_query in ["/бс", "бс", "/reset", "reset", "сброс", "/сброс"]:
            def_r = int(round(DEFAULT_BLUR_PERCENT * 0.4))
            reset_text = (
                f"🔄 **Сброс блюра (/бс)**\n"
                f"Сбрасывает размытие карточки до стандартного значения: **{DEFAULT_BLUR_PERCENT}%** ({def_r} px).\n\n"
                f"💡 Выполняется администратором в чате командой `/бс`."
            )
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="blur_reset_info",
                        title="🔄 Сброс блюра (/бс)",
                        description=f"Сбросить размытие до {DEFAULT_BLUR_PERCENT}%",
                        input_message_content=InputTextMessageContent(reset_text),
                    )
                ],
                cache_time=5,
                is_personal=True,
            )
            return

        if lower_query in ["/ф", "ф", "фон", "/фон", "background", "/background"]:
            bg_text = (
                "🖼 **Смена фона и аватара карточки (/ф)**\n\n"
                "1. Отправьте боту изображение (или GIF).\n"
                "2. Ответьте на него командой `/ф`.\n"
                "*(Доступно только администратору)*"
            )
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="bg_info_result",
                        title="🖼 Смена фона (/ф)",
                        description="Как сменить фон и аватарку карточки",
                        input_message_content=InputTextMessageContent(bg_text),
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🤖 Открыть бота для отправки фото", url="https://t.me/tsitatbot")]
                        ]),
                    )
                ],
                cache_time=10,
                is_personal=True,
            )
            return

        if lower_query in ["/helpp", "helpp"]:
            helpp_text = (
                "✏️ **Настройка справки (/helpp)**\n\n"
                "Команда позволяет администратору изменить текст, который бот отправляет по команде `/help`.\n\n"
                "Использование:\n"
                "• `/helpp <новый текст>`\n"
                "• или ответьте командой `/helpp` на сообщение с текстом.\n"
                "*(Доступно только администратору)*"
            )
            await inline_query.answer(
                results=[
                    InlineQueryResultArticle(
                        id="helpp_info_result",
                        title="✏️ Настройка справки (/helpp)",
                        description="Изменение текста /help (для администратора)",
                        input_message_content=InputTextMessageContent(helpp_text),
                    )
                ],
                cache_time=10,
                is_personal=True,
            )
            return

        is_gif_forced = False
        is_photo_forced = False
        quote_text = raw_query

        gif_prefixes = ["/гиф ", "!гиф ", "гиф ", "/gif ", "!gif ", "gif ", "/г ", "!г ", "г "]
        for pfx in gif_prefixes:
            if lower_query.startswith(pfx):
                quote_text = raw_query[len(pfx):].strip()
                is_gif_forced = True
                break

        if not is_gif_forced:
            photo_prefixes = ["/цитата ", "!цитата ", "цитата ", "/quote ", "!quote ", "quote ", "/ц ", "!ц ", "ц "]
            for pfx in photo_prefixes:
                if lower_query.startswith(pfx):
                    quote_text = raw_query[len(pfx):].strip()
                    is_photo_forced = True
                    break

        if not quote_text:
            quote_text = raw_query

        now = time.time()
        user_id = user.id if user else 0
        cache_key = hashlib.md5(f"{user_id}_{quote_text}".encode()).hexdigest()

        cached_photo_id, cached_anim_id = None, None
        if cache_key in _INLINE_MEDIA_CACHE:
            p_id, a_id, ts = _INLINE_MEDIA_CACHE[cache_key]
            if now - ts < 600:
                cached_photo_id, cached_anim_id = p_id, a_id

        author = "Unknown"
        username = None
        if user:
            author = user.first_name or "Unknown"
            if user.last_name:
                author = f"{author} {user.last_name}"
            username = f"@{user.username}" if user.username else None

        avatar_bytes = await _get_user_avatar(client, user_id) if user else None
        timestamp = datetime.now().strftime("%d.%m.%Y %H:%M:%S")

        photo_file_id = cached_photo_id
        anim_file_id = cached_anim_id

        if not is_gif_forced and not photo_file_id:
            try:
                photo_buf = await asyncio.to_thread(
                    generate_quote_image,
                    quote=quote_text,
                    author=author,
                    username=username,
                    avatar_bytes=avatar_bytes,
                    timestamp=timestamp,
                    avatar_seed=user_id,
                    user_id=user_id,
                )
                photo_file_id = await _upload_photo_file_id(client, photo_buf)
            except Exception as e:
                print(f"[ERROR in inline photo generation]: {e}")

        if not is_photo_forced and not anim_file_id:
            try:
                anim_buf = await asyncio.to_thread(
                    generate_quote_animation,
                    quote=quote_text,
                    author=author,
                    username=username,
                    avatar_bytes=avatar_bytes,
                    timestamp=timestamp,
                    avatar_seed=user_id,
                    user_id=user_id,
                )
                thumb_buf = getattr(anim_buf, "thumb", None)
                anim_file_id = await _upload_animation_file_id(client, anim_buf, thumb_buf)
            except Exception as e:
                print(f"[ERROR in inline animation generation]: {e}")

        _INLINE_MEDIA_CACHE[cache_key] = (photo_file_id, anim_file_id, now)

        results = []
        if is_gif_forced:
            if anim_file_id:
                results.append(
                    InlineQueryResultCachedAnimation(
                        animation_file_id=anim_file_id,
                        id="quote_anim",
                        title="🎬 Анимированная цитата (GIF)",
                        description=f"Отправить гифку: «{quote_text[:40]}»",
                    )
                )
            if photo_file_id:
                results.append(
                    InlineQueryResultCachedPhoto(
                        photo_file_id=photo_file_id,
                        id="quote_photo",
                        title="🖼 Статичная цитата (Фото)",
                        description=f"Отправить фото: «{quote_text[:40]}»",
                    )
                )
        else:
            if photo_file_id:
                results.append(
                    InlineQueryResultCachedPhoto(
                        photo_file_id=photo_file_id,
                        id="quote_photo",
                        title="🖼 Цитата (Фото)",
                        description=f"Отправить фото: «{quote_text[:40]}»",
                    )
                )
            if anim_file_id:
                results.append(
                    InlineQueryResultCachedAnimation(
                        animation_file_id=anim_file_id,
                        id="quote_anim",
                        title="🎬 Анимированная цитата (GIF)",
                        description=f"Отправить гифку: «{quote_text[:40]}»",
                    )
                )

        if not results:
            results.append(
                InlineQueryResultArticle(
                    title="❌ Не удалось создать цитату",
                    description="Попробуйте изменить текст",
                    input_message_content=InputTextMessageContent("Ошибка при создании цитаты."),
                )
            )

        await inline_query.answer(results=results, cache_time=300, is_personal=True)

