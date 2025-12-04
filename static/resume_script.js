const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const suggestionArea = document.getElementById('suggestion-area');
const finalForm = document.getElementById('final-form');
const formPlaceholder = document.getElementById('form-placeholder');
const successModal = document.getElementById('success-modal');
const resumeUpload = document.getElementById('resume-upload');
const progressBar = document.getElementById('progress-bar');

let currentStep = -1;
let collectedData = {};
let resumeSessionId = null;
let currentResumeUploadId = null;

const RESUME_STEPS = [
    { field: "full_name" }, { field: "email" }, { field: "phone" },
    { field: "experience_level" }, { field: "domain" }, { field: "job_title" },
    { field: "skills" }, { field: "summary" }, { field: "critique" }
];

document.addEventListener('DOMContentLoaded', () => {
    const savedData = localStorage.getItem('resumeData');
    const savedSessionId = localStorage.getItem('resumeSessionId');
    const savedUploadId = localStorage.getItem('resumeUploadId');

    if (savedData) {
        collectedData = JSON.parse(savedData);
        updateLiveForm(collectedData);
        if (Object.keys(collectedData).length > 0) showForm();
        if (savedSessionId) resumeSessionId = savedSessionId;
        if (savedUploadId) currentResumeUploadId = savedUploadId;
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
                updateProgressBar();
            }

            if (data.data && !data.keep_step) {
                collectedData = data.data;
                updateLiveForm(collectedData);
                localStorage.setItem('resumeData', JSON.stringify(collectedData));
                if (Object.keys(collectedData).length > 0) showForm();
            }

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
                disableChatInput();
            }
        }
    });
}

function updateProgressBar() {
    if(!progressBar) return;
    let progress = ((currentStep + 1) / RESUME_STEPS.length) * 100;
    progressBar.style.width = `${progress}%`;
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
            if (['Generate Options', 'Show Example', 'Suggest Skills', 'Critique', 'Submit', 'Check ATS Score'].includes(text)) {
                userInput.value = text;
                sendResumeMessage();
                return;
            }
            if (currentFieldName === 'skills') {
                chip.classList.toggle('selected');
                let currentVal = userInput.value.trim();
                let selectedSkill = text.trim();
                if (chip.classList.contains('selected')) {
                    if (currentVal.length > 0 && !currentVal.endsWith(',')) currentVal += ', ';
                    userInput.value = currentVal + selectedSkill;
                }
                userInput.focus();
            } else if (currentFieldName === 'summary') {
                let cleanText = text.replace(/^[\s\W]*(?:Option|Summary)\s*\d*[:\.]\s*/i, '').trim();
                userInput.value = cleanText;
                sendResumeMessage();
            } else {
                userInput.value = text;
                sendResumeMessage();
            }
        };
        suggestionArea.appendChild(chip);
    });
}

function downloadPDF() {
    document.getElementById('tpl-name').innerText = document.getElementById('form-full_name').value || "YOUR NAME";
    document.getElementById('tpl-email').innerText = document.getElementById('form-email').value;
    document.getElementById('tpl-phone').innerText = document.getElementById('form-phone').value;
    document.getElementById('tpl-job').innerText = document.getElementById('form-job_title').value;
    document.getElementById('tpl-summary').innerText = document.getElementById('form-summary').value;
    document.getElementById('tpl-skills').innerText = document.getElementById('form-skills').value;
    document.getElementById('tpl-exp').innerText = document.getElementById('form-experience_level').value;
    document.getElementById('tpl-domain').innerText = document.getElementById('form-domain').value;

    const element = document.getElementById('resume-template');
    element.style.display = 'block';
    const opt = { margin: 0.5, filename: 'Professional_Resume.pdf', image: { type: 'jpeg', quality: 0.98 }, html2canvas: { scale: 2 }, jsPDF: { unit: 'in', format: 'letter', orientation: 'portrait' } };
    html2pdf().set(opt).from(element).save().then(() => { element.style.display = 'none'; });
}

function uploadResume(file) {
    const formData = new FormData();
    formData.append('file', file);
    appendMessage(`Uploading: ${file.name}...`, 'user-message');
    const loadingId = showTypingIndicator();
    fetch('/api/upload-resume', { method: 'POST', body: formData })
    .then(res => res.json())
    .then(data => {
        removeMessage(loadingId);
        if (data.error) appendMessage(`⚠️ ${data.error}`, 'bot-message error');
        else {
            collectedData = { ...collectedData, ...data.data };
            if (data.resume_id) {
                currentResumeUploadId = data.resume_id;
                localStorage.setItem('resumeUploadId', currentResumeUploadId);
            }
            updateLiveForm(collectedData);
            localStorage.setItem('resumeData', JSON.stringify(collectedData));
            if (Object.keys(collectedData).length > 0) showForm();
            appendMessage(`✅ ${data.message}`, 'bot-message');
            sendResumeMessage(false, true);
        }
    });
}

resumeUpload.addEventListener('change', function() { if (this.files[0]) uploadResume(this.files[0]); });

function updateLiveForm(data) {
    for (const [key, value] of Object.entries(data)) {
        const field = document.getElementById(`form-${key}`);
        if (field && field.value !== value) {
            field.value = value;
            field.classList.add('flash-update');
            setTimeout(() => field.classList.remove('flash-update'), 1000);
        }
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
        domain: document.getElementById('form-domain').value.trim(),
        job_title: document.getElementById('form-job_title').value.trim(),
        skills: document.getElementById('form-skills').value.trim(),
        summary: document.getElementById('form-summary').value.trim(),
        resume_session_id: resumeSessionId,
        upload_resume_id: currentResumeUploadId
    };
    if (!finalData.full_name) return alert("Please fill Full Name.");
    fetch('/api/submit-resume', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(finalData) })
    .then(res => res.json())
    .then(data => {
        if(data.status === 'success') {
            localStorage.removeItem('resumeData'); localStorage.removeItem('resumeSessionId'); localStorage.removeItem('resumeUploadId');
            successModal.classList.remove('hidden'); disableChatInput();
        } else alert("Error saving: " + (data.error));
    });
}

function closeModal() {
    successModal.classList.add('hidden');
    window.location.href = '/';
}

function appendMessage(text, className, isMarkdown) {
    const div = document.createElement('div');
    div.className = `message ${className}`;
    const icon = className.includes('user') ? 'fa-user' : 'fa-robot';
    div.innerHTML = `<div class="avatar"><i class="fa-solid ${icon}"></i></div><div class="content">${isMarkdown ? marked.parse(text) : text}</div>`;

    if (className.includes('user')) {
        div.style.cursor = 'pointer';
        div.title = "Click to edit";
        div.onclick = () => { userInput.value = text; userInput.focus(); };
    }

    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function showTypingIndicator() {
    const id = 'typing-' + Date.now();
    const msgDiv = document.createElement('div');
    msgDiv.className = 'message bot-message'; msgDiv.id = id;
    msgDiv.innerHTML = `<div class="avatar"><i class="fa-solid fa-robot"></i></div><div class="content"><div class="typing-indicator"><span></span><span></span><span></span></div></div>`;
    chatBox.appendChild(msgDiv); chatBox.scrollTop = chatBox.scrollHeight;
    return id;
}

function removeMessage(id) { const el = document.getElementById(id); if (el) el.remove(); }

function clearProfile() {
    if (confirm("Start fresh?")) {
        localStorage.removeItem('resumeData'); localStorage.removeItem('resumeSessionId'); localStorage.removeItem('resumeUploadId');
        window.location.reload();
    }
}

userInput.addEventListener("keypress", function(event) {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendResumeMessage(); }
});