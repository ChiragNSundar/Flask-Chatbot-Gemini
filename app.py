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

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))
template_dir = os.path.join(basedir, 'templates')
static_dir = os.path.join(basedir, 'static')
PROFILES_FILE = os.path.join(basedir, 'profiles.json')

app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

# Database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_history.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

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
    {"field": "job_title", "question": "Target **Job Title**?", "mandatory": True, "type": "text",
     "suggestions": ["Data Scientist", "Full Stack Dev", "Product Manager"]},
    {"field": "skills", "question": "Top 3-5 **Skills**?", "mandatory": True, "type": "text",
     "suggestions": ["Python, SQL, ML", "React, Node, AWS"]},
    {"field": "summary", "question": "Professional **Summary**? (Type 'Generate' to see options, or type your own)",
     "mandatory": True, "type": "long_text", "suggestions": ["Generate Options"]}
]


def find_next_step(current_data):
    """Finds the index of the first mandatory field that is empty."""
    for i, step in enumerate(RESUME_STEPS):
        field = step['field']
        if step['mandatory'] and not current_data.get(field):
            return i
    return -1


# --- ROUTES ---
@app.route('/')
def home(): return render_template('chat.html')


@app.route('/resume')
def resume_page(): return render_template('resume.html')


# ... (Existing /api/conversations and /chat routes remain the same) ...
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
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"

        prompt = f"""
        Extract details from resume to JSON. Keys: "full_name", "email", "phone", "experience_level", "job_title", "skills", "summary".
        Text: {text[:4000]}
        """
        response = model.generate_content(prompt)
        cleaned_text = response.text.replace('```json', '').replace('```', '').strip()
        extracted_data = json.loads(cleaned_text)

        return jsonify({
            'success': True,
            'data': extracted_data,
            'message': "I've analyzed your resume."
        })
    except Exception as e:
        return jsonify({'error': 'Failed to process PDF'}), 500


@app.route('/api/resume-chat', methods=['POST'])
def resume_chat():
    data = request.json
    user_input = data.get('message', '').strip()
    collected_data = data.get('data', {})
    current_step_index = data.get('step', -1)

    # 1. Validation & Input Handling
    if current_step_index != -1 and user_input:
        current_rule = RESUME_STEPS[current_step_index]

        # Name Validation: No numbers + Min length
        if current_rule['field'] == 'full_name':
            if any(char.isdigit() for char in user_input):
                return jsonify({'error': "Name cannot contain numbers.", 'keep_step': True})
            if len(user_input) < 2:
                return jsonify({'error': "Name is too short. Please enter your full name.", 'keep_step': True})

        if current_rule['type'] == 'email' and not re.match(r"[^@]+@[^@]+\.[^@]+", user_input):
            return jsonify({'error': "Invalid email format.", 'keep_step': True})

        if current_rule['type'] == 'phone' and not re.search(r"\d{10}", user_input):
            return jsonify({'error': "Invalid phone (10+ digits).", 'keep_step': True})

        # --- MODIFIED: Summary Generation Logic ---
        if current_rule['field'] == 'summary' and 'generate' in user_input.lower():
            try:
                # Request 2 options and instruct to use placeholders
                prompt = f"Write 2 distinct professional resume summaries (separated by |) for a {collected_data.get('job_title')} with skills {collected_data.get('skills')}. Use placeholders like <Company Name> or <Specific Project> for generic parts."
                ai_resp = model.generate_content(prompt)
                options = [opt.strip() for opt in ai_resp.text.split('|') if opt.strip()]

                # New instruction message for the user
                new_response = "Here are two summary options. Click on the one you prefer, then review it carefully. **Replace any generic text** (like <Company Name> or <Role>) with your specific details before submitting."

                return jsonify({
                    'response': new_response,
                    'suggestions': options,
                    'keep_step': True
                })
            except:
                return jsonify({'error': "Generation failed. Please type your summary.", 'keep_step': True})
        # --- END MODIFIED LOGIC ---

        collected_data[current_rule['field']] = user_input

    # 2. Determine Next Step
    next_step_index = find_next_step(collected_data)

    # 3. Formulate Response
    if next_step_index == -1:
        return jsonify(
            {'response': "Profile complete! Please review and submit.", 'finished': True, 'data': collected_data})

    next_rule = RESUME_STEPS[next_step_index]

    response_text = ""
    if current_step_index == -1 and not user_input:
        response_text = "Hello! Let's build your resume."

    return jsonify({
        'response': response_text,
        'next_step': next_step_index,
        'question': next_rule['question'],
        'suggestions': next_rule['suggestions'],
        'data': collected_data
    })


@app.route('/api/submit-resume', methods=['POST'])
def submit_resume():
    try:
        new_profile = request.json
        if not new_profile:
            return jsonify({'error': 'No data provided'}), 400

        # --- SERVER SIDE VALIDATION ---
        required_fields = ["full_name", "email", "phone", "experience_level", "job_title", "skills", "summary"]
        missing = [field for field in required_fields if not new_profile.get(field)]

        if missing:
            return jsonify({'error': f"Missing mandatory fields: {', '.join(missing)}"}), 400
        # ------------------------------

        # Add timestamp
        new_profile['submitted_at'] = datetime.utcnow().isoformat()

        # Load existing data
        profiles = []
        if os.path.exists(PROFILES_FILE):
            try:
                with open(PROFILES_FILE, 'r') as f:
                    content = f.read()
                    if content.strip():
                        profiles = json.loads(content)
            except json.JSONDecodeError:
                profiles = []

        profiles.append(new_profile)

        with open(PROFILES_FILE, 'w') as f:
            json.dump(profiles, f, indent=4)

        return jsonify({'status': 'success', 'message': 'Profile saved to profiles.json'})

    except Exception as e:
        print(f"Error saving profile: {e}")
        return jsonify({'error': 'Internal Server Error while saving'}), 500


if __name__ == '__main__':
    app.run(debug=True)