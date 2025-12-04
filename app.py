import os
import json
import base64
import io
import re
from datetime import datetime
from PIL import Image
import PyPDF2
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import google.generativeai as genai

# --- MongoDB Imports ---
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure
from bson.objectid import ObjectId

# -----------------------

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(basedir, 'templates')
static_dir = os.path.join(basedir, 'static')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# --- SQLite/SQLAlchemy Configuration (For Main Chatbot) ---
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_history.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# --- MongoDB Configuration ---
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME = "main_db"

mongo_client = None
mongo_profile_collection = None
mongo_chat_collection = None
mongo_resume_upload_collection = None
mongo_resume_parsed_collection = None

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command('ismaster')

    mongo_db = mongo_client[DB_NAME]
    mongo_profile_collection = mongo_db["profile_resume"]
    mongo_chat_collection = mongo_db["ai_chat"]
    mongo_resume_upload_collection = mongo_db["resume_upload"]
    mongo_resume_parsed_collection = mongo_db["resume_parsed"]
    print("MongoDB connection successful.")

except ConnectionFailure as e:
    print(f"ERROR: MongoDB Connection Failed. {e}")
except Exception as e:
    print(f"MongoDB Error: {e}")

# Gemini Config
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
else:
    model = None


# --- MODELS (SQLite for Chatbot) ---
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), default="New Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='conversation', cascade="all, delete-orphan")


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    role = db.Column(db.String(10))  # 'user' or 'model'
    content = db.Column(db.Text)
    image_data = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()

# --- RESUME HELPERS ---
RESUME_STEPS = [
    {"field": "full_name",
     "question": "Let's build your profile. **Upload your Resume (PDF)** or tell me your **Full Name**.",
     "mandatory": True, "type": "text", "suggestions": []},
    {"field": "email", "question": "What is your **Email Address**?", "mandatory": True, "type": "email",
     "suggestions": []},
    {"field": "phone", "question": "What is your **Phone Number**?", "mandatory": True, "type": "phone",
     "suggestions": []},
    {"field": "experience_level", "question": "What is your **Experience Level**?", "mandatory": True,
     "type": "selection", "suggestions": ["Intern", "Entry Level", "Mid Level", "Senior", "Lead"]},
    {"field": "domain", "question": "Which **Industry or Domain** are you interested in?", "mandatory": True,
     "type": "text", "suggestions": ["Software Development", "Data Science", "Finance", "Marketing"]},
    {"field": "job_title", "question": "Target **Job Title**?", "mandatory": True, "type": "text", "suggestions": []},
    {"field": "skills", "question": "Top 3-5 **Skills**? (Type 'Suggest Skills' for AI help)", "mandatory": True,
     "type": "text", "suggestions": []},
    {"field": "summary", "question": "Professional **Summary**? (Type 'Generate' to see options)", "mandatory": True,
     "type": "long_text", "suggestions": ["Generate Options", "Show Example"]},
    {"field": "critique", "question": "Profile complete! Review your profile. Check ATS Score or Submit.",
     "mandatory": False, "type": "final", "suggestions": ["Check ATS Score", "Submit"]}
]


def find_next_step(current_data):
    for i, step in enumerate(RESUME_STEPS):
        field = step['field']
        if step['mandatory'] and not current_data.get(field):
            return i
        if step['field'] == 'critique':
            if all(current_data.get(s['field']) for s in RESUME_STEPS if s['mandatory']):
                return i
    return -1


def log_resume_interaction(session_id, user_text, ai_text, step_index, collected_data):
    if mongo_client is None: return
    if not ObjectId.is_valid(session_id): return
    oid = ObjectId(session_id)

    interaction = {
        'timestamp': datetime.utcnow(),
        'step': step_index,
        'user_said': user_text,
        'ai_replied': ai_text,
        'snapshot': collected_data
    }
    mongo_chat_collection.update_one(
        {'_id': oid},
        {
            '$push': {'interactions': interaction},
            '$setOnInsert': {'created_at': datetime.utcnow()}
        },
        upsert=True
    )


def get_dynamic_suggestions(field, data):
    try:
        if field == "job_title":
            prompt = f"List 3 standard job titles for a '{data.get('experience_level')}' professional in '{data.get('domain')}'. Output comma-separated."
            response = model.generate_content(prompt)
            return [s.strip() for s in response.text.split(',') if s.strip()][:3]
        if field == "skills":
            prompt = f"List 6 distinct single skills for a '{data.get('job_title')}'. Output comma-separated."
            response = model.generate_content(prompt)
            return [s.strip() for s in response.text.split(',') if s.strip()][:6]
    except:
        return []
    return []


# --- APP ROUTES ---

@app.route('/')
def home(): return render_template('chat.html')


@app.route('/resume')
def resume_page(): return render_template('resume.html')


# --- CHATBOT API (SQLITE) ---

@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    chats = Conversation.query.order_by(Conversation.created_at.desc()).all()
    return jsonify([{'id': c.id, 'title': c.title} for c in chats])


