from flask import Flask, request, jsonify, session
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename
from email.message import EmailMessage
from datetime import datetime, timedelta
from ml_temp_resume import ml_temp_resume_bp
from bson.objectid import ObjectId

import fitz  # PyMuPDF
import os
import smtplib
import random
import string
import re
import traceback
import tempfile


from db import db  # <--- NEW LINE

app = Flask(__name__)
bcrypt = Bcrypt(app)


CORS(app,
     origins=[
         "https://resumefrontend-rif3.onrender.com",
         "https://mini-project-eight-amber.vercel.app"
     ],
     supports_credentials=True,  # If you use cookies or JWT in headers
     allow_headers="*",
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
)

app.config['MAX_CONTENT_LENGTH'] = 2 * 1024 * 1024
app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY", "your-secret-key")
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = False
app.config["MONGO_URI"] = "mongodb+srv://22wh1a1215:Resume@cluster0.fu4wtmw.mongodb.net/job_scraping_db?retryWrites=true&w=majority"

jwt = JWTManager(app)

resumes = db["resumes"]
users = db["users"]
pending_verifications = db["pending_verifications"]
job_posts = db["job_posts"]
notifications = db["notifications"]
applications = db["applications"]
activities = db["activities"]


ALLOWED_USERS = {
    "22wh1a1215@bvrithyderabad.edu.in",
    "22wh1a1239@bvrithyderabad.edu.in",
    "allisarmishta@gmail.com",
    "chandrikavedula@gmail.com"
}

login_attempts = {}
MAX_ATTEMPTS = 3


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'


@app.route('/')
def home():
    return "Flask app is running!"


@app.route('/dbtest')
def db_test():
    return jsonify({"msg": "MongoDB connection successful!"})


@app.route('/test')
def test():
    return "Test route working!"


def send_verification_email(receiver_email, code):
    msg = EmailMessage()
    msg['Subject'] = 'Your Verification Code'
    msg['From'] = '22wh1a1215@bvrithyderabad.edu.in'
    msg['To'] = receiver_email
    msg.set_content(f"Your verification code is: {code}")

    with smtplib.SMTP('smtp.gmail.com', 587) as smtp:
        smtp.starttls()
        smtp.login('22wh1a1215@bvrithyderabad.edu.in', 'lhvcjbdvwqtxwazo')
        smtp.send_message(msg)

@app.route('/api/send-verification-code', methods=['POST'])
def send_verification_code_route():
    data = request.json
    email = data.get('email')

    if not email:
        return jsonify({'error': 'Email required'}), 400

    # Generate 6-digit verification code
    code = ''.join(random.choices(string.digits, k=6))

    try:
        # Send email with the code
        send_verification_email(email, code)

        # Send OTP to frontend to verify there
        return jsonify({'message': 'Verification email sent', 'otp': code}), 200

    except Exception as e:
        return jsonify({'error': str(e)}), 500
        

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    email = data.get('email')
    password = data.get('password')
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


