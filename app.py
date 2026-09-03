import os
import io
import re
from urllib.parse import urlparse

from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from google import genai
from PIL import Image

load_dotenv()

app = Flask(name)

Get Gemini API key

api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)

Home page

@app.route("/")
def home():
return render_template("index.html")

AI instructions

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

Detect URL in user message

def extract_url(text):
urls = re.findall(r'https?://[^\s]+|www.[^\s]+', text)

if urls:
    return urls[0]

return None

Basic URL risk analysis

def analyze_url(url):

original_url = url

if not url.startswith(("http://", "https://")):
    url = "https://" + url

parsed = urlparse(url)

domain = parsed.netloc.lower()
path = parsed.path.lower()

risk_score = 0
reasons = []


# HTTPS check
if parsed.scheme != "https":
    risk_score += 2
    reasons.append("It does not use HTTPS.")


# IP address instead of domain
if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', domain):
    risk_score += 3
    reasons.append("It uses an IP address instead of a normal domain.")


# Suspicious keywords
suspicious_keywords = [
    "login", "verify", "verification",
    "secure", "account", "update",
    "confirm", "password", "wallet",
    "bank", "upi", "gift", "free",
    "winner", "prize", "bonus",
    "urgent", "limited", "offer",
    "payment", "refund"
]

keyword_count = 0

for keyword in suspicious_keywords:

    if keyword in domain or keyword in path:
        keyword_count += 1


if keyword_count >= 3:
    risk_score += 3
    reasons.append("The URL contains several keywords commonly used in scam or phishing links.")

elif keyword_count >= 1:
    risk_score += 1
    reasons.append("The URL contains a potentially sensitive or promotional keyword.")


# Too many hyphens
if domain.count("-") >= 3:
    risk_score += 2
    reasons.append("The domain contains many hyphens, which can sometimes be used in fake domains.")


# Very long domain
if len(domain) > 45:
    risk_score += 2
    reasons.append("The domain name is unusually long.")


# Too many subdomains
if domain.count(".") >= 3:
    risk_score += 1
    reasons.append("The URL contains multiple subdomains.")


# @ symbol in URL
if "@" in original_url:
    risk_score += 3
    reasons.append("The URL contains an unusual @ symbol.")


# Final result
if risk_score >= 5:

    verdict = "🚨 HIGH RISK / SUSPICIOUS"

elif risk_score >= 2:

    verdict = "⚠️ SUSPICIOUS — VERIFY BEFORE USING"

else:

    verdict = "🟡 NO OBVIOUS URL RED FLAGS"


if not reasons:

    reasons.append(
        "No obvious suspicious URL pattern was detected."
    )


return verdict, reasons

Text chat

@app.route("/chat", methods=["POST"])
def chat():

data = request.get_json()

user_message = data.get("message", "")

# Check whether user provided a URL
url = extract_url(user_message)

if url:

    verdict, reasons = analyze_url(url)

    reason_text = "\n".join(
        [f"• {reason}" for reason in reasons[:2]]
    )

    reply = f"""{verdict}

{reason_text}

⚠️ This is a basic URL check, not a guarantee that the website is safe."""

    return jsonify({
        "reply": reply
    })


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

Image analysis

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

if name == "main":
app.run(debug=True)
