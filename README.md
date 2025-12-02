# 🤖 Gemini AI Chatbot & Resume Builder

A comprehensive full-stack AI application built with **Python Flask** and **Google's Gemini API**. This project combines a powerful, multimodal chatbot with an intelligent **Resume Builder** that acts as a personal interviewer to generate professional profiles.

## ✨ Features

### 💬 Advanced Chatbot
*   **⚡ Real-time Streaming:** Text appears instantly as it is generated (Typewriter effect).
*   **💾 Persistent Memory:** Saves chat history and conversations using SQLite.
*   **📸 Multimodal:** Upload images and ask questions about them.
*   **🎙️ Voice Interaction:** Built-in Speech-to-Text for voice commands.
*   **🎛️ Controls:** Adjust AI creativity (Temperature) and stop generation mid-stream.

### 📄 AI Resume Builder (New!)
*   **🤖 AI Interviewer:** A dedicated mode that asks structured questions to gather resume details.
*   **✅ Strict Validation:** Ensures mandatory fields, emails, and phone numbers are valid before proceeding.
*   **📝 Live Form Preview:** Watch your resume form fill up in real-time as you answer questions.
*   **🧠 Smart Suggestions:** The AI generates multiple professional summary options for you to choose from.
*   **✨ Interactive UI:** Split-screen layout with suggestion chips and a final review mode.

## 🛠️ Tech Stack

*   **Backend:** Python, Flask, SQLAlchemy (SQLite)
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
    *   Use the **Top Navigation Bar** to switch between the **Chatbot** and the **Resume Builder**.

## 📂 Project Structure

```text
/project-root
├── app.py               # Main Flask backend (Chatbot + Resume Logic)
├── chat_history.db      # SQLite database (auto-created)
├── .env                 # API Key configuration
├── requirements.txt     # Python dependencies
├── static/
│   ├── style.css        # Global styling (Glassmorphism, Layouts)
│   ├── script.js        # Logic for the General Chatbot
│   └── resume_script.js # Logic for the Resume Builder (State Machine)
└── templates/
    ├── chat.html        # General Chatbot Interface
    └── resume.html      # Resume Builder Interface
