import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    
    # MongoDB Configuration
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    DB_NAME = os.getenv("DB_NAME", "anime_poster_bot")
    
    # Port (Heroku provides this, but we don't use it for webhook)
    PORT = int(os.getenv("PORT", 8443))
    
    # Admin IDs (comma-separated)
    ADMIN_IDS = []
    admin_ids_str = os.getenv("ADMIN_IDS", "")
    if admin_ids_str:
        ADMIN_IDS = [int(x.strip()) for x in admin_ids_str.split(",") if x.strip().isdigit()]
    
    @classmethod
    def validate(cls):
        """Validate critical configuration"""
        if not cls.BOT_TOKEN:
            raise ValueError("BOT_TOKEN must be set in environment variables!")
        if not cls.DB_NAME:
            raise ValueError("DB_NAME must be set in environment variables!")
