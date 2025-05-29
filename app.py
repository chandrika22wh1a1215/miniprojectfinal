from flask import Flask, request, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
from pdfminer.high_level import extract_text
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# CHANGE: Use environment variable for MongoDB URI
mongo_uri = os.getenv("MONGO_URI")
if not mongo_uri:
    raise Exception("MONGO_URI environment variable not set")

client = MongoClient(mongo_uri)
db = client["job_scraping_db"]
resumes = db["resumes"]

if not os.path.exists('uploads'):
    os.makedirs('uploads')

@app.route('/')
def home():
    return "Flask app is running!"

@app.route("/resumes", methods=["GET"])
def get_resumes():
    data = list(resumes.find({}, {"_id": 0}))
    return jsonify(data)

@app.route("/upload_resume", methods=["POST"])
def upload_resume():
    if 'file' not in request.files:
        return jsonify({"msg": "No file part"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"msg": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = os.path.join("uploads", file.filename)
        file.save(filename)

        try:
            text = extract_text(filename)
            resume_data = {
                "filename": file.filename,
                "text": text
            }
            resumes.insert_one(resume_data)
        except Exception as e:
            return jsonify({"msg": f"Error extracting text from PDF: {str(e)}"}), 500
        finally:
            os.remove(filename)

        return jsonify({"msg": "Resume uploaded and processed successfully!"}), 201
    else:
        return jsonify({"msg": "Invalid file format. Only PDFs are allowed."}), 400

@app.route("/resumes/<id>", methods=["PUT"])
def update_resume(id):
    updated_data = request.json
    resumes.update_one({"_id": ObjectId(id)}, {"$set": updated_data})
    return jsonify({"msg": "Resume updated successfully!"})

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'pdf'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0")
