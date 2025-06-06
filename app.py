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

app = Flask(__name__)
# Allow only your frontend origin for CORS
CORS(app, origins=["https://resumefrontend-rif3.onrender.com"])

# Configurations
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB upload limit
app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY", "your-secret-key")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False  # Tokens without expiry

bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# MongoDB setup
mongo_uri = "mongodb+srv://22wh1a1215:Resume@cluster0.fu4wtmw.mongodb.net/job_scraping_db?retryWrites=true&w=majority"
client = MongoClient(mongo_uri)
db = client["job_scraping_db"]
resumes = db["resumes"]
users = db["users"]
pending_verifications = db["pending_verifications"]  # New collection for pending verifications

# Allowed users for protected routes
ALLOWED_USERS = {
    "22wh1a1215@bvrithyderabad.edu.in",
    "22wh1a1239@bvrithyderabad.edu.in",
    "allisarmishta@gmail.com"
}

login_attempts = {}  # Track failed login attempts
MAX_ATTEMPTS = 3

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

@app.route('/')
def home():
    return "Flask app is running!"

# --------------------
# Registration with verification code generation
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    email = data.get("email")
    password = data.get("password")

    # Password validation: at least 8 characters
    if not password or len(password) < 8:
        return jsonify({"msg": "Password must be at least 8 characters"}), 400

    # Check if user already exists (verified)
    if users.find_one({"email": email}):
        return jsonify({"msg": "User already exists"}), 409

    # Check if pending verification exists for this email, remove it to reset code
    pending_verifications.delete_many({"email": email})

    # Generate 6-digit numeric verification code
    verification_code = ''.join(random.choices(string.digits, k=6))

    # Hash the password but DO NOT create user yet - wait for verification
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')

    # Store verification info in pending_verifications collection with timestamp
    pending_verifications.insert_one({
        "email": email,
        "password": hashed_pw,
        "verification_code": verification_code,
        "created_at": datetime.datetime.utcnow()
    })

    # For now, simulate sending email by printing the code in console (replace this with actual email service)
    print(f"Verification code for {email}: {verification_code}")

    return jsonify({"msg": "Verification code sent to your email (check console in dev)"}), 200

# Verification endpoint
@app.route("/verify-registration", methods=["POST"])
def verify_registration():
    data = request.json
    email = data.get("email")
    code = data.get("code")

    record = pending_verifications.find_one({"email": email})

    if not record:
        return jsonify({"msg": "No pending verification found for this email"}), 404

    # Optional: check if code expired - for example after 10 minutes
    now = datetime.datetime.utcnow()
    if now - record["created_at"] > datetime.timedelta(minutes=10):
        pending_verifications.delete_one({"email": email})
        return jsonify({"msg": "Verification code expired. Please register again."}), 400

    if record["verification_code"] != code:
        return jsonify({"msg": "Invalid verification code"}), 400

    # Create the actual user in users collection
    users.insert_one({
        "email": email,
        "password": record["password"]
    })

    # Remove the pending verification record
    pending_verifications.delete_one({"email": email})

    return jsonify({"msg": "User verified and registered successfully"}), 201

# --------------------
# Login remains unchanged
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

    # Successful login resets attempts count
    login_attempts[email] = 0
    access_token = create_access_token(identity=email)
    return jsonify({"access_token": access_token}), 200

# --------------------
# Other routes remain unchanged

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

        skills = data.get("Skills", [])
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
Skills: {', '.join(skills)}

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
    app.run(debug=True, host="0.0.0.0")
