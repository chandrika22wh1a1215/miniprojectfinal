from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import os
from flask_cors import CORS
from werkzeug.utils import secure_filename
import fitz  # PyMuPDF
import tempfile
import traceback
import re
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
import random
import string
import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage
from datetime import datetime

app = Flask(__name__)
CORS(app, origins=["https://resumefrontend-rif3.onrender.com"])

app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY", "your-secret-key")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False

bcrypt = Bcrypt(app)
jwt = JWTManager(app)

mongo_uri = "mongodb+srv://22wh1a1215:Resume@cluster0.fu4wtmw.mongodb.net/job_scraping_db?retryWrites=true&w=majority"
client = MongoClient(mongo_uri)
db = client["job_scraping_db"]
resumes = db["resumes"]
users = db["users"]
pending_verifications = db["pending_verifications"]

ALLOWED_USERS = {
    "22wh1a1215@bvrithyderabad.edu.in",
    "22wh1a1239@bvrithyderabad.edu.in",
    "allisarmishta@gmail.com"
}

login_attempts = {}
MAX_ATTEMPTS = 3

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

def send_verification_email(receiver_email, code):
    try:
        msg = EmailMessage()
        msg['Subject'] = 'Your Verification Code'
        msg['From'] = '22wh1a1215@bvrithyderabad.edu.in'  # Replace with your Gmail
        msg['To'] = receiver_email
        msg.set_content(f"Your verification code is: {code}")

        # Gmail SMTP server
        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.starttls()
            smtp.login('22wh1a1215@bvrithyderabad.edu.in', 'lhvcjbdvwqtxwazo')  # Your Gmail + App password (no spaces)
            smtp.send_message(msg)

        print(f"✅ Verification email sent to {receiver_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")



@app.route('/')
def home():
    return "Flask app is running!"

def send_verification_email(receiver_email, code):
    try:
        print(f"⚙️ Preparing to send email to {receiver_email} with code {code}")
        
        msg = EmailMessage()
        msg['Subject'] = 'Your Verification Code'
        msg['From'] = '8f06f4002@smtp-brevo.com'
        msg['To'] = receiver_email
        msg.set_content(f"Your verification code is: {code}")

        with smtplib.SMTP('smtp-relay.brevo.com', 587) as smtp:
            smtp.starttls()
            smtp.login('8f06f4002@smtp-brevo.com', 'g5OsRyTUfJnXtM96')
            smtp.send_message(msg)

        print(f"✅ Verification email sent to {receiver_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")


def send_verification_email(receiver_email, code):
    try:
        msg = EmailMessage()
        msg['Subject'] = 'Your Verification Code'
        msg['From'] = '22wh1a1215@bvrithyderabad.edu.in'  # Your Gmail address
        msg['To'] = receiver_email
        msg.set_content(f"Your verification code is: {code}")

        with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
            smtp.starttls()
            smtp.login('22wh1a1215@bvrithyderabad.edu.in', 'lhvcjbdvwqtxwazo')  # Your Gmail + App password
            smtp.send_message(msg)

        print(f"✅ Verification email sent to {receiver_email}")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")


@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    if email not in login_attempts:
        login_attempts[email] = 0

    user = users.find_one({"email": email})
    if not user or not bcrypt.check_password_hash(user["password"], password):
        login_attempts[email] += 1
        if login_attempts[email] >= MAX_ATTEMPTS:
            return jsonify({"msg": "Invalid credentials", "show_forgot": True}), 401
        return jsonify({"msg": "Invalid credentials"}), 401

    login_attempts[email] = 0
    access_token = create_access_token(identity=email)
    return jsonify({"access_token": access_token}), 200

@app.route("/resumes", methods=["GET"])
@jwt_required()
def get_resumes():
    current_user_email = get_jwt_identity()
    if current_user_email not in ALLOWED_USERS:
        return jsonify({"msg": "Access forbidden"}), 403
    data = list(resumes.find({}))
    for resume in data:
        resume["_id"] = str(resume["_id"])
    return jsonify(data)

@app.route("/dbtest")
def db_test():
    return jsonify({"msg": "MongoDB connection successful!"})

@app.route("/test")
def test():
    return "Test route working!"

def extract_text_pymupdf(pdf_path):
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text()
    return text


