from datetime import datetime
from db import db

notifications = db["notifications"]

def add_notification(user_email, message, job_id=None, notification_type="info"):
    notification = {
        "user_email": user_email,
        "message": message,
        "type": notification_type,
        "job_id": job_id,
        "created_at": datetime.utcnow(),
        "is_read": False
    }
    notifications.insert_one(notification)
