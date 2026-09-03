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

api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

@app.route("/")
def home():
return render_template("index.html")

SYSTEM_PROMPT = """
You are DASH, a friendly AI Digital Trust, Scam and Fraud Advisor.

Help users understand online scams, fraud, phishing messages,
suspicious websites and links, fake offers, and digital safety.

Give very short chatbot-style answers.
Maximum 4 short lines.
Keep answers under 70 words.

Do not claim with 100% certainty that a website is safe or fraudulent.
"""

def extract_url(text):
urls = re.findall(r'https?://[^\s]+|www.[^\s]+', text)
return urls[0] if urls else None

def analyze_url(url):
original_url = url

if not url.startswith(("http://", "https://")):
    url = "https://" + url

parsed = urlparse(url)
domain = parsed.netloc.lower()
path = parsed.path.lower()

risk_score = 0
reasons = []

if parsed.scheme != "https":
    risk_score += 2
    reasons.append("It does not use HTTPS.")

if re.match(r'^\d{1,3}(\.\d{1,3}){3}$', domain):
    risk_score += 3
    reasons.append("It uses an IP address instead of a normal domain.")

suspicious_keywords = [
    "login", "verify", "verification", "secure",
    "account", "password", "wallet", "bank",
    "upi", "gift", "free", "winner", "prize",
    "urgent", "offer", "payment", "refund"
]

keyword_count = sum(
    1 for keyword in suspicious_keywords
    if keyword in domain or keyword in path
)

if keyword_count >= 3:
    risk_score += 3
    reasons.append("The URL contains several suspicious keywords.")
elif keyword_count >= 1:
    risk_score += 1
    reasons.append("The URL contains a potentially sensitive keyword.")

if domain.count("-") >= 3:
    risk_score += 2
    reasons.append("The domain contains many hyphens.")

if len(domain) > 45:
    risk_score += 2
    reasons.append("The domain name is unusually long.")

if domain.count(".") >= 3:
    risk_score += 1
    reasons.append("The URL contains multiple subdomains.")

if "@" in original_url:
    risk_score += 3
    reasons.append("The URL contains an unusual @ symbol.")

if risk_score >= 5:
    verdict = "🚨 HIGH RISK / SUSPICIOUS"
elif risk_score >= 2:
    verdict = "⚠️ SUSPICIOUS — VERIFY BEFORE USING"
else:
    verdict = "🟡 NO OBVIOUS URL RED FLAGS"

if not reasons:
    reasons.append("No obvious suspicious URL pattern was detected.")

return verdict, reasons

@app.route("/chat", methods=["POST"])
def chat():
data = request.get_json()
user_message = data.get("message", "")

url = extract_url(user_message)

if url:
    verdict, reasons = analyze_url(url)
    reason_text = "\n".join(
        [f"• {reason}" for reason in reasons[:2]]
    )

    return jsonify({
        "reply": f"{verdict}\n\n{reason_text}\n\n⚠️ This is a basic URL check, not a guarantee."
    })

try:
    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=f"{SYSTEM_PROMPT}\n\nUser message:\n{user_message}"
    )

    return jsonify({
        "reply": response.text
    })

except Exception:
    return jsonify({
        "reply": "Sorry, something went wrong. Please try again."
    })

@app.route("/analyze-image", methods=["POST"])
def analyze_image():
try:
if "image" not in request.files:
return jsonify({
"reply": "⚠️ Please select an image first."
})

    image_file = request.files["image"]

    if image_file.filename == "":
        return jsonify({
            "reply": "⚠️ Please select an image first."
        })

    image = Image.open(
        io.BytesIO(image_file.read())
    )

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[
            f"""

{SYSTEM_PROMPT}

Analyze this uploaded image for visible scam or fraud warning signs.
It may contain a suspicious website, scam message, phishing email,
fake offer, or suspicious payment request.

Give a short answer.
""",
image
]
)

    return jsonify({
        "reply": response.text
    })

except Exception:
    return jsonify({
        "reply": "Sorry, I couldn't analyze this image. Please try again."
    })

if name == "main":
app.run(debug=True)
