import os
import asyncio
from io import BytesIO
from PIL import Image
from hydrogram import Client, filters
from hydrogram.enums import ChatType
from hydrogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)

from config import admin_id
from utils.quote import (
    background_path,
    reload_background,
    save_user_background,
    reset_user_background,
    get_user_background_path,
    _extract_attachment_frames,
    get_blur_percent,
    get_blur_radius,
    set_blur_percent,
    reset_blur_percent,
    DEFAULT_BLUR_PERCENT,
)


def _has_media(msg: Message) -> bool:
    if not msg:
        return False
    if msg.photo or msg.animation or msg.video:
        return True
    if msg.document and msg.document.mime_type and (
        msg.document.mime_type.startswith("image/")
        or msg.document.mime_type.startswith("video/")
    ):
        return True
    return False


async def _extract_image_from_message(client: Client, target_msg: Message) -> Image.Image | None:
    try:
        media_obj = (
            target_msg.photo
            or target_msg.animation
            or target_msg.video
            or target_msg.document
        )
        downloaded = await client.download_media(media_obj.file_id, in_memory=True)
        if not downloaded:
            return None

        img_bytes = downloaded.getvalue()

        is_anim = bool(
            target_msg.animation
            or target_msg.video
            or (
                target_msg.document
                and (target_msg.document.mime_type or "").startswith(
                    ("image/gif", "video/")
                )
            )
        )

        frames = _extract_attachment_frames(img_bytes, is_animated=is_anim, max_frames=1)
        if not frames:
            return None

        return frames[0]
    except Exception as e:
        print(f"[ERROR in _extract_image_from_message]: {e}")
        return None


def _get_settings_markup() -> InlineKeyboardMarkup:
    cur_p = get_blur_percent()
    def _mark(p: int) -> str:
        return f"• {p}% •" if cur_p == p else f"{p}%"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(_mark(0), callback_data="blur_set_0"),
            InlineKeyboardButton(_mark(25) + " (деф)", callback_data="blur_set_25"),
            InlineKeyboardButton(_mark(50), callback_data="blur_set_50"),
        ],
        [
            InlineKeyboardButton(_mark(75), callback_data="blur_set_75"),
            InlineKeyboardButton(_mark(100), callback_data="blur_set_100"),
            InlineKeyboardButton("🔄 Сбросить", callback_data="blur_reset"),
        ],
        [
            InlineKeyboardButton("💬 Проверить цитату", switch_inline_query_current_chat="Тестовая цитата")
        ]
    ])


