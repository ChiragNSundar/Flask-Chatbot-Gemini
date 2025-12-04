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
mongo_resume_upload_collection = None  # NEW
mongo_resume_parsed_collection = None  # NEW

try:
    mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    mongo_client.admin.command('ismaster')

    mongo_db = mongo_client[DB_NAME]

    # Collections
    mongo_profile_collection = mongo_db["profile_resume"]
    mongo_chat_collection = mongo_db["ai_chat"]
    mongo_resume_upload_collection = mongo_db["resume_upload"]  # Raw PDF Text
    mongo_resume_parsed_collection = mongo_db["resume_parsed"]  # AI Parsed JSON

    print("MongoDB connection successful.")

except ConnectionFailure as e:
    print(f"ERROR: MongoDB Connection Failed. {e}")
    mongo_client = None
except Exception as e:
    print(f"MongoDB Error: {e}")
    mongo_client = None

# Gemini Config
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')
else:
    model = None


# --- MODELS ---
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), default="New Chat")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    messages = db.relationship('Message', backref='conversation', cascade="all, delete-orphan")


class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation.id'), nullable=False)
    role = db.Column(db.String(10))
    content = db.Column(db.Text)
    image_data = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


with app.app_context():
    db.create_all()

# --- RESUME CONFIG ---
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
    {"field": "domain",
     "question": "Which **Industry or Domain** are you interested in? (e.g., Software, Finance, Healthcare)",
     "mandatory": True, "type": "text",
     "suggestions": ["Software Development", "Data Science", "Finance", "Marketing"]},
    {"field": "job_title", "question": "Target **Job Title**?", "mandatory": True, "type": "text", "suggestions": []},
    {"field": "skills", "question": "Top 3-5 **Skills**? (Type 'Suggest Skills' for AI help)", "mandatory": True,
     "type": "text", "suggestions": []},
    {"field": "summary", "question": "Professional **Summary**? (Type 'Generate' to see options, or type your own)",
     "mandatory": True, "type": "long_text", "suggestions": ["Generate Options", "Show Example"]},
    {"field": "critique",
     "question": "Profile complete! Review your profile on the right. Type 'Critique' for AI feedback or 'Submit' to finalize.",
     "mandatory": False, "type": "final", "suggestions": ["Critique", "Submit"]}
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


