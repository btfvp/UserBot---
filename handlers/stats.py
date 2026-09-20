import asyncio
from datetime import datetime, timezone
from hydrogram import Client, enums
from hydrogram.types import Message
from hydrogram import filters
from clients import ataraxis
from config import user_id
from utils.progress import build_bar, compute_progress


def register(app: Client):
    @app.on_message(filters.command(["ataraxis", "ax"], prefixes=["!", ".", "/"]) & (filters.user(user_id) | filters.me))
    async def ataraxis_stats_handler(client: Client, message: Message):
        try:
            stats = await ataraxis.get_my_listening_stats()
            profile = await ataraxis.get_my_profile()
            np = await ataraxis.get_my_now_playing()
        except Exception as e:
            await message.reply(f"Account linking error: {e}")
            return

        text = (
            f"**{profile.username or 'User'}**\n"
            f"**Tracks played:** __{stats.totalPlays}__\n"
            f"**Unique tracks:** __{stats.uniqueTracks}__\n"
            f"**Minutes listened:** __{stats.totalMinutes}__"
            f"\n\n\n"
        )

        status_msg = await message.reply(text, parse_mode=enums.ParseMode.MARKDOWN)

        if not np.isPlaying or not np.track:
            await status_msg.edit_text(
                text + "Nothing is playing right now.",
                parse_mode=enums.ParseMode.MARKDOWN
            )
            return

        track = np.track
        duration_sec = track.durationMs / 1000
        played_at = datetime.fromisoformat(np.playedAt.replace("Z", "+00:00"))

        for _ in range(10):
            progress, cur_min, cur_sec, total_min, total_sec = compute_progress(
                played_at, duration_sec
            )
            bar = build_bar(progress)

            playing_text = (
                f"**{track.title}**\n"
                f"{track.artists_string}\n\n"
                f"`{bar}` {int(progress * 100)}%\n"
                f"{cur_min}:{cur_sec:02d} / {total_min}:{total_sec:02d}"
            )

            try:
                await status_msg.edit_text(
                    text + playing_text,
                    parse_mode=enums.ParseMode.MARKDOWN
                )
            except Exception:
                pass

            await asyncio.sleep(3)

            if progress >= 1.0:
                break
