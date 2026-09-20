import asyncio
from hydrogram import Client
from ataraxis import AsyncAtaraxisClient
from config import api_id, api_hash, bot_token, ataraxis_api

app = Client("bot", api_id=api_id, api_hash=api_hash, bot_token=bot_token)
ataraxis = AsyncAtaraxisClient(api_key=ataraxis_api)