def register(app: Client):
    @app.on_message(
        filters.private
        & (filters.photo | filters.animation | filters.video | filters.document)
    )
    async def direct_photo_in_pm_handler(client: Client, message: Message):
        if not _has_media(message):
            return
        user_id = message.from_user.id if message.from_user else None
        if not user_id:
            return

        img = await _extract_image_from_message(client, message)
        if img:
            save_user_background(user_id, img)
            await message.reply(
                "✅ **Ваше личное фото для цитат успешно сохранено!**\n"
                "Теперь на всех ваших цитатах будет это фоновое изображение.\n\n"
                "💡 Чтобы вернуть стандартный общий фон, отправьте: `/фс`"
            )

    @app.on_message(
        filters.command(["ф", "f", "фон", "bg", "ава", "ava"], prefixes=["/", "!", "."])
    )
    async def set_background_handler(client: Client, message: Message):
        try:
            target_msg = None
            is_private = (message.chat.type == ChatType.PRIVATE)
            user_id = message.from_user.id if message.from_user else None

            if _has_media(message):
                target_msg = message

            elif message.reply_to_message and _has_media(message.reply_to_message):
                target_msg = message.reply_to_message

            else:
                try:
                    async for prev_msg in client.get_chat_history(message.chat.id, limit=6):
                        if prev_msg.id != message.id and _has_media(prev_msg):
                            target_msg = prev_msg
                            break
                except Exception:
                    pass

            if not target_msg:
                try:
                    chat = await client.get_chat(message.chat.id)
                    if chat.pinned_message and _has_media(chat.pinned_message):
                        target_msg = chat.pinned_message
                except Exception:
                    pass

            if not target_msg:
                if is_private:
                    await message.reply(
                        "⚠️ **Фото не найдено.**\nОтправьте боту изображение/гифку или ответьте командой `/ф` на фотографию."
                    )
                else:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                return

            img = await _extract_image_from_message(client, target_msg)

            if img and user_id:
                save_user_background(user_id, img)
                print(f"[+] User {user_id} personal background updated ({img.width}x{img.height})")

                if is_private:
                    await message.reply(
                        "✅ **Ваше личное фото для цитат успешно сохранено!**\n"
                        "Теперь на всех ваших цитатах будет это фоновое изображение.\n\n"
                        "💡 Чтобы вернуться к стандартному фону, отправьте: `/фс`"
                    )
                else:
                    try:
                        if message != target_msg:
                            await message.delete()
                    except Exception:
                        pass
            else:
                if is_private:
                    await message.reply("❌ Не удалось обработать изображение для фона.")

        except Exception as e:
            print(f"[ERROR in set_background]: {e}")

    @app.on_message(
        filters.command(["фс", "фсброс", "resetbg", "bgreset"], prefixes=["/", "!", "."])
    )
    async def reset_user_bg_handler(client: Client, message: Message):
        user_id = message.from_user.id if message.from_user else None
        is_private = (message.chat.type == ChatType.PRIVATE)
        if user_id:
            reset_user_background(user_id)
        if is_private:
            await message.reply("🔄 **Ваше персональное фото сброшено.**\nТеперь для ваших цитат используется стандартный общий фон.")
        else:
            try:
                await message.delete()
            except Exception:
                pass

    @app.on_message(
        filters.command(["фдефолт", "defbg", "defaultbg"], prefixes=["/", "!", "."])
        & filters.user(admin_id)
    )
    async def set_default_background_handler(client: Client, message: Message):
        try:
            target_msg = None
            if _has_media(message):
                target_msg = message
            elif message.reply_to_message and _has_media(message.reply_to_message):
                target_msg = message.reply_to_message

            if not target_msg:
                await message.reply("⚠️ Ответьте на фото командой `/фдефолт`, чтобы изменить стандартный фон для всех.")
                return

            img = await _extract_image_from_message(client, target_msg)
            if img:
                img.save(background_path, format="PNG")
                reload_background()
                await message.reply("✅ **Глобальный стандартный фон для всех пользователей успешно обновлен!**")
        except Exception as e:
            print(f"[ERROR in set_default_background]: {e}")

    @app.on_message(
        filters.command(["б", "blur", "блюр"], prefixes=["/", "!", "."])
        & filters.user(admin_id)
    )
    async def set_blur_handler(client: Client, message: Message):
        try:
            is_private = (message.chat.type == ChatType.PRIVATE)
            cmd_args = message.command[1:] if message.command else []

            if not cmd_args:
                cur_p = get_blur_percent()
                cur_r = get_blur_radius()
                def_r = int(round(DEFAULT_BLUR_PERCENT * 0.4))
                resp_text = (
                    f"ℹ️ **Блюр карточки:** **{cur_p}%** ({cur_r} px) | Дефолт: **{DEFAULT_BLUR_PERCENT}%** ({def_r} px)\n"
                    f"Чтобы изменить: `/б <проценты>` (например, `/б 40` или `/б 0`)"
                )
                if is_private:
                    await message.reply(resp_text, reply_markup=_get_settings_markup())
                else:
                    resp = await message.reply(resp_text)
                    await asyncio.sleep(5)
                    try:
                        await resp.delete()
                        await message.delete()
                    except Exception:
                        pass
                return

            raw_val = cmd_args[0].strip().rstrip("%")
            if raw_val.lower().endswith("px"):
                px_val = float(raw_val[:-2].strip())
                new_p = int(round(px_val / 0.4))
            else:
                new_p = int(round(float(raw_val)))

            saved_p, saved_r = set_blur_percent(new_p)

            if is_private:
                await message.reply(
                    f"✅ **Блюр карточки установлен на {saved_p}%** ({saved_r} px)",
                    reply_markup=_get_settings_markup(),
                )
            else:
                try:
                    await message.delete()
                except Exception:
                    pass

            print(f"[+] Quote blur silently updated to {saved_p}% ({saved_r} px)")

        except Exception as e:
            print(f"[ERROR in set_blur]: {e}")
            if message.chat.type != ChatType.PRIVATE:
                try:
                    await message.delete()
                except Exception:
                    pass

    @app.on_message(
        filters.command(["бс", "blurreset", "сбросблюра", "бreset"], prefixes=["/", "!", "."])
        & filters.user(admin_id)
    )
    async def reset_blur_handler(client: Client, message: Message):
        try:
            is_private = (message.chat.type == ChatType.PRIVATE)
            saved_p, saved_r = reset_blur_percent()

            if is_private:
                await message.reply(
                    f"🔄 **Блюр сброшен к дефолтному: {saved_p}%** ({saved_r} px)",
                    reply_markup=_get_settings_markup(),
                )
            else:
                try:
                    await message.delete()
                except Exception:
                    pass

            print(f"[+] Quote blur silently reset to default {saved_p}% ({saved_r} px)")

        except Exception as e:
            print(f"[ERROR in reset_blur]: {e}")
            if message.chat.type != ChatType.PRIVATE:
                try:
                    await message.delete()
                except Exception:
                    pass

    @app.on_message(
        filters.private
        & filters.command(["settings", "настройки", "menu"], prefixes=["/", "!", "."])
        & filters.user(admin_id)
    )
    async def settings_menu_handler(client: Client, message: Message):
        cur_p = get_blur_percent()
        cur_r = get_blur_radius()
        def_r = int(round(DEFAULT_BLUR_PERCENT * 0.4))
        text = (
            f"⚙️ **Панель управления оформлением цитат**\n\n"
            f"• Текущий блюр: **{cur_p}%** ({cur_r} px)\n"
            f"• Дефолтный блюр: **{DEFAULT_BLUR_PERCENT}%** ({def_r} px)\n\n"
            f"💡 Выберите значение блюра кнопками ниже или отправьте новое фото в этот чат для смены фона."
        )
        await message.reply(text, reply_markup=_get_settings_markup())

    @app.on_callback_query(filters.user(admin_id) & filters.regex(r"^blur_"))
    async def blur_callback_handler(client: Client, callback_query: CallbackQuery):
        data = callback_query.data
        if data == "blur_reset":
            saved_p, saved_r = reset_blur_percent()
            await callback_query.answer(f"🔄 Сброшено к {saved_p}% ({saved_r} px)")
        elif data.startswith("blur_set_"):
            try:
                val = int(data.split("_")[-1])
                saved_p, saved_r = set_blur_percent(val)
                await callback_query.answer(f"✅ Установлен блюр {saved_p}% ({saved_r} px)")
            except Exception:
                await callback_query.answer("Ошибка")

        cur_p = get_blur_percent()
        cur_r = get_blur_radius()
        def_r = int(round(DEFAULT_BLUR_PERCENT * 0.4))
        text = (
            f"⚙️ **Панель управления оформлением цитат**\n\n"
            f"• Текущий блюр: **{cur_p}%** ({cur_r} px)\n"
            f"• Дефолтный блюр: **{DEFAULT_BLUR_PERCENT}%** ({def_r} px)\n\n"
            f"💡 Выберите значение блюра кнопками ниже или отправьте новое фото в этот чат для смены фона."
        )
        try:
            await callback_query.edit_message_text(text, reply_markup=_get_settings_markup())
        except Exception:
            pass
