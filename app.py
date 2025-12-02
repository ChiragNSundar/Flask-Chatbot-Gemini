import os
import json
import base64
import io
from datetime import datetime
from PIL import Image
from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# --- CONFIGURATION ---
basedir = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)

# Database Config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'chat_history.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Gemini Config
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY:
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash')  # Use 2.0 or 1.5-flash
else:
    model = None


# --- DATABASE MODELS ---
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
    image_data = db.Column(db.Text, nullable=True)  # Base64 string
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)


# Create DB
with app.app_context():
    db.create_all()


# --- ROUTES ---

@app.route('/')
def home():
    return render_template('chat.html')


# 1. Get All Conversations (Sidebar)
@app.route('/api/conversations', methods=['GET'])
def get_conversations():
    chats = Conversation.query.order_by(Conversation.created_at.desc()).all()
    return jsonify([{'id': c.id, 'title': c.title} for c in chats])


# 2. Create New Conversation
@app.route('/api/conversations', methods=['POST'])
def create_conversation():
    new_chat = Conversation(title="New Chat")
    db.session.add(new_chat)
    db.session.commit()
    return jsonify({'id': new_chat.id, 'title': new_chat.title})


# 3. Delete Conversation
@app.route('/api/conversations/<int:chat_id>', methods=['DELETE'])
def delete_conversation(chat_id):
    chat = Conversation.query.get_or_404(chat_id)
    db.session.delete(chat)
    db.session.commit()
    return jsonify({'success': True})


# 4. Get Messages for a specific Chat
@app.route('/api/conversations/<int:chat_id>/messages', methods=['GET'])
def get_messages(chat_id):
    messages = Message.query.filter_by(conversation_id=chat_id).order_by(Message.timestamp).all()
    return jsonify([{
        'role': m.role,
        'content': m.content,
        'image': m.image_data
    } for m in messages])


# 5. THE MAIN CHAT ROUTE (STREAMING)
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_input = data.get('message')
    image_b64 = data.get('image')  # Base64 string
    chat_id = data.get('chat_id')
    temperature = float(data.get('temperature', 0.7))

    if not chat_id:
        return jsonify({'error': "No chat ID provided"}), 400

    # Save User Message to DB
    user_msg = Message(conversation_id=chat_id, role='user', content=user_input, image_data=image_b64)
    db.session.add(user_msg)
    db.session.commit()

    # Prepare Content for Gemini
    content_parts = [user_input]
    if image_b64:
        try:
            # Clean base64 string
            if "base64," in image_b64:
                image_b64 = image_b64.split("base64,")[1]
            img_data = base64.b64decode(image_b64)
            image = Image.open(io.BytesIO(img_data))
            content_parts.append(image)
        except Exception as e:
            print(f"Image Error: {e}")

    # Generator for Streaming
    def generate():
        full_response = ""
        try:
            config = genai.GenerationConfig(temperature=temperature)
            # We use generate_content (stream=True) instead of chat_session for simplicity with images
            response = model.generate_content(
                content_parts,
                stream=True,
                generation_config=config
            )

            for chunk in response:
                if chunk.text:
                    full_response += chunk.text
                    # Yield data in SSE format
                    yield f"data: {json.dumps({'text': chunk.text})}\n\n"

            # After streaming is done, save Bot Message to DB
            with app.app_context():
                # Update Title if it's the first message
                chat = Conversation.query.get(chat_id)
                if chat.title == "New Chat":
                    # Generate a short title
                    title_prompt = f"Summarize this in 3-4 words: {user_input}"
                    try:
                        title_resp = model.generate_content(title_prompt)
                        chat.title = title_resp.text.strip()
                    except:
                        pass

                bot_msg = Message(conversation_id=chat_id, role='model', content=full_response)
                db.session.add(bot_msg)
                db.session.commit()

                # Send a final 'done' event
                yield f"data: {json.dumps({'done': True, 'title': chat.title})}\n\n"

        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return Response(stream_with_context(generate()), mimetype='text/event-stream')


if __name__ == '__main__':
    app.run(debug=True)