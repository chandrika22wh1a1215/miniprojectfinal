from pymongo import MongoClient
import os

mongo_uri = os.getenv("MONGO_URI", "mongodb+srv://22wh1a1215:Resume@cluster0.fu4wtmw.mongodb.net/job_scraping_db?retryWrites=true&w=majority")
client = MongoClient(mongo_uri)
db = client["job_scraping_db"]
