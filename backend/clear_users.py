from pymongo import MongoClient

client = MongoClient("mongodb://127.0.0.1:27017/")
db = client["cakeshop"]

db.users.delete_many({})

print("✅ All users cleared successfully")
