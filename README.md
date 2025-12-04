# 🤖 Gemini AI Chatbot

A powerful, full-stack AI application built with **Python Flask** and **Google's Gemini API**. This project provides an advanced, multimodal chatbot experience with persistent memory and real-time streaming.

## ✨ Features

### 💬 Advanced Chatbot
*   **⚡ Real-time Streaming:** Text responses appear instantly as they are generated, providing a smooth, typewriter-like user experience.
*   **💾 Persistent Memory:** Conversations are saved and maintained across sessions using a **SQLite** database, ensuring context is maintained.
*   **📸 Multimodal:** The chatbot can process and understand context from uploaded images, allowing users to ask questions about visual content.
*   **🎙️ Voice Interaction (STT):** Built-in Speech-to-Text allows for hands-free interaction and voice commands.
*   **🎛️ Controls:** Users can adjust AI creativity by modifying the **Temperature** setting and stop ongoing generation mid-stream.

## 🛠️ Tech Stack

*   **Backend:** Python, Flask, **SQLAlchemy (SQLite)**
*   **AI Engine:** Google Gemini 2.0 Flash (via `google-generativeai`)
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript
*   **Utilities:** Pillow (Image processing), Dotenv, Regex (Validation)

## 🚀 Installation & Setup

1.  **Clone the repository** (or download the files):
    ```bash
    git clone https://github.com/yourusername/gemini-chatbot.git
    cd gemini-chatbot
    ```

2.  **Install Dependencies:**
    Make sure you have Python installed, then run:
    ```bash
    pip install -r requirements.txt
    ```
    *(Note: Your `requirements.txt` should contain dependencies like `Flask`, `SQLAlchemy`, `google-genai`, `python-dotenv`, `Pillow`, etc.)*

3.  **Configure API Key:**
    *   Create a file named `.env` in the root directory.
    *   Add your Google Gemini API key inside:
    ```ini
    GOOGLE_API_KEY=your_actual_api_key_here
    ```

4.  **Run the Application:**
    ```bash
    python app.py
    ```

5.  **Open in Browser:**
    Go to `http://127.0.0.1:5000`.

## 📂 Project Structure

```text
/project-root
├── app.py               # Main Flask backend (Chatbot logic)
├── chat_history.db      # SQLite database (auto-created for chat history)
├── .env                 # API Key configuration
├── requirements.txt     # Python dependencies
├── static/
│   ├── style.css        # Global styling (Glassmorphism, Layouts)
│   └── script.js        # Frontend chat logic (streaming, multimodal, memory)
└── templates/
    └── chat.html        # Main Chatbot Interface
