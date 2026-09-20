import os
from dotenv import load_dotenv

load_dotenv()

api_id = int(os.getenv("api_id", "2040"))
api_hash = str(os.getenv("api_hash", "b18441a1ff607e10a989891a5462e627"))
bot_token = str(os.getenv("bot_token", ""))
admin_id = int(os.getenv("admin_id", os.getenv("user_id", "0")))
user_id = admin_id
ataraxis_api = str(os.getenv("ataraxis", ""))
