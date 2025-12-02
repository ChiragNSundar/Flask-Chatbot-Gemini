const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const suggestionArea = document.getElementById('suggestion-area');
const finalForm = document.getElementById('final-form');
const formPlaceholder = document.getElementById('form-placeholder');
const successModal = document.getElementById('success-modal');

let currentStep = -1;
let collectedData = {};

document.addEventListener('DOMContentLoaded', () => {
    sendResumeMessage(true);
});

function sendResumeMessage(isInit = false) {
    const text = isInit ? '' : userInput.value.trim();
    if (!isInit && !text) return;

    if (!isInit) {
        appendMessage(text, 'user-message');
        userInput.value = '';
        suggestionArea.innerHTML = '';
    }

    const loadingId = showTypingIndicator();

    fetch('/api/resume-chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: text,
            step: currentStep,
            data: collectedData
        })
    })
    .then(res => res.json())
    .then(data => {
        removeMessage(loadingId);

        if (data.error) {
            appendMessage(`⚠️ ${data.error}`, 'bot-message error');
        } else {
            if (data.response) {
                appendMessage(data.response, 'bot-message');
            }

            // FIX: Only update step if backend says so (handles "keep_step" for generation)
            if (data.next_step !== undefined && !data.keep_step) {
                currentStep = data.next_step;
            }

            // FIX: Only update form if we are NOT in the middle of generating options
            if (data.data && !data.keep_step) {
                collectedData = data.data;
                updateLiveForm(collectedData);
            }

            if (data.question) {
                setTimeout(() => {
                    appendMessage(data.question, 'bot-message', true);
                    if (data.suggestions && data.suggestions.length > 0) {
                        renderSuggestions(data.suggestions);
                    }
                }, 500);
            }

            if (data.finished) {
                showFinalForm();
            }
        }
    });
}

function renderSuggestions(suggestions) {
    suggestionArea.innerHTML = '';
    suggestions.forEach(text => {
        const chip = document.createElement('div');
        chip.className = 'chip';
        // Truncate long summaries in chips for display
        chip.innerText = text.length > 50 ? text.substring(0, 50) + "..." : text;
        chip.title = text; // Show full text on hover

        chip.onclick = () => {
            // When clicked, put the FULL text into input and send
            userInput.value = text;
            sendResumeMessage();
        };
        suggestionArea.appendChild(chip);
    });
}

function updateLiveForm(data) {
    for (const [key, value] of Object.entries(data)) {
        const field = document.getElementById(`form-${key}`);
        if (field) field.value = value;
    }
}

function showFinalForm() {
    formPlaceholder.style.display = 'none';
    finalForm.classList.remove('hidden-form');
    finalForm.classList.add('visible-form');
    suggestionArea.innerHTML = '';
    userInput.disabled = true;
    userInput.placeholder = "Interview complete.";
}

function submitFinalForm() {
    const finalData = {
        full_name: document.getElementById('form-full_name').value,
        email: document.getElementById('form-email').value,
        phone: document.getElementById('form-phone').value,
        experience: document.getElementById('form-experience_level').value,
        job: document.getElementById('form-job_title').value,
        skills: document.getElementById('form-skills').value,
        summary: document.getElementById('form-summary').value
    };

    fetch('/api/submit-resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(finalData)
    })
    .then(res => res.json())
    .then(data => {
        successModal.classList.remove('hidden');
    });
}

function closeModal() {
    successModal.classList.add('hidden');
    window.location.href = '/';
}

function appendMessage(text, className, isMarkdown = false) {
    const div = document.createElement('div');
    div.className = `message ${className}`;
    const icon = className.includes('user') ? 'fa-user' : 'fa-robot';

    div.innerHTML = `
        <div class="avatar"><i class="fa-solid ${icon}"></i></div>
        <div class="content">${isMarkdown ? marked.parse(text) : text}</div>
    `;

    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function showTypingIndicator() {
    const id = 'typing-' + Date.now();
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message bot-message';
    msgDiv.id = id;
    msgDiv.innerHTML = `
        <div class="avatar"><i class="fa-solid fa-robot"></i></div>
        <div class="content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>
    `;
    chatBox.appendChild(msgDiv);
    chatBox.scrollTop = chatBox.scrollHeight;
    return id;
}

function removeMessage(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
}

userInput.addEventListener("keypress", function(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendResumeMessage();
    }
});