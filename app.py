import os
import io

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from PIL import Image


load_dotenv()

app = Flask(__name__)


# Get Gemini API key
api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)


# Home page
@app.route("/")
def home():
    return render_template("index.html")


# AI instructions
SYSTEM_PROMPT = """
You are DASH, a friendly AI Digital Trust, Scam and Fraud Advisor.

Help users understand:
- Online scams and fraud
- Phishing messages and emails
- Suspicious websites and links
- Fake online offers
- Digital privacy and safety

IMPORTANT RESPONSE RULES:

Give very short chatbot-style answers.

Maximum 4 short lines.
Keep the answer under 70 words.

Give the conclusion first using one of these styles when appropriate:
"🚨 This looks suspicious."
"⚠️ Please be careful."
"✅ This appears relatively safe based on the information provided."

Then give only 2 or 3 important reasons or safety suggestions.

Do not write long paragraphs.
Do not give detailed explanations unless the user specifically asks for details.

Do not claim with 100% certainty that a website is safe or fraudulent
unless there is sufficient evidence.
"""


# Text chat
@app.route("/chat", methods=["POST"])
def chat():

    data = request.get_json()

    user_message = data.get("message", "")

    try:

        response = client.models.generate_content(

            model="gemini-3.5-flash-lite",

            contents=f"""
{SYSTEM_PROMPT}

User message:
{user_message}
"""
        )

        return jsonify({
            "reply": response.text
        })

    except Exception as e:

        return jsonify({
            "reply": "Sorry, something went wrong. Please try again."
        })


# Image analysis
@app.route("/analyze-image", methods=["POST"])
def analyze_image():

    try:

        # Check image
        if "image" not in request.files:

            return jsonify({
                "reply": "⚠️ Please select an image first."
            })


        image_file = request.files["image"]


        if image_file.filename == "":

            return jsonify({
                "reply": "⚠️ Please select an image first."
            })


        # Open uploaded image
        image = Image.open(
            io.BytesIO(image_file.read())
        )


        # Send image to Gemini
        response = client.models.generate_content(

            model="gemini-3.5-flash-lite",

            contents=[
                f"""
{SYSTEM_PROMPT}

Analyze this uploaded image.

It may contain:
- A suspicious website
- A scam message
- A phishing email
- A fake product offer
- A suspicious payment request

Identify visible scam or fraud warning signs.

Give only a short chatbot-style answer.
Maximum 4 short lines and under 70 words.
""",

                image
            ]
        )


        return jsonify({
            "reply": response.text
        })


    except Exception as e:

        return jsonify({
            "reply": "Sorry, I couldn't analyze this image. Please try again."
        })


if __name__ == "__main__":
    app.run(debug=True)