# --- LOGGING ---
def log_resume_interaction(session_id, user_text, ai_text, step_index, collected_data):
    if mongo_client is None: return
    if not ObjectId.is_valid(session_id): return

    oid = ObjectId(session_id)

    interaction = {
        'timestamp': datetime.utcnow(),
        'step_index': step_index,
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


# --- DYNAMIC SUGGESTIONS ---
def get_dynamic_suggestions(field, data):
    try:
        if field == "job_title":
            exp = data.get("experience_level", "Entry Level")
            dom = data.get("domain", "General")

            prompt = f"List 3 standard job titles for a '{exp}' professional in the '{dom}' industry. Output ONLY the titles separated by commas."
            response = model.generate_content(prompt)
            return [s.strip() for s in response.text.split(',') if s.strip()][:3]

        if field == "skills":
            job = data.get("job_title", "Professional")
            prompt = f"List 6 distinct, single technical or soft skills (e.g. Python, SQL, Communication) suitable for a '{job}'. Output ONLY the skills separated by commas."
            response = model.generate_content(prompt)
            return [s.strip() for s in response.text.split(',') if s.strip()][:6]

    except Exception as e:
        print(f"Suggestion Error: {e}")
        return []
    return []


# --- ROUTES ---
@app.route('/')
def home(): return render_template('chat.html')


@app.route('/resume')
def resume_page(): return render_template('resume.html')


# Chatbot API
@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    chats = Conversation.query.order_by(Conversation.created_at.desc()).all()
    return jsonify([{'id': c.id, 'title': c.title} for c in chats])


@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    last_chat = Conversation.query.order_by(Conversation.created_at.desc()).first()
    if last_chat and len(last_chat.messages) == 0:
        return jsonify({'id': last_chat.id, 'title': last_chat.title})
    new_chat = Conversation(title="New Chat")
    db.session.add(new_chat)
    db.session.commit()
    return jsonify({'id': new_chat.id, 'title': new_chat.title})


@app.route('/api/conversations/<int:chat_id>', methods=['DELETE'])
def delete_conversation(chat_id):
    chat = Conversation.query.get_or_404(chat_id)
    db.session.delete(chat)
    db.session.commit()
    return jsonify({'success': True})


@app.route('/api/conversations/<int:chat_id>/messages', methods=['GET'])
def get_messages(chat_id):
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
            print(f"Image Error: {e}")

    def generate():
        full_response = ""
        try:
            config = genai.GenerationConfig(temperature=temperature)
            response = model.generate_content(content_parts, stream=True, generation_config=config)
            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    yield f"data: {json.dumps({'text': chunk.text})}\n\n"

            with app.app_context():
                chat = Conversation.query.get(chat_id)
                if chat.title == "New Chat" and len(chat.messages) <= 1:
                    try:
                        title_resp = model.generate_content(f"Summarize in 3 words: {user_input}")
                        chat.title = title_resp.text.strip()
                    except:
                        pass
                bot_msg = Message(conversation_id=chat_id, role='model', content=full_response)
                db.session.add(bot_msg)
                db.session.commit()
                yield f"data: {json.dumps({'done': True, 'title': chat.title})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


# --- RESUME API ---

@app.route('/api/upload-resume', methods=['POST'])
def upload_resume():
    if 'file' not in request.files: return jsonify({'error': 'No file uploaded'}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({'error': 'No file selected'}), 400

    try:
        # 1. Generate unique resume_id
        resume_id = ObjectId()

        # 2. Extract Raw Text
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"

        # 3. Store Raw Data in 'resume_upload'
        if mongo_resume_upload_collection is not None:
            mongo_resume_upload_collection.insert_one({
                "_id": resume_id,
                "resume_id": resume_id,  # Redundant but explicit for queries
                "filename": file.filename,
                "raw_text_content": text,
                "timestamp": datetime.utcnow()
            })

        # 4. Parse with Gemini
        prompt = f"""
        Extract details from resume to JSON. Keys: "full_name", "email", "phone", "experience_level", "domain", "job_title", "skills", "summary".
        Text: {text[:4000]}
        """
        response = model.generate_content(prompt)
        cleaned_text = response.text.replace('```json', '').replace('```', '').strip()
        extracted_data = json.loads(cleaned_text)

        # 5. Store Parsed Data in 'resume_parsed'
        if mongo_resume_parsed_collection is not None:
            mongo_resume_parsed_collection.insert_one({
                "resume_id": resume_id,  # Linking ID
                "parsed_data": extracted_data,
                "timestamp": datetime.utcnow()
            })

        # 6. Return data + resume_id to frontend
        return jsonify({
            'success': True,
            'data': extracted_data,
            'resume_id': str(resume_id),  # Send ID as string
            'message': "I've analyzed your resume and stored the data."
        })
    except Exception as e:
        print(f"Upload Error: {e}")
        return jsonify({'error': 'Failed to process PDF'}), 500


@app.route('/api/resume-chat', methods=['POST'])
def resume_chat():
    data = request.json
    user_input = data.get('message', '').strip()
    collected_data = data.get('data', {})
    current_step_index = data.get('step', -1)
    session_id = data.get('session_id')
    if not session_id:
        session_id = str(ObjectId())

    # 1. Handle Special Commands
    if user_input.lower() == 'submit':
        ai_text = "Interview complete! Please review your details on the right and click the green 'Submit Profile' button to finish."
        log_resume_interaction(session_id, user_input, ai_text, current_step_index, collected_data)
        return jsonify({'response': ai_text, 'finished': True, 'data': collected_data, 'session_id': session_id})

    if user_input.lower() == 'critique' and collected_data.get('summary'):
        prompt = f"Critique the following resume profile for a {collected_data.get('job_title')}. Focus on the summary and skills. Profile: {collected_data}"
        try:
            ai_resp = model.generate_content(prompt)
            ai_text = f"**AI Critique:**\n\n{ai_resp.text}"
            log_resume_interaction(session_id, user_input, ai_text, current_step_index, collected_data)
            return jsonify({'response': ai_text, 'keep_step': True, 'question': RESUME_STEPS[-1]['question'],
                            'suggestions': RESUME_STEPS[-1]['suggestions'], 'session_id': session_id})
        except:
            return jsonify({'error': "Critique failed.", 'keep_step': True, 'session_id': session_id})

    if user_input.lower() == 'suggest skills' and collected_data.get('job_title'):
        prompt = f"Based on the job title '{collected_data.get('job_title')}' and existing skills '{collected_data.get('skills')}', suggest 3-5 highly relevant, modern skills that are missing. List them separated by a comma."
        try:
            ai_resp = model.generate_content(prompt)
            ai_text = f"**Suggested Skills:**\n\n{ai_resp.text}"
            log_resume_interaction(session_id, user_input, ai_text, current_step_index, collected_data)
            return jsonify({'response': ai_text, 'keep_step': True, 'question': RESUME_STEPS[5]['question'],
                            'suggestions': RESUME_STEPS[5]['suggestions'], 'session_id': session_id})
        except:
            return jsonify({'error': "Skill suggestion failed.", 'keep_step': True, 'session_id': session_id})

    if user_input.lower() == 'show example' and collected_data.get('job_title'):
        prompt = f"Provide a brief, strong example of a professional summary for a {collected_data.get('experience_level')} {collected_data.get('job_title')}."
        try:
            ai_resp = model.generate_content(prompt)
            ai_text = f"**Example Summary:**\n\n{ai_resp.text}"
            log_resume_interaction(session_id, user_input, ai_text, current_step_index, collected_data)
            return jsonify({'response': ai_text, 'keep_step': True, 'question': RESUME_STEPS[6]['question'],
                            'suggestions': RESUME_STEPS[6]['suggestions'], 'session_id': session_id})
        except:
            return jsonify({'error': "Example generation failed.", 'keep_step': True, 'session_id': session_id})

    # 2. Validation & Input Handling
    just_saved_summary = False
    if current_step_index != -1 and user_input:
        current_rule = RESUME_STEPS[current_step_index]
        error_msg = None

        if current_rule['field'] == 'full_name':
            if any(char.isdigit() for char in user_input):
                error_msg = "Name cannot contain numbers."
            elif len(user_input) < 2:
                error_msg = "Name is too short."
        elif current_rule['type'] == 'email' and not re.match(r"[^@]+@[^@]+\.[^@]+", user_input):
            error_msg = "Invalid email format."
        elif current_rule['type'] == 'phone' and not re.search(r"\d{10}", user_input):
            error_msg = "Invalid phone (10+ digits)."

        if error_msg:
            log_resume_interaction(session_id, user_input, error_msg, current_step_index, collected_data)
            return jsonify({'error': error_msg, 'keep_step': True, 'session_id': session_id})

        if current_rule['field'] == 'summary' and 'generate' in user_input.lower():
            try:
                prompt = f"Write 2 distinct professional resume summaries for a {collected_data.get('job_title')} with skills {collected_data.get('skills')}. Return ONLY the summaries separated by '|||'. Do not include labels like 'Option 1'."
                ai_resp = model.generate_content(prompt)

                raw_text = ai_resp.text
                options = [opt.strip() for opt in raw_text.split('|||') if opt.strip()]

                ai_text = "Here are two summary options. Click one to auto-fill."
                log_resume_interaction(session_id, user_input, ai_text + f" [Options: {options}]", current_step_index,
                                       collected_data)

                return jsonify(
                    {'response': ai_text, 'suggestions': options, 'keep_step': True, 'session_id': session_id})
            except:
                return jsonify({'error': "Generation failed.", 'keep_step': True, 'session_id': session_id})

        collected_data[current_rule['field']] = user_input
        if current_rule['field'] == 'summary':
            just_saved_summary = True

    # 3. Determine Next Step
    next_step_index = find_next_step(collected_data)

    # 4. Formulate Response & Suggestions
    if next_step_index == -1:
        ai_text = "Profile complete! Please review and submit."
        if just_saved_summary:
            ai_text = "I've updated your summary. Please review it for any placeholders.\n\n" + ai_text

        log_resume_interaction(session_id, user_input, ai_text, current_step_index, collected_data)
        return jsonify({'response': ai_text, 'finished': True, 'data': collected_data, 'session_id': session_id})

    next_rule = RESUME_STEPS[next_step_index]
    ai_text = next_rule['question']

    if just_saved_summary:
        ai_text = "I've updated your summary. Please review it for any placeholders.\n\n" + ai_text

    dynamic_suggestions = next_rule['suggestions']
    if next_rule['field'] in ['job_title', 'skills']:
        generated = get_dynamic_suggestions(next_rule['field'], collected_data)
        if generated: dynamic_suggestions = generated

    ui_response_text = ""
    if current_step_index == -1 and not user_input:
        if collected_data.get('full_name'):
            ai_text = f"Welcome back, **{collected_data['full_name']}**! Resuming your profile. " + ai_text
        else:
            ai_text = "Hello! Let's build your resume. " + ai_text
        ui_response_text = ai_text

    log_resume_interaction(session_id, user_input, ai_text, next_step_index, collected_data)

    return jsonify({
        'response': ui_response_text,
        'next_step': next_step_index,
        'question': next_rule['question'],
        'suggestions': dynamic_suggestions,
        'data': collected_data,
        'session_id': session_id
    })


@app.route('/api/submit-resume', methods=['POST'])
def submit_resume():
    if mongo_client is None:
        return jsonify({'error': 'MongoDB connection failed.'}), 500

    try:
        new_profile = request.json

        # 1. Chat Log Linking
        session_id_str = new_profile.pop('resume_session_id', None)
        if session_id_str and ObjectId.is_valid(session_id_str):
            new_profile['chat_session_id'] = ObjectId(session_id_str)
        else:
            new_profile['chat_session_id'] = None

        # 2. PDF Upload Linking
        upload_id_str = new_profile.pop('upload_resume_id', None)
        if upload_id_str and ObjectId.is_valid(upload_id_str):
            new_profile['resume_upload_id'] = ObjectId(upload_id_str)  # Links to resume_upload & resume_parsed
        else:
            new_profile['resume_upload_id'] = None

        new_profile['submitted_at'] = datetime.utcnow()
        mongo_profile_collection.insert_one(new_profile)

        return jsonify({'status': 'success', 'message': 'Profile saved to MongoDB'})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({'error': 'Error saving to MongoDB'}), 500


if __name__ == '__main__':
    app.run(debug=True)