@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    # Reuse empty chat if exists
    last_chat = Conversation.query.order_by(Conversation.created_at.desc()).first()
    if last_chat and len(last_chat.messages) == 0:
        return jsonify({'id': last_chat.id, 'title': last_chat.title})

    new_chat = Conversation(title="New Chat")
    db.session.add(new_chat)
    db.session.commit()
    return jsonify({'id': new_chat.id, 'title': new_chat.title})


@app.route('/api/conversations/<int:chat_id>', methods=['DELETE'])
def delete_conv(chat_id):
    chat = Conversation.query.get_or_404(chat_id)
    db.session.delete(chat)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/conversations/<int:chat_id>/messages', methods=['GET'])
def get_msgs(chat_id):
    messages = Message.query.filter_by(conversation_id=chat_id).order_by(Message.timestamp).all()
    return jsonify([{'role': m.role, 'content': m.content, 'image': m.image_data} for m in messages])


@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message')
    image_b64 = data.get('image')
    chat_id = data.get('chat_id')
    temperature = float(data.get('temperature', 0.7))

    if not chat_id: return jsonify({'error': "No chat ID"}), 400

    # Save User Message
    user_msg = Message(conversation_id=chat_id, role='user', content=user_input, image_data=image_b64)
    db.session.add(user_msg)
    db.session.commit()

    content_parts = [user_input]
    if image_b64:
        try:
            if "base64," in image_b64: image_b64 = image_b64.split("base64,")[1]
            img_data = base64.b64decode(image_b64)
            image = Image.open(io.BytesIO(img_data))
            content_parts.append(image)
        except Exception as e:
            print(e)

    def generate():
        full_response = ""
        try:
            config = genai.GenerationConfig(temperature=temperature)
            response = model.generate_content(content_parts, stream=True, generation_config=config)

            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield f"data: {json.dumps({'text': chunk.text})}\n\n"

            # Save Bot Message inside app context
            with app.app_context():
                bot_msg = Message(conversation_id=chat_id, role='model', content=full_response)
                db.session.add(bot_msg)

                # Rename chat if first message
                chat_obj = Conversation.query.get(chat_id)
                if chat_obj.title == "New Chat":
                    try:
                        title_resp = model.generate_content(f"Summarize in 3 words: {user_input}")
                        chat_obj.title = title_resp.text.strip()
                    except:
                        pass

                db.session.commit()
                yield f"data: {json.dumps({'done': True, 'title': chat_obj.title})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# --- RESUME API (MongoDB) ---

@app.route('/api/upload-resume', methods=['POST'])
def upload_resume():
    if 'file' not in request.files: return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No file selected'}), 400

    try:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"

        resume_id = ObjectId()
        if mongo_resume_upload_collection is not None:
            mongo_resume_upload_collection.insert_one({
                "_id": resume_id, "resume_id": resume_id, "filename": file.filename,
                "raw_text_content": text, "timestamp": datetime.utcnow()
            })

        prompt = f"""Extract details to JSON. Keys: full_name, email, phone, experience_level, domain, job_title, skills, summary. Text: {text[:4000]}"""
        response = model.generate_content(prompt)
        cleaned_text = response.text.replace('```json', '').replace('```', '').strip()
        extracted_data = json.loads(cleaned_text)

        if mongo_resume_parsed_collection is not None:
            mongo_resume_parsed_collection.insert_one({
                "resume_id": resume_id, "parsed_data": extracted_data, "timestamp": datetime.utcnow()
            })

        return jsonify({'success': True, 'data': extracted_data, 'resume_id': str(resume_id), 'message': "Analyzed."})
    except Exception as e:
        return jsonify({'error': 'Failed to process PDF'}), 500