def extract_text_pymupdf(pdf_path):
    doc = fitz.open(pdf_path)
    return ''.join(page.get_text() for page in doc)

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    full_name = data.get("full_name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    confirm_password = data.get("confirm_password", "")
    dob = data.get("dob", "").strip()

    if not all([full_name, email, password, confirm_password, dob]):
        return jsonify({"message": "All fields are required"}), 400

    if password != confirm_password:
        return jsonify({"message": "Passwords do not match"}), 400

    if users.find_one({"email": email}) or pending_verifications.find_one({"email": email}):
        return jsonify({"message": "Email already exists"}), 409

    hashed_password = bcrypt.generate_password_hash(password).decode("utf-8")
    verification_code = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.utcnow() + timedelta(minutes=3)

    pending_verifications.insert_one({
        "full_name": full_name,
        "email": email,
        "password": hashed_password,
        "dob": dob,
        "verification_code": verification_code,
        "created_at": datetime.utcnow(),
        "expires_at": expires_at
    })

    send_verification_email(email, verification_code)

    return jsonify({"message": "Verification email sent"}), 200

@app.route("/verify", methods=["POST"])
def verify_code():
    data = request.json
    email = data.get("email", "").strip()
    code = str(data.get("code", "")).strip()

    if not email or not code:
        return jsonify({"message": "Missing email or code"}), 400

    now = datetime.utcnow()
    record = pending_verifications.find_one({"email": email})

    if not record or str(record.get("verification_code", "")).strip() != code:
        return jsonify({"message": "Invalid verification code"}), 400

    if record["expires_at"] < now:
        return jsonify({"message": "Verification code expired"}), 400

    user_data = {
        "full_name": record["full_name"],
        "email": record["email"],
        "password": record["password"],
        "dob": record["dob"],
        "created_at": datetime.utcnow()
    }
    users.insert_one(user_data)
    pending_verifications.delete_one({"_id": record["_id"]})

    return jsonify({"message": "Email verified and user registered successfully"}), 200


@app.route("/resend-code", methods=["POST"])
def resend_code():
    data = request.json
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email required"}), 400

    record = pending_verifications.find_one({"email": email})
    if not record:
        return jsonify({"error": "No pending verification found"}), 404

    new_code = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.utcnow() + timedelta(minutes=3)

    pending_verifications.update_one(
        {"email": email},
        {"$set": {
            "verification_code": new_code,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at
        }}
    )

    send_verification_email(email, new_code)
    return jsonify({"message": "Verification code resent"}), 200


@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.json
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email required"}), 400

    user = users.find_one({"email": email})
    if not user:
        return jsonify({"error": "User not found"}), 404

    reset_code = ''.join(random.choices(string.digits, k=6))
    expires_at = datetime.utcnow() + timedelta(minutes=3)

    pending_verifications.update_one(
        {"email": email},
        {"$set": {
            "reset_code": reset_code,
            "created_at": datetime.utcnow(),
            "expires_at": expires_at
        }},
        upsert=True
    )

    send_verification_email(email, reset_code)
    return jsonify({"message": "Password reset code sent to your email"}), 200


@app.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.json
    email = data.get("email")
    code = data.get("code")
    new_password = data.get("new_password")
    confirm_password = data.get("confirm_password")

    if not email or not code or not new_password or not confirm_password:
        return jsonify({"error": "All fields required"}), 400
    if new_password != confirm_password:
        return jsonify({"error": "Passwords do not match"}), 400

    password_regex = r'^(?=.[a-z])(?=.[A-Z])(?=.\d)(?=.[!@#$%^&]).{8,}$'
    if not re.match(password_regex, new_password):
        return jsonify({"error": "Password too weak"}), 400

    record = pending_verifications.find_one({"email": email})
    now = datetime.utcnow()
    if not record or record.get("reset_code") != code or record.get("expires_at", now) < now:
        return jsonify({"error": "Invalid or expired reset code"}), 400

    hashed_password = bcrypt.generate_password_hash(new_password).decode("utf-8")
    users.update_one({"email": email}, {"$set": {"password": hashed_password}})
    pending_verifications.delete_one({"email": email})

    return jsonify({"message": "Password reset successful"}), 200

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
        return jsonify({"msg": "File uploaded!", "id": str(result.inserted_id)}), 201
    except Exception as e:
        print(traceback.format_exc())
        return jsonify({"msg": f"Server error: {str(e)}"}), 500
    finally:
        if 'filepath' in locals() and os.path.exists(filepath):
            os.remove(filepath)

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
        email = get_jwt_identity()

        name = data.get("fullName", "").strip()
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
            "SubmittedBy": email
        }

        # Calculate profile completion
        fields_filled = sum(bool(data.get(key)) for key in [
            "fullName", "email", "phoneNumber", "SoftSkills", "TechnicalSkills",
            "Education", "Experience", "Certifications", "Projects", "Links", "Summary", "TotalYearsOverall"
        ])
        total_fields = 12
        profile_completion = int((fields_filled / total_fields) * 100)

        # Update or insert resume
        resumes.update_one(
            {"SubmittedBy": email},
            {"$set": resume},
            upsert=True
        )

        # Update user collection
        users.update_one(
            {"email": email},
            {"$set": {
                "profileCompletion": profile_completion,
                "lastUpdated": datetime.utcnow()
            }}
        )

        return jsonify({
            "msg": "Profile saved or updated",
            "profileCompletion": profile_completion
        }), 200

    except Exception as e:
        traceback.print_exc()
        return jsonify({"msg": f"Internal Server Error: {str(e)}"}), 500

@app.route("/profile", methods=["GET"])
@jwt_required()
def get_profile():
    try:
        email = get_jwt_identity()
        user = users.find_one({"email": email}, {"_id": 0})  # Don't return _id

        if not user:
            return jsonify({"msg": "User not found"}), 404

        return jsonify(user), 200

    except Exception as e:
        print("[GET PROFILE ERROR]", e)
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500



@app.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    try:
        email = get_jwt_identity()
        print("Dashboard accessed by:", email)

        if not email:
            return jsonify({"msg": "Invalid identity"}), 401

        user = users.find_one({"email": email})
        if not user:
            return jsonify({"msg": "User not found"}), 404

        # Safely get values with defaults
        total_resumes = resumes.count_documents({"email": email})
        total_applications = applications.count_documents({"email": email}) if "applications" in db.list_collection_names() else 0
        profile_completion = user.get("profileCompletion", 0)
        last_updated = user.get("lastUpdated", datetime.utcnow()).isoformat()

        # Get recent activity
        activity_cursor = activities.find({"email": email}).sort("date", -1).limit(5) if "activities" in db.list_collection_names() else []
        activity_list = []
        for act in activity_cursor:
            activity_list.append({
                "id": str(act.get("_id", "")),
                "type": act.get("type", "profile_update"),
                "description": act.get("description", ""),
                "date": act.get("date", datetime.utcnow()).isoformat()
            })

        return jsonify({
            "stats": {
                "totalResumes": total_resumes,
                "totalApplications": total_applications,
                "profileCompletion": profile_completion,
                "lastUpdated": last_updated
            },
            "recentActivity": activity_list
        }), 200

    except Exception as e:
        print("[DASHBOARD ERROR]", e)
        return jsonify({"error": "Internal Server Error", "details": str(e)}), 500



