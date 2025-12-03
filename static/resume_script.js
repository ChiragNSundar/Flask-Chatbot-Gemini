const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const suggestionArea = document.getElementById('suggestion-area');
const finalForm = document.getElementById('final-form');
const formPlaceholder = document.getElementById('form-placeholder');
const successModal = document.getElementById('success-modal');
const resumeUpload = document.getElementById('resume-upload');

let currentStep = -1;
let collectedData = {};

document.addEventListener('DOMContentLoaded', () => {
    sendResumeMessage(true);
});

resumeUpload.addEventListener('change', function() {
    const file = this.files[0];
    if (file) {
        uploadResume(file);
    }
});

function uploadResume(file) {
    const formData = new FormData();
    formData.append('file', file);

    appendMessage(`Uploading: ${file.name}...`, 'user-message');
    const loadingId = showTypingIndicator();

    fetch('/api/upload-resume', {
        method: 'POST',
        body: formData
    })
    .then(res => res.json())
    .then(data => {
        removeMessage(loadingId);
        if (data.error) {
            appendMessage(`⚠️ ${data.error}`, 'bot-message error');
        } else {
            collectedData = { ...collectedData, ...data.data };
            updateLiveForm(collectedData);

            if (Object.keys(collectedData).length > 0) {
                formPlaceholder.style.display = 'none';
                finalForm.classList.remove('hidden-form');
                finalForm.classList.add('visible-form');
            }

            appendMessage(`✅ ${data.message}`, 'bot-message');
            sendResumeMessage(false, true);
        }
    })
    .catch(err => {
        removeMessage(loadingId);
        appendMessage('Error uploading file.', 'bot-message error');
    });
}

function sendResumeMessage(isInit = false, silentCheck = false) {
    const text = isInit || silentCheck ? '' : userInput.value.trim();
    if (!isInit && !silentCheck && !text) return;

    if (!isInit && !silentCheck) {
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
            if (data.response && data.response.trim() !== "") {
                appendMessage(data.response, 'bot-message');
            }

            if (data.next_step !== undefined && !data.keep_step) {
                currentStep = data.next_step;
            }

            if (data.data && !data.keep_step) {
                collectedData = data.data;
                updateLiveForm(collectedData);
                if (Object.keys(collectedData).length > 0) {
                    formPlaceholder.style.display = 'none';
                    finalForm.classList.remove('hidden-form');
                    finalForm.classList.add('visible-form');
                }
            }

            if (data.suggestions && data.suggestions.length > 0) {
                renderSuggestions(data.suggestions);
            }

            if (data.question) {
                setTimeout(() => {
                    appendMessage(data.question, 'bot-message', true);
                }, 300);
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
            // --- FIX: Remove leading heading/numbering before setting input ---
            let cleanText = text.replace(/^\s*(\*\*Resume Summary \d+:\*\*|\d+\.\s*|Option \d+:\s*|\*\*\s*|\s*\*\*)/i, '').trim();

            // If the cleaning removed everything, use the original text as a fallback
            if (cleanText.length === 0) {
                cleanText = text.trim();
            }

            userInput.value = cleanText;
            // ------------------------------------------------------------------
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
        full_name: document.getElementById('form-full_name').value.trim(),
        email: document.getElementById('form-email').value.trim(),
        phone: document.getElementById('form-phone').value.trim(),
        experience_level: document.getElementById('form-experience_level').value.trim(),
        job_title: document.getElementById('form-job_title').value.trim(),
        skills: document.getElementById('form-skills').value.trim(),
        summary: document.getElementById('form-summary').value.trim()
    };

    const emptyFields = [];
    if (!finalData.full_name) emptyFields.push("Full Name");
    if (!finalData.email) emptyFields.push("Email");
    if (!finalData.phone) emptyFields.push("Phone");
    if (!finalData.experience_level) emptyFields.push("Experience");
    if (!finalData.job_title) emptyFields.push("Job Title");
    if (!finalData.skills) emptyFields.push("Skills");
    if (!finalData.summary) emptyFields.push("Summary");

    if (emptyFields.length > 0) {
        alert("Please complete the following mandatory fields before submitting:\n\n- " + emptyFields.join("\n- "));
        return;
    }

    fetch('/api/submit-resume', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(finalData)
    })
    .then(res => res.json())
    .then(data => {
        if(data.status === 'success') {
            successModal.classList.remove('hidden');
        } else {
            alert("Error saving profile: " + (data.error || "Unknown error"));
        }
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