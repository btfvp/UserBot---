import re
from hydrogram import Client, filters
from hydrogram.types import Message


def _make_filter(target_id: int, pattern: str, name: str):
    async def func(flt, client: Client, message: Message):
        if not message.text:
            return False
        is_correct = message.from_user and message.from_user.id == flt.target_id
        word_active = bool(re.search(pattern, message.text, re.IGNORECASE))
        return is_correct and word_active
    return filters.create(func, name=name, target_id=target_id)


