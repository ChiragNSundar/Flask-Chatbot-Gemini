# 🤖 Gemini AI Ultimate Chatbot

A modern, full-stack AI chatbot built with **Python Flask** and **Google's Gemini API**. This application features real-time streaming, persistent chat history, voice input, and image analysis in a beautiful glassmorphism UI.

## ✨ Features

*   **⚡ Real-time Streaming:** Text appears instantly as it is generated (Typewriter effect).
*   **💾 Persistent Memory:** Saves chat history and conversations using SQLite.
*   **📸 Multimodal:** Upload images and ask questions about them.
*   **🎙️ Voice Interaction:** Built-in Speech-to-Text for voice commands.
*   **🎨 Modern UI:** Glassmorphism design with animated backgrounds and Markdown support.
*   **🎛️ Controls:** Adjust AI creativity (Temperature) and stop generation mid-stream.

## 🛠️ Tech Stack

*   **Backend:** Python, Flask, SQLAlchemy (SQLite)
*   **AI Engine:** Google Gemini 2.0 Flash (via `google-generativeai`)
*   **Frontend:** HTML5, CSS3, Vanilla JavaScript
*   **Utilities:** Pillow (Image processing), Dotenv

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
    Go to `http://127.0.0.1:5000` to start chatting!

## 📂 Project Structure

```text
/project-root
├── app.py               # Main Flask backend application
├── chat_history.db      # SQLite database (auto-created)
├── .env                 # API Key configuration
├── requirements.txt     # Python dependencies
├── static/
│   ├── style.css        # Styling and animations
│   └── script.js        # Frontend logic (Streaming, Voice, API calls)
└── templates/
    └── chat.html        # Main HTML interface
