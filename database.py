from pymongo import MongoClient
from config import Config
import uuid
from datetime import datetime

class Database:
    def __init__(self):
        self.client = MongoClient(Config.MONGO_URI)
        self.db = self.client[Config.DB_NAME]
        self.users = self.db.users
        self.templates = self.db.templates
        
    def get_user(self, user_id):
        user = self.users.find_one({"user_id": user_id})
        if not user:
            user = {
                "user_id": user_id,
                "templates": [],
                "channels": [],
                "auto_mode": False,
                "created_at": datetime.now()
            }
            self.users.insert_one(user)
        return user
    
    def update_user(self, user_id, data):
        self.users.update_one({"user_id": user_id}, {"$set": data}, upsert=True)
    
    def add_template(self, user_id, template):
        template["id"] = str(uuid.uuid4())
        template["created_at"] = datetime.now()
        self.users.update_one(
            {"user_id": user_id},
            {"$push": {"templates": template}}
        )
        return template["id"]
    
    def delete_template(self, user_id, template_id):
        self.users.update_one(
            {"user_id": user_id},
            {"$pull": {"templates": {"id": template_id}}}
        )
    
    def update_template(self, user_id, template_id, data):
        self.users.update_one(
            {"user_id": user_id, "templates.id": template_id},
            {"$set": {"templates.$": data}}
        )
    
    def add_channel(self, user_id, channel_data):
        self.users.update_one(
            {"user_id": user_id},
            {"$push": {"channels": channel_data}}
        )
    
    def remove_channel(self, user_id, channel_id):
        self.users.update_one(
            {"user_id": user_id},
            {"$pull": {"channels": {"id": channel_id}}}
        )
    
    def export_data(self, user_id):
        user = self.get_user(user_id)
        return {
            "templates": user.get("templates", []),
            "channels": user.get("channels", [])
        }
    
    def import_data(self, user_id, data):
        self.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "templates": data.get("templates", []),
                "channels": data.get("channels", [])
            }}
        )

db = Database()