@app.route("/resume/<resume_id>", methods=["GET"])
@jwt_required()
def get_resume_by_id(resume_id):
    current_user_email = get_jwt_identity()
    resume = resumes.find_one({"_id": ObjectId(resume_id), "SubmittedBy": current_user_email})
    if not resume:
        return jsonify({"msg": "Resume not found or access denied"}), 404
    resume["_id"] = str(resume["_id"])
    return jsonify(resume), 200

@app.route('/add-job', methods=['POST'])
def add_job():
    data = request.get_json()

    required_fields = ['title', 'company', 'location', 'description', 'requirements', 'experienceRequired']
    if not all(field in data for field in required_fields):
        return jsonify({'error': 'Missing fields'}), 400

    # Enforce data types
    if not isinstance(data['title'], str):
        return jsonify({'error': 'title must be a string'}), 400
    if not isinstance(data['company'], str):
        return jsonify({'error': 'company must be a string'}), 400
    if not isinstance(data['location'], str):
        return jsonify({'error': 'location must be a string'}), 400
    if not isinstance(data['description'], str):
        return jsonify({'error': 'description must be a string'}), 400
    if not isinstance(data['requirements'], list) or not all(isinstance(r, str) for r in data['requirements']):
        return jsonify({'error': 'requirements must be a list of strings'}), 400
    if not isinstance(data['experienceRequired'], int):
        return jsonify({'error': 'experienceRequired must be an integer'}), 400

    job = {
        "title": data['title'],
        "company": data['company'],
        "location": data['location'],
        "description": data['description'],
        "requirements": data['requirements'],
        "experienceRequired": data['experienceRequired'],
        "created_at": datetime.utcnow()
    }
    job_posts.insert_one(job)
    return jsonify({'msg': 'Job added successfully!'}), 201

    
@app.route('/jobs', methods=['GET'])
def get_all_jobs():
    jobs = list(job_posts.find({}, {'_id': 0}))
    return jsonify(jobs), 200

@app.route('/jobs/matches', methods=['GET'])
@jwt_required()
def get_job_matches():
    email = get_jwt_identity()
    try:
        user_resumes = list(db["ml_temp_resumes"].find({"user_email": email}, {"_id": 1}))
        valid_resume_ids = [resume["_id"] for resume in user_resumes]

        print("User email:", email)
        print("User resume IDs:", valid_resume_ids)

        if not valid_resume_ids:
            print("No ML resumes found for user.")
            return jsonify([]), 200

        matched_jobs_cursor = db["job_posts"].find({
            "resume_id": {"$in": valid_resume_ids}
        })

        results = []
        for job in matched_jobs_cursor:
            results.append({
                "id": str(job["_id"]),
                "title": job.get("title"),
                "company": job.get("company"),
                "location": job.get("location"),
                "description": job.get("description"),
                "requiredSkills": job.get("requiredSkills", []),
                "link": job.get("link"),
                "resume_id": str(job.get("resume_id")),
                "matchPercentage": job.get("matchPercentage", 0)
            })

        print(f"Found {len(results)} matched jobs for user {email}")
        print("Matched jobs:", results)
        return jsonify(results), 200
    except Exception as e:
        print(f"[GET JOB MATCHES ERROR] {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": "Failed to fetch matched jobs"}), 500


@app.route('/notifications', methods=['GET'])
@jwt_required()
def get_notifications():
    try:
        user_email = get_jwt_identity()
        user_notifications = list(notifications.find({"user_email": user_email}).sort("created_at", -1))
        # Convert ObjectId to string for JSON serialization
        for notification in user_notifications:
            notification["_id"] = str(notification["_id"])
            if notification.get("job_id"):
                notification["job_id"] = str(notification["job_id"])
            if "created_at" in notification:
                notification["created_at"] = notification["created_at"].isoformat()
        return jsonify(user_notifications), 200
    except Exception as e:
        print(f"[GET NOTIFICATIONS ERROR] {e}")
        return jsonify({"error": "Failed to fetch notifications"}), 500

@app.route('/notifications/mark-read', methods=['POST'])
@jwt_required()
def mark_notifications_read():
    user_email = get_jwt_identity()
    data = request.json
    notification_ids = data.get('notification_ids', [])
    # Convert string IDs to ObjectId
    obj_ids = [ObjectId(id) for id in notification_ids if ObjectId.is_valid(id)]
    notifications.update_many(
        {"_id": {"$in": obj_ids}, "user_email": user_email},
        {"$set": {"is_read": True}}
    )
    return jsonify({"msg": "Notifications marked as read"}), 200


app.register_blueprint(ml_temp_resume_bp)

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
