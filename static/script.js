const input = document.querySelector("#user-input");
const sendButton = document.querySelector("#send-btn");
const chatBox = document.querySelector(".chat-box");

const uploadButton = document.querySelector("#upload-btn");
const imageInput = document.querySelector("#image-input");

let selectedImage = null;


// Send text message
async function sendMessage(customMessage = null) {

    const message = customMessage || input.value.trim();

    if (message === "") return;

    addMessage(message, "user-message");

    input.value = "";

    const thinkingMessage = addMessage(
        "DASH is thinking... 🤖",
        "bot-message"
    );

    try {

        const response = await fetch("/chat", {
            method: "POST",

            headers: {
                "Content-Type": "application/json"
            },

            body: JSON.stringify({
                message: message
            })
        });

        const data = await response.json();

        thinkingMessage.textContent = data.reply;

    } catch (error) {

        thinkingMessage.textContent =
            "Sorry, I couldn't connect right now. Please try again.";
    }

    scrollChat();
}


// Add message to chat
function addMessage(text, className) {

    const message = document.createElement("div");

    message.className = "message " + className;

    message.textContent = text;

    chatBox.appendChild(message);

    scrollChat();

    return message;
}


function scrollChat() {

    chatBox.scrollTop = chatBox.scrollHeight;
}


// Send button
sendButton.addEventListener("click", function () {

    if (selectedImage) {
        uploadImage();
    } else {
        sendMessage();
    }

});


// Enter key
input.addEventListener("keypress", function (event) {

    if (event.key === "Enter") {

        if (selectedImage) {
            uploadImage();
        } else {
            sendMessage();
        }
    }

});


// Option buttons working
document.querySelectorAll(".option-btn").forEach(button => {

    button.addEventListener("click", function () {

        const prompt = this.dataset.prompt;

        sendMessage(prompt);

    });

});


// Open image selector
uploadButton.addEventListener("click", function () {

    imageInput.click();

});


// Select image
imageInput.addEventListener("change", function () {

    if (this.files.length > 0) {

        selectedImage = this.files[0];

        addMessage(
            "📷 Image selected: " + selectedImage.name +
            "\nPress Send ➤ to analyze it.",
            "user-message"
        );

    }

});


// Upload image to Flask
async function uploadImage() {

    if (!selectedImage) return;

    const formData = new FormData();

    formData.append("image", selectedImage);

    addMessage(
        "Please analyze this image for possible scam or fraud signs.",
        "user-message"
    );

    const thinkingMessage = addMessage(
        "DASH is analyzing the image... 🤖🔍",
        "bot-message"
    );

    try {

        const response = await fetch("/analyze-image", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        thinkingMessage.textContent = data.reply;

        selectedImage = null;

        imageInput.value = "";

    } catch (error) {

        thinkingMessage.textContent =
            "Sorry, I couldn't analyze the image. Please try again.";

    }

    scrollChat();
}
