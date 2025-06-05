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

app = Flask(__name__)
CORS(app)
app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024  # 2 MB upload limit
app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY", "your-secret-key")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False

bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# MongoDB setup
mongo_uri = "mongodb+srv://22wh1a1215:Resume@cluster0.fu4wtmw.mongodb.net/job_scraping_db?retryWrites=true&w=majority"
client = MongoClient(mongo_uri)
db = client["job_scraping_db"]
resumes = db["resumes"]
users = db["users"]

ALLOWED_USERS = {
    "22wh1a1215@bvrithyderabad.edu.in", 
    "22wh1a1239@bvrithyderabad.edu.in",
    "allisarmishta@gmail.com"
}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

@app.route('/')
def home():
    return "Flask app is running!"

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    if users.find_one({"email": email}):
        return jsonify({"msg": "User already exists"}), 409
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    users.insert_one({"email": email, "password": hashed_pw})
    return jsonify({"msg": "User registered successfully"}), 201

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    user = users.find_one({"email": email})
    if not user or not bcrypt.check_password_hash(user["password"], password):
        return jsonify({"msg": "Invalid credentials"}), 401
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

@app.route("/upload_resume", methods=["POST"])
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

import re  # make sure to import re at the top of your file if not already

@app.route("/profile", methods=["POST"])
@jwt_required()
def add_manual_resume():
    data = request.json

    # Personal Information
    personal_info = data.get("personalInformation", {})
    name = personal_info.get("fullName", "")
    email = personal_info.get("email", "")
    phone = personal_info.get("phoneNumber", "")

    # Validate name, email, phone
    if not isinstance(name, str) or any(char.isdigit() for char in name):
        return jsonify({"msg": "Invalid name: must be a string without numbers."}), 400
    if not isinstance(email, str) or not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return jsonify({"msg": "Invalid email format."}), 400
    if not isinstance(phone, str) or not phone.isdigit():
        return jsonify({"msg": "Invalid phone: digits only."}), 400

    # Other fields
    skills = data.get("skills", "")
    education = data.get("education", [])
    projects = data.get("projects", [])
    experience = data.get("experience", [])
    certifications = data.get("certifications", [])
    links = data.get("links", "")
    summary = data.get("summary", "")

    # Validate non-list string fields
    for field_name, field_value in [("skills", skills), ("links", links), ("summary", summary)]:
        if not isinstance(field_value, str):
            return jsonify({"msg": f"Invalid {field_name}: must be a string."}), 400

    # Validate list fields
    for field_name, field_value in [
        ("education", education), ("projects", projects),
        ("experience", experience), ("certifications", certifications)
    ]:
        if not isinstance(field_value, list):
            return jsonify({"msg": f"Invalid {field_name}: must be a list."}), 400

    # Build resumeText from nested data
    resume_text = f"""
Name: {name}
Email: {email}
Phone: {phone}
Skills: {skills}

Education:
"""
    for edu in education:
        resume_text += f"- {edu.get('degree', '')}, {edu.get('institution', '')}, {edu.get('year', '')}, Grade: {edu.get('grade', '')} ({edu.get('type', '')})\n"

    resume_text += "\nProjects:\n"
    for proj in projects:
        resume_text += f"- {proj.get('projectName', '')}: {proj.get('description', '')}, Tech: {proj.get('technologiesUsed', '')}, GitHub: {proj.get('githubURL', '')}, URL: {proj.get('projectURL', '')}\n"

    resume_text += "\nExperience:\n"
    for exp in experience:
        resume_text += f"- {exp.get('jobTitle', '')} at {exp.get('company', '')} ({exp.get('duration', '')}), {exp.get('description', '')}, {exp.get('totalYears', '')} years overall\n"

    resume_text += "\nCertifications:\n"
    for cert in certifications:
        resume_text += f"- {cert.get('certificationName', '')} from {cert.get('issuingOrganisation', '')}, Year: {cert.get('year', '')}\n"

    resume_text += f"\nLinks: {links}\nSummary: {summary.strip()}"

    resume = {
        "personalInformation": {
            "fullName": name,
            "email": email,
            "phoneNumber": phone
        },
        "skills": skills,
        "education": education,
        "projects": projects,
        "experience": experience,
        "certifications": certifications,
        "links": links,
        "summary": summary,
        "resumeText": resume_text.strip(),
        "submitted_by": get_jwt_identity(),
    }

    result = resumes.insert_one(resume)
    return jsonify({"msg": "Manual resume added!", "id": str(result.inserted_id)}), 201

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
