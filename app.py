from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from pdfminer.high_level import extract_text
import os
from flask_cors import CORS
from werkzeug.utils import secure_filename  # NEW IMPORT
import fitz

app = Flask(__name__)
CORS(app)

# MongoDB setup
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise Exception("MONGO_URI environment variable not set")

client = MongoClient(mongo_uri)
db = client["job_scraping_db"]
resumes = db["resumes"]

# Ensure upload folder exists
if not os.path.exists('uploads'):
    os.makedirs('uploads')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'pdf'  # Simplified check

@app.route('/')
def home():
    return "Flask app is running!"

@app.route("/resumes", methods=["GET"])
def get_resumes():
    data = list(resumes.find({}))
    # Convert ObjectId to string for JSON serialization
    for resume in data:
        resume["_id"] = str(resume["_id"])
    return jsonify(data)


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
        safe_filename = secure_filename(file.filename)
        filepath = os.path.join("uploads", safe_filename)
        file.save(filepath)

        # Use PyMuPDF for text extraction
        text = extract_text_pymupdf(filepath)
        resume_data = {
            "filename": safe_filename,
            "text": text
        }
        result = resumes.insert_one(resume_data)
        resume_id = str(result.inserted_id)
        return jsonify({"msg": "File uploaded!", "id": resume_id}), 201

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"msg": f"Server error: {str(e)}"}), 500

    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

@app.route("/resumes/<id>", methods=["PUT"])
def update_resume(id):
    updated_data = request.json
    resumes.update_one({"_id": ObjectId(id)}, {"$set": updated_data})
    return jsonify({"msg": "Resume updated successfully!"})

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