@app.route("/register", methods=["POST"])
def register():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    dob_str = data.get("dob")  # Expected format: dd-mm-yyyy

    if not email or not password or not dob_str:
        return jsonify({"msg": "Email, password and DOB required"}), 400

    # Validate DOB format
    try:
        dob = datetime.strptime(dob_str, "%d-%m-%Y")
    except ValueError:
        return jsonify({"msg": "DOB must be in dd-mm-yyyy format"}), 400

    existing_user = users.find_one({"email": email})
    if existing_user:
        return jsonify({"msg": "User already registered"}), 409

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    verification_code = ''.join(random.choices(string.digits, k=6))

    pending_verifications.update_one(
        {"email": email},
        {
            "$set": {
                "password": hashed_password,
                "dob": dob_str,  # Store as original string or dob.isoformat()
                "verification_code": verification_code,
                "created_at": datetime.utcnow()
            }
        },
        upsert=True
    )

    send_verification_email(email, verification_code)
    return jsonify({"msg": "Verification code sent to your email"}), 200

@app.route("/upload_resume", methods=["POST"])
@jwt_required()
def upload_resume():
    if 'file' not in request.files:
        return jsonify({"msg": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"msg": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"msg": "Invalid file type (only PDF allowed)"}), 400

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            file.save(tmp.name)
            filepath = tmp.name
        text = extract_text_pymupdf(filepath)
        resume_data = {
            "filename": secure_filename(file.filename),
            "resumeText": text
        }
        result = resumes.insert_one(resume_data)
        resume_id = str(result.inserted_id)
        return jsonify({"msg": "File uploaded!", "id": resume_id}), 201
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"msg": f"Server error: {str(e)}"}), 500
    finally:
        try:
            if 'filepath' in locals() and os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

@app.route("/resumes/<id>", methods=["PUT"])
@jwt_required()
def update_resume(id):
    updated_data = request.json
    resumes.update_one({"_id": ObjectId(id)}, {"$set": updated_data})
    return jsonify({"msg": "Resume updated successfully!"})

@app.route("/profile", methods=["POST"])
@jwt_required()
def add_manual_resume():
    try:
        data = request.json

        name = data.get("fullName", "").strip()
        email = data.get("email", "").strip()
        phone = data.get("phoneNumber", "").strip()

        if not name or any(char.isdigit() for char in name):
            return jsonify({"msg": "Invalid name"}), 400
        if not email or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            return jsonify({"msg": "Invalid email"}), 400
        if not phone or not phone.isdigit():
            return jsonify({"msg": "Phone must be digits only"}), 400

        soft_skills = data.get("SoftSkills", [])
        technical_skills = data.get("TechnicalSkills", [])
        skills = {
            "SoftSkills": soft_skills,
            "TechnicalSkills": technical_skills
        }

        education = data.get("Education", [])
        experience = data.get("Experience", [])
        certifications = data.get("Certifications", [])
        projects = data.get("Projects", [])
        links = data.get("Links", [])
        summary = data.get("Summary", "")
        total_years = data.get("TotalYearsOverall", "")

        resume_text = f"""
Name: {name}
Email: {email}
Phone: {phone}

Technical Skills: {', '.join(technical_skills)}
Soft Skills: {', '.join(soft_skills)}

Education:
""" + "\n".join([
            f"- {e.get('Degree', '')} at {e.get('Institution', '')} ({e.get('Year', '')})"
            for e in education]) + """

Projects:
""" + "\n".join([
            f"- {p.get('Name', '')}: {p.get('Description', '')} using {p.get('Technologies', '')}"
            for p in projects]) + """

Experience:
""" + "\n".join([
            f"- {x.get('Title', '')} at {x.get('Company', '')} ({x.get('Duration', '')})"
            for x in experience]) + """

Certifications:
""" + "\n".join([
            f"- {c.get('Name', '')} from {c.get('Issuer', '')} ({c.get('Year', '')})"
            for c in certifications]) + f"""

Links: {', '.join(links)}
Summary: {summary}
Total Experience: {total_years} years
""".strip()

        resume = {
            "Name": name,
            "Email": email,
            "Phone": phone,
            "Skills": skills,
            "Education": education,
            "Experience": experience,
            "Certifications": certifications,
            "Projects": projects,
            "Links": links,
            "Summary": summary,
            "TotalYearsOverall": total_years,
            "ResumeText": resume_text,
            "SubmittedBy": get_jwt_identity()
        }

        result = resumes.insert_one(resume)
        return jsonify({"msg": "Profile saved", "id": str(result.inserted_id)}), 201

    except Exception as e:
        traceback.print_exc()
        return jsonify({"msg": f"Internal Server Error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
