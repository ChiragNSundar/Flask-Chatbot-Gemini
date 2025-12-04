const chatBox = document.getElementById('chat-box');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const stopBtn = document.getElementById('stop-btn');
const imageInput = document.getElementById('image-upload');
const imagePreview = document.getElementById('image-preview');
const imagePreviewContainer = document.getElementById('image-preview-container');
const conversationList = document.getElementById('conversation-list');
const micBtn = document.getElementById('mic-btn');
const settingsPanel = document.getElementById('settings-panel');
const tempSlider = document.getElementById('temp-slider');
const tempValue = document.getElementById('temp-value');

let currentChatId = null;
let abortController = null;
let currentImageBase64 = null;

document.addEventListener('DOMContentLoaded', () => {
    loadConversations(true);
    if(tempSlider && tempValue) tempValue.textContent = tempSlider.value;
});

function toggleSettings() { settingsPanel.classList.toggle('open'); }

if(tempSlider) {
    tempSlider.addEventListener('input', function() { tempValue.textContent = this.value; });
}

function loadConversations(autoLoadFirst = false) {
    fetch('/api/conversations')
        .then(res => res.json())
        .then(chats => {
            conversationList.innerHTML = '';
            chats.forEach(chat => {
                const div = document.createElement('div');
                div.className = `chat-item ${chat.id == currentChatId ? 'active' : ''}`;
                div.innerHTML = `<span onclick="loadChat(${chat.id})">${chat.title}</span> <i class="fa-solid fa-trash delete-chat" onclick="deleteChat(${chat.id}, event)"></i>`;
                conversationList.appendChild(div);
            });
            if (autoLoadFirst) {
                if (chats.length > 0) loadChat(chats[0].id);
                else createNewChat();
            }
        });
}

function createNewChat() {
    fetch('/api/conversations', { method: 'POST' })
        .then(res => res.json())
        .then(chat => { loadChat(chat.id); loadConversations(); });
}

function loadChat(chatId) {
    currentChatId = chatId;
    loadConversations();
    chatBox.innerHTML = '';
    fetch(`/api/conversations/${chatId}/messages`)
        .then(res => res.json())
        .then(messages => {
            if(messages.length === 0) appendMessage("Start a new conversation!", "bot-message");
            else messages.forEach(msg => appendMessage(msg.content, msg.role === 'user' ? 'user-message' : 'bot-message', true, false, msg.image));
        });
}

function deleteChat(chatId, event) {
    event.stopPropagation();
    if(!confirm("Delete this chat?")) return;
    fetch(`/api/conversations/${chatId}`, { method: 'DELETE' })
        .then(() => {
            if(currentChatId == chatId) { currentChatId = null; loadConversations(true); }
            else loadConversations();
        });
}

if(imageInput) {
    imageInput.addEventListener('change', function() {
        const file = this.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = function(e) {
                currentImageBase64 = e.target.result;
                imagePreview.src = currentImageBase64;
                imagePreviewContainer.classList.remove('hidden');
            }
            reader.readAsDataURL(file);
        }
    });
}

function clearImage() {
    imageInput.value = '';
    currentImageBase64 = null;
    imagePreviewContainer.classList.add('hidden');
}

const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
const recognition = SpeechRecognition ? new SpeechRecognition() : null;

function toggleVoice() {
    if(!recognition) return alert("Browser does not support voice.");
    if(micBtn.classList.contains('recording')) recognition.stop();
    else { recognition.start(); micBtn.classList.add('recording'); }
}
if(recognition) {
    recognition.onresult = (event) => { userInput.value += event.results[0][0].transcript; micBtn.classList.remove('recording'); };
    recognition.onend = () => micBtn.classList.remove('recording');
}

async function sendMessage() {
    const text = userInput.value.trim();
    if (!text && !currentImageBase64) return;
    if (!currentChatId) return alert("Please select a chat first.");

    appendMessage(text, 'user-message', false, false, currentImageBase64);
    userInput.value = ''; userInput.style.height = 'auto';
    const imgToSend = currentImageBase64;
    clearImage();

    toggleButtons(true);
    const contentDiv = appendMessage("", 'bot-message', false, false, null);
    abortController = new AbortController();

    try {
        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chat_id: currentChatId, message: text, image: imgToSend, temperature: tempSlider.value }),
            signal: abortController.signal
        });
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let botText = "";
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');
            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.text) { botText += data.text; contentDiv.innerHTML = marked.parse(botText); chatBox.scrollTop = chatBox.scrollHeight; }
                        if (data.done && data.title) loadConversations();
                    } catch (e) {}
                }
            }
        }
    } catch (err) { if (err.name !== 'AbortError') contentDiv.innerHTML += `<br><span style="color:red">Error: ${err.message}</span>`; }
    toggleButtons(false);
}

function appendMessage(text, className, isMarkdown, isTypewriter, imageSrc) {
    const div = document.createElement('div');
    div.className = `message ${className}`;
    const icon = className.includes('user') ? 'fa-user' : 'fa-robot';
    let imgHTML = imageSrc ? `<img src="${imageSrc}" class="message-img">` : '';
    div.innerHTML = `<div class="avatar"><i class="fa-solid ${icon}"></i></div><div class="content">${imgHTML}<div class="text-content">${isMarkdown ? marked.parse(text) : text}</div></div>`;
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
    return div.querySelector('.text-content');
}

function stopGeneration() { if(abortController) abortController.abort(); toggleButtons(false); }
function toggleButtons(loading) { sendBtn.classList.toggle('hidden', loading); stopBtn.classList.toggle('hidden', !loading); }

userInput.addEventListener("keydown", function(event) { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); sendMessage(); } });