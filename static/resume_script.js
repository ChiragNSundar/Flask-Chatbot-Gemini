const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const suggestionArea = document.getElementById('suggestion-area');
const finalForm = document.getElementById('final-form');
const formPlaceholder = document.getElementById('form-placeholder');
const successModal = document.getElementById('success-modal');
const resumeUpload = document.getElementById('resume-upload');

let currentStep = -1;
let collectedData = {};
let resumeSessionId = null;

// Make sure this matches Python RESUME_STEPS exactly
const RESUME_STEPS = [
    { field: "full_name" },
    { field: "email" },
    { field: "phone" },
    { field: "experience_level" },
    { field: "domain" },
    { field: "job_title" },
    { field: "skills" }, // Index 6
    { field: "summary" }, // Index 7
    { field: "critique" }
];

document.addEventListener('DOMContentLoaded', () => {
    const savedData = localStorage.getItem('resumeData');
    const savedSessionId = localStorage.getItem('resumeSessionId');

    if (savedData) {
        collectedData = JSON.parse(savedData);
        updateLiveForm(collectedData);
        if (Object.keys(collectedData).length > 0) showForm();
        if (savedSessionId) resumeSessionId = savedSessionId;
        sendResumeMessage(false, true);
    } else {
        sendResumeMessage(true);
    }

    finalForm.querySelectorAll('input, textarea').forEach(field => {
        field.addEventListener('input', function() {
            const fieldName = this.id.replace('form-', '');
            collectedData[fieldName] = this.value.trim();
            localStorage.setItem('resumeData', JSON.stringify(collectedData));
            showForm();
        });
    });
});

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
            data: collectedData,
            session_id: resumeSessionId
        })
    })
    .then(res => res.json())
    .then(data => {
        removeMessage(loadingId);

        if (data.error) {
            appendMessage(`⚠️ ${data.error}`, 'bot-message error');
        } else {
            if (data.session_id && data.session_id !== resumeSessionId) {
                resumeSessionId = data.session_id;
                localStorage.setItem('resumeSessionId', resumeSessionId);
            }

            if (data.response && data.response.trim() !== "") {
                appendMessage(data.response, 'bot-message', true);
            }

            if (data.next_step !== undefined && !data.keep_step) {
                currentStep = data.next_step;
            }

            if (data.data && !data.keep_step) {
                collectedData = data.data;
                updateLiveForm(collectedData);
                localStorage.setItem('resumeData', JSON.stringify(collectedData));
                if (Object.keys(collectedData).length > 0) showForm();
            }

            // Pass field name to renderer
            if (data.suggestions && data.suggestions.length > 0) {
                const stepField = RESUME_STEPS[currentStep] ? RESUME_STEPS[currentStep].field : 'unknown';
                renderSuggestions(data.suggestions, stepField);
            }

            if (data.question) {
                setTimeout(() => {
                    appendMessage(data.question, 'bot-message', true);
                }, 300);
            }

            if (data.finished) {
                showFinalForm();
                disableChatInput(); // Disable input on natural finish
            }
        }
    });
}

function disableChatInput() {
    userInput.disabled = true;
    userInput.placeholder = "Interview Complete. Please Submit.";
    suggestionArea.innerHTML = '';
}

function renderSuggestions(suggestions, currentFieldName) {
    suggestionArea.innerHTML = '';

    suggestions.forEach(text => {
        const chip = document.createElement('div');
        chip.className = 'chip';
        chip.innerText = text.length > 50 ? text.substring(0, 50) + "..." : text;
        chip.title = text;

        chip.onclick = () => {
            // COMMANDS: Auto-send
            if (['Generate Options', 'Show Example', 'Suggest Skills', 'Critique', 'Submit'].includes(text)) {
                userInput.value = text;
                sendResumeMessage();
                return;
            }

            // SKILLS: Multi-Select (No Auto-Send)
            if (currentFieldName === 'skills') {
                chip.classList.toggle('selected');

                let currentVal = userInput.value.trim();
                let selectedSkill = text.trim();

                if (chip.classList.contains('selected')) {
                    if (currentVal.length > 0 && !currentVal.endsWith(',')) {
                        currentVal += ', ';
                    }
                    userInput.value = currentVal + selectedSkill;
                }
                userInput.focus();
            }
            // SUMMARY RESULTS: Auto-Send (CHANGED per request)
            else if (currentFieldName === 'summary') {
                let cleanText = text.replace(/^[\s\W]*(?:Option|Summary)\s*\d*[:\.]\s*/i, '').trim();
                userInput.value = cleanText;
                sendResumeMessage(); // Auto-send triggered
            }
            // DEFAULT: Single Select (Auto-Send)
            else {
                userInput.value = text;
                sendResumeMessage();
            }
        };
        suggestionArea.appendChild(chip);
    });
}

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
            localStorage.setItem('resumeData', JSON.stringify(collectedData));
            if (Object.keys(collectedData).length > 0) showForm();
            appendMessage(`✅ ${data.message}`, 'bot-message');
            sendResumeMessage(false, true);
        }
    })
    .catch(err => {
        removeMessage(loadingId);
        appendMessage('Error uploading file.', 'bot-message error');
    });
}

resumeUpload.addEventListener('change', function() {
    const file = this.files[0];
    if (file) uploadResume(file);
});

function updateLiveForm(data) {
    for (const [key, value] of Object.entries(data)) {
        const field = document.getElementById(`form-${key}`);
        if (field) field.value = value;
    }
}

function showForm() {
    formPlaceholder.classList.add('hidden');
    finalForm.classList.remove('hidden-form');
    finalForm.classList.add('visible-form');
}

function showFinalForm() {
    showForm();
    suggestionArea.innerHTML = '';
}

function submitFinalForm() {
    const finalData = {
        full_name: document.getElementById('form-full_name').value.trim(),
        email: document.getElementById('form-email').value.trim(),
        phone: document.getElementById('form-phone').value.trim(),
        experience_level: document.getElementById('form-experience_level').value.trim(),
        domain: collectedData.domain || document.getElementById('form-domain').value.trim(),
        job_title: document.getElementById('form-job_title').value.trim(),
        skills: document.getElementById('form-skills').value.trim(),
        summary: document.getElementById('form-summary').value.trim(),
        resume_session_id: resumeSessionId
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
        alert("Please complete mandatory fields:\n\n- " + emptyFields.join("\n- "));
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
            localStorage.removeItem('resumeData');
            localStorage.removeItem('resumeSessionId');
            successModal.classList.remove('hidden');
            disableChatInput(); // Disable chat input on manual submit
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

function clearProfile() {
    if (confirm("Clear profile and start over?")) {
        localStorage.removeItem('resumeData');
        localStorage.removeItem('resumeSessionId');
        window.location.reload();
    }
}

userInput.addEventListener("keypress", function(event) {
    if (event.key === "Enter" && !event.shiftKey) {
        event.preventDefault();
        sendResumeMessage();
    }
});