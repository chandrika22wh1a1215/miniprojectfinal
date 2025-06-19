from flask import Blueprint, request, jsonify, send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from bson.objectid import ObjectId
from bson.binary import Binary
from datetime import datetime
from werkzeug.utils import secure_filename
import io
from db import db

ml_temp_resume_bp = Blueprint('ml_temp_resume_bp', __name__)
ml_temp_resumes = db["ml_temp_resumes"]

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'

# 1. Upload ML-generated PDF resume (temporarily)
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
    temp_resume = {
        "user_email": email,
        "job_id": request.form.get("job_id"),  # job_id for job-specific resume
        "filename": secure_filename(file.filename),
        "pdf_data": Binary(pdf_data),
        "created_at": datetime.utcnow()
    }
    result = ml_temp_resumes.insert_one(temp_resume)
    return jsonify({"msg": "ML resume uploaded temporarily", "id": str(result.inserted_id)}), 201

# 2. List all temporary ML resumes for the user (optional for admin/debug)
@ml_temp_resume_bp.route("/ml/temp_resumes", methods=["GET"])
@jwt_required()
def get_temp_ml_resumes():
    email = get_jwt_identity()
    resumes_list = list(ml_temp_resumes.find({"user_email": email}))
    for r in resumes_list:
        r["_id"] = str(r["_id"])
        if "job_id" in r and r["job_id"]:
            r["job_id"] = str(r["job_id"])
        del r["pdf_data"]  # Don't send binary data in the list
    return jsonify(resumes_list), 200

# 3. Get resume by job_id (for job-matching page)
@ml_temp_resume_bp.route("/ml/job_resume/<job_id>", methods=["GET"])
@jwt_required()
def get_job_resume(job_id):
    email = get_jwt_identity()
    resume = ml_temp_resumes.find_one({"user_email": email, "job_id": job_id})
    if not resume:
        return jsonify({"msg": "Resume not found for this job"}), 404
    return jsonify({
        "resume_id": str(resume["_id"]),
        "download_link": f"/ml/temp_resumes/{resume['_id']}/download"
    }), 200

# 4. Download/view a specific temporary ML resume (by resume_id)
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
        as_attachment=True  # Always prompt download
    )

# 5. Reject (delete) a temporary ML resume (by resume_id)
@ml_temp_resume_bp.route("/ml/temp_resumes/<resume_id>", methods=["DELETE"])
@jwt_required()
def reject_ml_resume(resume_id):
    email = get_jwt_identity()
    try:
        result = ml_temp_resumes.delete_one({"_id": ObjectId(resume_id), "user_email": email})
    except Exception:
        return jsonify({"msg": "Invalid resume ID"}), 400
    if result.deleted_count == 0:
        return jsonify({"msg": "Resume not found"}), 404
    return jsonify({"msg": "Resume rejected and deleted"}), 200

# 6. Optionally: Reject (delete) by job_id for job-matching UX
@ml_temp_resume_bp.route("/ml/job_resume/<job_id>", methods=["DELETE"])
@jwt_required()
def reject_resume_by_job(job_id):
    email = get_jwt_identity()
    result = ml_temp_resumes.delete_one({"user_email": email, "job_id": job_id})
    if result.deleted_count == 0:
        return jsonify({"msg": "Resume not found for this job"}), 404
    return jsonify({"msg": "Resume rejected and deleted for this job"}), 200