@app.route('/api/resume-chat', methods=['POST'])
def resume_chat():
    data = request.json
    user_input = data.get('message', '').strip()
    collected_data = data.get('data', {})
    current_step_index = data.get('step', -1)
    session_id = data.get('session_id') or str(ObjectId())

    # Special Commands
    if user_input.lower() == 'check ats score':
        prompt = f"ATS Scan. Profile: {collected_data}. Score (0-100), 3 missing keywords, feedback."
        try:
            ai_resp = model.generate_content(prompt)
            ai_text = f"**ATS Analysis:**\n\n{ai_resp.text}"

            next_step_idx = find_next_step(collected_data)
            if next_step_idx != -1:
                next_rule = RESUME_STEPS[next_step_idx]
                ai_text += f"\n\n---\n**Resuming:** {next_rule['question']}"
                sugs = next_rule['suggestions']
                if next_rule['field'] in ['job_title', 'skills']:
                    dyn = get_dynamic_suggestions(next_rule['field'], collected_data)
                    if dyn: sugs = dyn
                log_resume_interaction(session_id, user_input, ai_text, next_step_idx, collected_data)
                return jsonify(
                    {'response': ai_text, 'keep_step': True, 'question': next_rule['question'], 'suggestions': sugs,
                     'session_id': session_id, 'next_step': next_step_idx})
            else:
                log_resume_interaction(session_id, user_input, ai_text, current_step_index, collected_data)
                return jsonify({'response': ai_text, 'keep_step': True, 'question': RESUME_STEPS[-1]['question'],
                                'suggestions': RESUME_STEPS[-1]['suggestions'], 'session_id': session_id})
        except:
            return jsonify({'error': "ATS failed.", 'keep_step': True, 'session_id': session_id})

    if user_input.lower() == 'submit':
        ai_text = "Interview complete! Please click the green 'Submit Profile' button."
        log_resume_interaction(session_id, user_input, ai_text, current_step_index, collected_data)
        return jsonify({'response': ai_text, 'finished': True, 'data': collected_data, 'session_id': session_id})

    # Validation
    just_saved_summary = False
    if current_step_index != -1 and user_input:
        current_rule = RESUME_STEPS[current_step_index]
        error_msg = None
        if current_rule['field'] == 'full_name' and any(char.isdigit() for char in user_input):
            error_msg = "Name cannot contain numbers."
        elif current_rule['type'] == 'email' and not re.match(r"[^@]+@[^@]+\.[^@]+", user_input):
            error_msg = "Invalid email format."
        elif current_rule['type'] == 'phone' and not re.search(r"\d{10}", user_input):
            error_msg = "Invalid phone."

        if error_msg:
            log_resume_interaction(session_id, user_input, error_msg, current_step_index, collected_data)
            return jsonify({'error': error_msg, 'keep_step': True, 'session_id': session_id})

        if current_rule['field'] == 'summary' and 'generate' in user_input.lower():
            try:
                prompt = f"Write 2 summaries for {collected_data.get('job_title')}, skills {collected_data.get('skills')}. Separate by '|||'. No headers."
                ai_resp = model.generate_content(prompt)
                raw_text = ai_resp.text
                options = [opt.strip() for opt in raw_text.split('|||') if opt.strip()]
                ai_text = "Here are two summary options. Click one to auto-fill."
                log_resume_interaction(session_id, user_input, ai_text + f" {options}", current_step_index,
                                       collected_data)
                return jsonify(
                    {'response': ai_text, 'suggestions': options, 'keep_step': True, 'session_id': session_id})
            except:
                return jsonify({'error': "Generation failed.", 'keep_step': True, 'session_id': session_id})

        collected_data[current_rule['field']] = user_input
        if current_rule['field'] == 'summary': just_saved_summary = True

    # Next Step
    next_step_index = find_next_step(collected_data)

    if next_step_index == -1:
        ai_text = "Profile complete! Please review and submit."
        if just_saved_summary: ai_text = "Summary updated.\n\n" + ai_text
        log_resume_interaction(session_id, user_input, ai_text, current_step_index, collected_data)
        return jsonify({'response': ai_text, 'finished': True, 'data': collected_data, 'session_id': session_id})

    next_rule = RESUME_STEPS[next_step_index]
    ai_text = next_rule['question']
    if just_saved_summary: ai_text = "Summary updated.\n\n" + ai_text

    dynamic_suggestions = next_rule['suggestions']
    if next_rule['field'] in ['job_title', 'skills']:
        generated = get_dynamic_suggestions(next_rule['field'], collected_data)
        if generated: dynamic_suggestions = generated

    ui_response_text = ""
    if current_step_index == -1 and not user_input:
        if collected_data.get('full_name'):
            ai_text = f"Welcome back, **{collected_data['full_name']}**! Resuming... " + ai_text
        else:
            ai_text = "Hello! Let's build your resume. " + ai_text
        ui_response_text = ai_text

    log_resume_interaction(session_id, user_input, ai_text, next_step_index, collected_data)

    return jsonify({'response': ui_response_text, 'next_step': next_step_index, 'question': next_rule['question'],
                    'suggestions': dynamic_suggestions, 'data': collected_data, 'session_id': session_id})


@app.route('/api/submit-resume', methods=['POST'])
def submit_resume():
    if mongo_client is None: return jsonify({'error': 'DB Error'}), 500
    try:
        new_profile = request.json
        session_id_str = new_profile.pop('resume_session_id', None)
        upload_id_str = new_profile.pop('upload_resume_id', None)

        new_profile['chat_session_id'] = ObjectId(session_id_str) if session_id_str and ObjectId.is_valid(
            session_id_str) else None
        new_profile['resume_upload_id'] = ObjectId(upload_id_str) if upload_id_str and ObjectId.is_valid(
            upload_id_str) else None
        new_profile['submitted_at'] = datetime.utcnow()

        mongo_profile_collection.insert_one(new_profile)
        return jsonify({'status': 'success', 'message': 'Profile saved to MongoDB'})
    except Exception as e:
        print(e)
        return jsonify({'error': 'Error saving'}), 500


if __name__ == '__main__':
    app.run(debug=True)