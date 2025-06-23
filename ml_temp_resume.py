from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson.objectid import ObjectId
from bson.binary import Binary
from datetime import datetime
from werkzeug.utils import secure_filename
import io
from db import db
from utils import add_notification
from flask import Blueprint

ml_temp_resume_bp = Blueprint('ml_temp_resume', __name__)

def allowed_file(filename):
    """Check if file has an allowed extension"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'pdf'}

@ml_temp_resume_bp.route("/ml/upload_resume", methods=["POST"])
@jwt_required()
def ml_upload_resume():
    email = get_jwt_identity()
    if 'file' not in request.files:
        return jsonify({"msg": "No file part in the request"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"msg": "No file selected"}), 400
    if not allowed_file(file.filename):
        return jsonify({"msg": "Invalid file type (only PDF allowed)"}), 400

    pdf_data = file.read()
    job_ids = request.form.getlist("job_ids")  # Expecting job_ids[] in form-data

    # Get match_percentage from request
    match_percentage = request.form.get("match_percentage")
    if match_percentage is not None:
        try:
            match_percentage = float(match_percentage)
        except ValueError:
            return jsonify({"msg": "Invalid match_percentage format"}), 400
    else:
        # Handle case where match_percentage is not provided
        # You can set a default (e.g., None or 0), or return an error
        match_percentage = None  # or 0, or return an error

    temp_resume = {
        "user_email": email,
        "filename": secure_filename(file.filename),
        "pdf_data": Binary(pdf_data),
        "created_at": datetime.utcnow(),
        "match_percentage": match_percentage
    }
    result = ml_temp_resumes.insert_one(temp_resume)
    resume_id = result.inserted_id

    # Update all referenced jobs to point to this resume
    for job_id in job_ids:
        job_posts.update_one(
            {"_id": ObjectId(job_id)},
            {"$set": {"resume_id": resume_id}}
        )

    # Create a notification for the user
    add_notification(
        user_email=email,
        message="Your ML-generated resume was uploaded successfully.",
        notification_type="success"
    )

    return jsonify({"msg": "ML resume uploaded and linked to jobs", "resume_id": str(resume_id)}), 201



@ml_temp_resume_bp.route("/ml/temp_resumes", methods=["GET"])
@jwt_required()
def get_temp_resumes():
    email = get_jwt_identity()
    resumes = list(ml_temp_resumes.find({"user_email": email}))
    for resume in resumes:
        resume["_id"] = str(resume["_id"])
        # You can add more fields here if needed
    return jsonify(resumes), 200



# 2. Get download link for a job (jobs reference resume_id)
@ml_temp_resume_bp.route("/ml/job_resume/<job_id>", methods=["GET"])
@jwt_required()
def get_job_resume(job_id):
    email = get_jwt_identity()
    job = job_posts.find_one({"_id": ObjectId(job_id)})
    if not job or job.get("resume_id") is None:
        return jsonify({"msg": "Resume not found for this job"}), 404
    resume_id = job["resume_id"]
    # Option 1: Relative path (recommended if frontend knows API base)
    download_link = f"/ml/temp_resumes/{resume_id}/download"
    # Option 2: Absolute URL (uncomment if needed)
    # from flask import request
    # base_url = request.host_url.rstrip('/')
    # download_link = f"{base_url}/ml/temp_resumes/{resume_id}/download"
    return jsonify({
        "resume_id": str(resume_id),
        "download_link": download_link
    }), 200

# 3. Download/view a specific temporary ML resume (by resume_id)
@ml_temp_resume_bp.route("/ml/temp_resumes/<resume_id>/download", methods=["GET"])
@jwt_required()
def download_temp_ml_resume(resume_id):
    email = get_jwt_identity()
    try:
        resume = ml_temp_resumes.find_one({"_id": ObjectId(resume_id), "user_email": email})
    except Exception:
        return jsonify({"msg": "Invalid resume ID"}), 400
    if not resume:
        return jsonify({"msg": "Resume not found"}), 404
    return send_file(
        io.BytesIO(resume["pdf_data"]),
        download_name=resume.get("filename", "resume.pdf"),
        mimetype="application/pdf",
        as_attachment=True
    )

# 4. Reject (delete) a temporary ML resume (by resume_id)
@ml_temp_resume_bp.route("/ml/temp_resumes/<resume_id>", methods=["DELETE"])
@jwt_required()
def reject_ml_resume(resume_id):
    email = get_jwt_identity()
    try:
        result = ml_temp_resumes.delete_one({"_id": ObjectId(resume_id), "user_email": email})
        # Optionally, remove resume_id from jobs referencing this resume
        job_posts.update_many({"resume_id": ObjectId(resume_id)}, {"$unset": {"resume_id": ""}})
    except Exception:
        return jsonify({"msg": "Invalid resume ID"}), 400
    if result.deleted_count == 0:
        return jsonify({"msg": "Resume not found"}), 404
    return jsonify({"msg": "Resume rejected and deleted"}), 200

# 5. Optionally: Unlink resume from a job (but keep the resume for other jobs)
@ml_temp_resume_bp.route("/ml/job_resume/<job_id>", methods=["DELETE"])
@jwt_required()
def unlink_resume_from_job(job_id):
    email = get_jwt_identity()
    job = job_posts.find_one({"_id": ObjectId(job_id)})
    if not job or "resume_id" not in job:
        return jsonify({"msg": "Resume not found for this job"}), 404
    job_posts.update_one({"_id": ObjectId(job_id)}, {"$unset": {"resume_id": ""}})
    return jsonify({"msg": "Resume unlinked from this job"}), 200
