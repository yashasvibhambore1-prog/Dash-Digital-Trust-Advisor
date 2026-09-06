import os
import json
import re
from dotenv import load_dotenv
from flask import Flask, request, jsonify, render_template_string
from google import genai
from google.genai import types
from PIL import Image

load_dotenv()

app = Flask(__name__)

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError(
        "GEMINI_API_KEY not found. Create a .env file and add:\n"
        "GEMINI_API_KEY=your_actual_api_key"
    )

client = genai.Client(api_key=API_KEY)

SYSTEM_PROMPT = '''
You are an intelligent AI Scam and Fraud Advisor.

Analyze suspicious links, websites, URLs, messages, advertisements,
online offers, and uploaded screenshots or images.

Identify specific signs of:
- Scams
- Phishing
- Fraud
- Fake offers
- Impersonation
- Suspicious payment requests
- Fake rewards
- UPI fraud
- OTP fraud
- Fake websites

Never invent information that is not visible or provided.
Do not say something is definitely safe or definitely a scam unless there
is clear evidence. If information is insufficient, clearly say that.

Always respond ONLY with valid JSON in exactly this structure:
{
  "risk_level": "LOW",
  "risk_percentage": 20,
  "suspicious_details": [
    {
      "detail": "Exact suspicious detail",
      "reason": "Why this is suspicious"
    }
  ],
  "why_scam": "Explain the possible scam technique in simple language",
  "safety_advice": [
    "Practical safety advice 1",
    "Practical safety advice 2",
    "Practical safety advice 3"
  ],
  "summary": "Short final conclusion"
}

risk_level must be only LOW, MEDIUM, or HIGH.

risk_percentage must be a whole number from 0 to 100 showing how likely
this is to be a scam/fraud (0 = definitely safe, 100 = certainly a
scam), consistent with risk_level: roughly 0-30 for LOW, 31-70 for
MEDIUM, 71-100 for HIGH.

When analyzing URLs, consider misspelled brands, suspicious domains,
random characters, misleading subdomains, fake login pages, password
requests, OTP requests, bank information requests, and UPI requests.

When analyzing offers, consider unrealistic prices, huge discounts,
too-good-to-be-true claims, fake cashback or rewards, urgency, and
advance payment requests.

When analyzing screenshots, inspect all visible URLs, text, logos, prices,
discounts, phone numbers, email addresses, payment instructions, UPI IDs,
QR codes, verification badges, spelling mistakes, urgency messages,
popups, and requests for sensitive information.

Be specific and explain exactly what looks suspicious.
'''


def fallback_result(message="Further verification is recommended."):
    return {
        "risk_level": "MEDIUM",
        "risk_percentage": 50,
        "suspicious_details": [
            {
                "detail": "The information could not be fully verified automatically.",
                "reason": message
            }
        ],
        "why_scam": "The available information does not allow a complete automatic verification.",
        "safety_advice": [
            "Do not make a payment until the source is verified.",
            "Do not share OTPs, passwords, or banking details.",
            "Verify the information through an official source."
        ],
        "summary": message
    }


def clean_json(text):
    if not text:
        return None

    text = text.strip()
    text = text.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def analyze_with_ai(user_prompt, image=None):
    try:
        contents = [SYSTEM_PROMPT, user_prompt]

        if image is not None:
            contents.append(image)

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=contents,
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level="minimal"
                )
            )
        )

        result = clean_json(response.text)

        if not isinstance(result, dict):
            return fallback_result()

        risk = str(result.get("risk_level", "MEDIUM")).upper()

        if risk not in {"LOW", "MEDIUM", "HIGH"}:
            risk = "MEDIUM"

        result["risk_level"] = risk

        try:
            percentage = int(result.get("risk_percentage", 50))
        except (TypeError, ValueError):
            percentage = 50

        result["risk_percentage"] = max(0, min(100, percentage))

        if not isinstance(result.get("suspicious_details"), list):
            result["suspicious_details"] = []

        if not isinstance(result.get("safety_advice"), list):
            result["safety_advice"] = []

        result.setdefault("why_scam", "No additional explanation was available.")
        result.setdefault("summary", "Further verification is recommended.")

        return result

    except json.JSONDecodeError:
        return fallback_result(
            "The AI response could not be converted into the required format."
        )

    except Exception as error:
        return {
            "risk_level": "MEDIUM",
            "risk_percentage": 50,
            "suspicious_details": [
                {
                    "detail": "Analysis could not be completed.",
                    "reason": str(error)
                }
            ],
            "why_scam": "The AI analysis system encountered an error.",
            "safety_advice": [
                "Do not make a payment.",
                "Do not share personal or banking information.",
                "Check your internet connection and API key, then try again."
            ],
            "summary": "Analysis unavailable."
        }


CHAT_SYSTEM_PROMPT = '''
You are a friendly AI Scam and Fraud Advisor chatbot.

The user has been using a security tool to check a link, message, offer,
or screenshot. They have only seen a risk level and risk percentage so
far — NOT the detailed breakdown. Answer their follow-up question about
that specific check in a clear, short, conversational way (2-5
sentences). No markdown.

If analysis context is provided, use its risk_level, risk_percentage,
suspicious_details, why_scam, and safety_advice to explain exactly
what's wrong and what to do, in plain language. Don't just repeat the
summary — actually walk through the real reasons.

If no analysis context is provided, answer using general scam-safety
knowledge and suggest the user run an analysis first for a specific
answer.
'''


def chat_with_ai(section, question, content=None, analysis=None):
    try:
        context_parts = [f"The user is currently using the '{section}' security tool."]

        if content:
            context_parts.append(f"Content that was submitted for analysis: {content}")

        if analysis:
            context_parts.append(f"Previous AI analysis result (JSON): {json.dumps(analysis)}")

        context_parts.append(f"User question: {question}")

        user_prompt = "\n\n".join(context_parts)

        response = client.models.generate_content(
            model="gemini-3.5-flash-lite",
            contents=[CHAT_SYSTEM_PROMPT, user_prompt],
            config=types.GenerateContentConfig(
                thinking_config=types.ThinkingConfig(
                    thinking_level="minimal"
                )
            )
        )

        answer = (response.text or "").strip()

        if not answer:
            answer = "I couldn't come up with an answer for that. Could you rephrase your question?"

        return answer

    except Exception as error:
        if "RESOURCE_EXHAUSTED" in str(error) or "429" in str(error):
            return (
                "I'm getting a lot of requests right now and hit my daily "
                "limit. Please try again in a little while."
            )
        return "Sorry, I couldn't process that question right now. Please try again."


@app.route("/")
def home():
    return render_template_string(r'''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Scam and Fraud Advisor</title>

<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg:#07090d;--panel:#10141b;--panel2:#151a23;--border:#252d3a;--text:#f4f7fb;--muted:#929aaa}
body{font-family:Arial,Helvetica,sans-serif;background:var(--bg);color:var(--text)}
button,input,textarea{font-family:inherit}
.app{min-height:100vh;display:flex}
.sidebar{width:255px;min-height:100vh;position:fixed;left:0;top:0;padding:22px 14px;background:#0b0e13;border-right:1px solid var(--border)}
.logo{display:flex;align-items:center;gap:12px;padding:12px 10px;margin-bottom:42px}
.logo-icon{width:45px;height:45px;border-radius:13px;display:grid;place-items:center;font-size:23px;background:white;color:black}
.logo h1{font-size:18px;letter-spacing:.2px}
.logo p{color:var(--muted);font-size:10px;margin-top:4px}
.menu-title{padding:0 11px;margin-bottom:12px;color:#687182;font-size:10px;letter-spacing:1.5px}
.nav-button{width:100%;border:1px solid transparent;background:transparent;color:#9ca5b5;padding:14px;margin-bottom:7px;border-radius:11px;text-align:left;cursor:pointer;font-size:14px;transition:.2s}
.nav-button:hover{background:#151a23;color:white}
.nav-button.active{background:white;color:#090b0f;font-weight:bold}
.nav-icon{display:inline-block;width:30px}
.main{width:calc(100% - 255px);margin-left:255px;padding:34px 48px 50px}
.top{display:flex;justify-content:space-between;align-items:center;margin-bottom:35px}
.system-label{color:#7f8999;font-size:10px;letter-spacing:1.5px;margin-bottom:8px}
#pageTitle{font-size:29px}
.online{padding:10px 16px;border:1px solid var(--border);border-radius:999px;color:#aab3c1;font-size:12px;background:var(--panel)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:#54e68a;margin-right:7px}
.section{display:none}.section.active{display:block}
.hero{min-height:280px;border:1px solid var(--border);border-radius:22px;padding:48px;display:flex;justify-content:space-between;align-items:center;background:radial-gradient(circle at 85% 25%,rgba(255,255,255,.09),transparent 22%),linear-gradient(135deg,#151a22,#090b10)}
.hero h1{font-size:45px;margin-bottom:17px}
.hero p{max-width:590px;color:var(--muted);line-height:1.7}
.shield{font-size:100px;margin-right:60px}
.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:17px;margin-top:22px}
.card{background:var(--panel);border:1px solid var(--border);border-radius:17px;padding:24px;cursor:pointer;transition:transform .2s,border-color .2s}
.card:hover{transform:translateY(-5px);border-color:#586273}
.card-icon{width:47px;height:47px;display:grid;place-items:center;border-radius:13px;background:var(--panel2);font-size:21px;margin-bottom:17px}
.card h3{font-size:15px;margin-bottom:9px}.card p{font-size:12px;color:var(--muted);line-height:1.55}
.tool,.result{max-width:980px}
.tool{background:var(--panel);border:1px solid var(--border);border-radius:20px;padding:34px}
.tool-header{margin-bottom:25px}.tool-header h2{font-size:22px;margin-bottom:9px}.tool-header p{color:var(--muted);font-size:13px}
input,textarea{width:100%;background:#090c11;border:1px solid #2a3240;border-radius:11px;color:white;padding:16px;outline:none;font-size:14px}
input:focus,textarea:focus{border-color:#7b8492}
textarea{min-height:180px;resize:vertical}
.button{margin-top:15px;border:none;background:white;color:#080a0d;padding:14px 24px;border-radius:10px;cursor:pointer;font-weight:bold}
.button:hover{opacity:.86}.button:disabled{opacity:.5;cursor:not-allowed}
.upload{min-height:220px;border:2px dashed #343d4b;border-radius:16px;display:flex;flex-direction:column;justify-content:center;align-items:center;cursor:pointer;color:#9ca5b5;text-align:center}
.upload:hover{border-color:#788393}.upload-icon{font-size:42px;margin-bottom:12px}.upload h3{color:white;margin-bottom:8px}
.preview img{display:block;max-width:100%;max-height:360px;margin:18px auto 0;border-radius:12px;border:1px solid var(--border)}
.result{margin-top:22px}.loading,.result-box{background:var(--panel);border:1px solid var(--border);border-radius:18px;padding:28px}
.loading{text-align:center;color:var(--muted)}
.result-top{display:flex;justify-content:space-between;align-items:center;gap:15px;border-bottom:1px solid var(--border);padding-bottom:19px;margin-bottom:23px}
.result-top h2{font-size:19px}
.risk{padding:8px 14px;border-radius:999px;font-size:11px;font-weight:bold}
.low{background:#143526;color:#76efaa}.medium{background:#3a3217;color:#ffda66}.high{background:#3b1719;color:#ff8589}
.risk-gauge-wrap{margin-bottom:22px}
.risk-gauge-label{display:flex;justify-content:space-between;font-size:13px;color:var(--muted);margin-bottom:8px}
.risk-gauge-track{width:100%;height:16px;background:#0d1015;border-radius:10px;overflow:hidden;border:1px solid var(--border)}
.risk-gauge-fill{height:100%;border-radius:10px;transition:width .6s ease}
.risk-gauge-fill.low{background:linear-gradient(90deg,#1f8a4c,#4cff8d)}
.risk-gauge-fill.medium{background:linear-gradient(90deg,#a3841a,#ffd75c)}
.risk-gauge-fill.high{background:linear-gradient(90deg,#8a1f1f,#ff7777)}
.ask-chatbot-cta{margin-top:6px;padding:16px 18px;background:var(--panel2);border:1px dashed var(--border);border-radius:12px;display:flex;justify-content:space-between;align-items:center;gap:14px;flex-wrap:wrap}
.ask-chatbot-cta p{color:var(--muted);font-size:13px;margin:0}
.ask-chatbot-btn{background:white;color:#080a0d;border:none;padding:10px 18px;border-radius:10px;font-weight:bold;font-size:13px;cursor:pointer;white-space:nowrap}
.ask-chatbot-btn:hover{opacity:.85}
.result-section{margin-bottom:23px}.result-section h3{font-size:14px;margin-bottom:12px}.result-section p{color:#b0b8c4;font-size:13px;line-height:1.7}
.warning{background:var(--panel2);border-left:3px solid #7b8492;padding:15px;border-radius:8px;margin-bottom:10px}
.warning strong{display:block;margin-bottom:6px}.warning p{color:#aab3c1;font-size:13px;line-height:1.6}
.advice{list-style:none}.advice li{background:var(--panel2);color:#b0b8c4;padding:13px;border-radius:9px;margin-bottom:8px;font-size:13px}
.error{background:#331719;border:1px solid #6c2c30;color:#ffb2b5;padding:16px;border-radius:12px}

.chat-page{max-width:900px;height:calc(100vh - 205px);min-height:520px;background:var(--panel);border:1px solid var(--border);border-radius:20px;display:flex;flex-direction:column;overflow:hidden}
.chat-header{padding:20px 24px;background:#0b0e13;border-bottom:1px solid var(--border);display:flex;justify-content:space-between;align-items:center}
.chat-header h3{font-size:17px;margin-bottom:4px}
.chat-header span{color:var(--muted);font-size:12px}
.chat-header-icon{width:42px;height:42px;border-radius:12px;background:var(--panel2);display:grid;place-items:center;font-size:19px}
.chat-header-left{display:flex;align-items:center;gap:13px}
.chat-body{flex:1;overflow-y:auto;padding:24px;display:flex;flex-direction:column;gap:13px}
.chat-msg{max-width:72%;padding:13px 16px;border-radius:14px;font-size:14px;line-height:1.6;white-space:pre-wrap}
.chat-msg.user{align-self:flex-end;background:white;color:#080a0d}
.chat-msg.bot{align-self:flex-start;background:var(--panel2);color:#dfe4ec;border:1px solid var(--border)}
.chat-typing{align-self:flex-start;color:var(--muted);font-size:12.5px;padding:2px 4px}
.chat-suggestions{padding:0 20px 14px;display:flex;flex-wrap:wrap;gap:9px;border-top:1px solid var(--border);padding-top:14px}
.chat-chip{background:var(--panel2);border:1px solid var(--border);color:#c3cad6;padding:9px 14px;border-radius:999px;font-size:12.5px;cursor:pointer;transition:.2s}
.chat-chip:hover{border-color:#788393;color:white}
.chat-input-row{display:flex;gap:10px;padding:18px 20px;border-top:1px solid var(--border)}
.chat-input-row input{flex:1;padding:14px 16px;font-size:14px}
.chat-send{background:white;color:#080a0d;border:none;border-radius:10px;padding:0 22px;cursor:pointer;font-weight:bold}
.chat-send:disabled{opacity:.5;cursor:not-allowed}

@media(max-width:950px){.cards{grid-template-columns:repeat(2,1fr)}}
@media(max-width:680px){.sidebar{width:74px;padding:20px 8px}.logo{justify-content:center;padding:8px}.logo-text,.menu-title,.nav-text{display:none}.nav-button{text-align:center}.nav-icon{width:auto;font-size:18px}.main{margin-left:74px;width:calc(100% - 74px);padding:25px 15px}.online{display:none}.hero{padding:30px}.hero h1{font-size:33px}.shield{display:none}.cards{grid-template-columns:1fr}.tool{padding:24px}.chat-page{max-width:100%;height:calc(100vh - 260px)}}
</style>
</head>

<body>
<div class="app">
<aside class="sidebar">
    <div class="logo">
        <div class="logo-icon">🛡️</div>
        <div class="logo-text">
            <h1>AI Scam and Fraud Advisor</h1>
            <p>AI SECURITY PLATFORM</p>
        </div>
    </div>

    <div class="menu-title">SECURITY TOOLS</div>

    <button class="nav-button active" onclick="showSection('dashboard',this)"><span class="nav-icon">▦</span><span class="nav-text">Dashboard</span></button>
    <button class="nav-button" onclick="showSection('chat',this)"><span class="nav-icon">💬</span><span class="nav-text">AI Chat Assistant</span></button>
    <button class="nav-button" onclick="showSection('link',this)"><span class="nav-icon">🔗</span><span class="nav-text">Analyze Link</span></button>
    <button class="nav-button" onclick="showSection('message',this)"><span class="nav-icon">💬</span><span class="nav-text">Analyze Message</span></button>
    <button class="nav-button" onclick="showSection('offer',this)"><span class="nav-icon">🏷️</span><span class="nav-text">Check Offer</span></button>
    <button class="nav-button" onclick="showSection('image',this)"><span class="nav-icon">🖼️</span><span class="nav-text">Scan Image</span></button>
</aside>

<main class="main">
    <div class="top">
        <div>
            <div class="system-label">AI SECURITY PLATFORM</div>
            <h2 id="pageTitle">Security Dashboard</h2>
        </div>
        <div class="online"><span class="dot"></span>System Online</div>
    </div>

    <section id="dashboard" class="section active">
        <div class="hero">
            <div>
                <h1>Check before you trust.</h1>
                <p>Analyze suspicious links, websites, messages, online offers and screenshots using AI-powered scam and fraud detection.</p>
            </div>
            <div class="shield">🛡️</div>
        </div>

        <div class="cards">
            <div class="card" onclick="goTo('link')"><div class="card-icon">🔗</div><h3>Analyze Link</h3><p>Check suspicious websites and URLs for warning signs.</p></div>
            <div class="card" onclick="goTo('message')"><div class="card-icon">💬</div><h3>Analyze Message</h3><p>Detect possible phishing and scam messages.</p></div>
            <div class="card" onclick="goTo('offer')"><div class="card-icon">⚡</div><h3>Check Offer</h3><p>Identify suspicious discounts and online offers.</p></div>
            <div class="card" onclick="goTo('image')"><div class="card-icon">🖼️</div><h3>Scan Image</h3><p>Analyze suspicious screenshots and advertisements.</p></div>
        </div>
    </section>

    <section id="chat" class="section">
        <div class="chat-page">
            <div class="chat-header">
                <div class="chat-header-left">
                    <div class="chat-header-icon">🛡️</div>
                    <div>
                        <h3>Scam Advisor Assistant</h3>
                        <span id="chatContext">Ask about: Security Dashboard</span>
                    </div>
                </div>
            </div>
            <div class="chat-body" id="chatBody"></div>
            <div class="chat-suggestions" id="chatSuggestions"></div>
            <div class="chat-input-row">
                <input id="chatInput" type="text" placeholder="Type your question..." onkeydown="if(event.key==='Enter'){sendChatMessage();}">
                <button class="chat-send" id="chatSendBtn" onclick="sendChatMessage()">Send</button>
            </div>
        </div>
    </section>

    <section id="link" class="section">
        <div class="tool">
            <div class="tool-header"><h2>Analyze Link or Website</h2><p>Enter a suspicious website URL for AI security analysis.</p></div>
            <input id="urlInput" type="text" placeholder="https://example.com">
            <button id="urlButton" class="button" onclick="analyzeText('url')">Analyze Website</button>
        </div>
        <div id="urlResult" class="result"></div>
    </section>

    <section id="message" class="section">
        <div class="tool">
            <div class="tool-header"><h2>Analyze Suspicious Message</h2><p>Paste an SMS, WhatsApp, email or social media message.</p></div>
            <textarea id="messageInput" placeholder="Paste suspicious message here..."></textarea>
            <button id="messageButton" class="button" onclick="analyzeText('message')">Scan Message</button>
        </div>
        <div id="messageResult" class="result"></div>
    </section>

    <section id="offer" class="section">
        <div class="tool">
            <div class="tool-header"><h2>Check Online Offer</h2><p>Enter details about a suspicious product deal or advertisement.</p></div>
            <textarea id="offerInput" placeholder="Example: A ₹50,000 phone is available for ₹499 and the seller says pay immediately through UPI..."></textarea>
            <button id="offerButton" class="button" onclick="analyzeText('offer')">Analyze Offer</button>
        </div>
        <div id="offerResult" class="result"></div>
    </section>

    <section id="image" class="section">
        <div class="tool">
            <div class="tool-header"><h2>Scan Screenshot or Image</h2><p>Upload a suspicious website, offer, advertisement or message screenshot.</p></div>
            <label class="upload" for="imageInput">
                <div class="upload-icon">☁️</div>
                <h3>Upload Screenshot</h3>
                <p>Click here to select an image</p>
                <input type="file" id="imageInput" accept="image/*" hidden>
            </label>
            <div id="preview" class="preview"></div>
            <button id="imageButton" class="button" onclick="analyzeImage()">Scan Image</button>
        </div>
        <div id="imageResult" class="result"></div>
    </section>
</main>
</div>

<script>
const titles = {
    dashboard: "Security Dashboard",
    chat: "AI Chat Assistant",
    link: "Analyze Link",
    message: "Analyze Message",
    offer: "Check Offer",
    image: "Scan Image"
};

const SECTION_QUESTIONS = {
    dashboard: [
        "What is phishing?",
        "How do online scams usually work?",
        "What are common warning signs of fraud?",
        "How can I stay safe online?"
    ],
    link: [
        "What is wrong with this link?",
        "How much percent risky is it?",
        "Is this link safe to open?",
        "What should I do if I already clicked it?"
    ],
    message: [
        "What is suspicious about this message?",
        "How much percent risky is it?",
        "Should I reply to this message?",
        "What should I do if I already responded?"
    ],
    offer: [
        "What is wrong with this offer?",
        "How much percent risky is it?",
        "Is this deal too good to be true?",
        "What should I do if I already paid?"
    ],
    image: [
        "What is wrong with this screenshot?",
        "How much percent risky is it?",
        "What details here look suspicious?",
        "What should I do next?"
    ]
};

let currentSection = "dashboard";
let activeToolSection = "dashboard";
const lastAnalysis = {};

function showSection(id, button) {
    document.querySelectorAll(".section").forEach(section => section.classList.remove("active"));
    document.querySelectorAll(".nav-button").forEach(nav => nav.classList.remove("active"));
    document.getElementById(id).classList.add("active");
    if (button) button.classList.add("active");
    document.getElementById("pageTitle").textContent = titles[id];

    currentSection = id;

    if (id !== "chat") {
        activeToolSection = id;
    }

    updateChatContext();

    if (id === "chat" && !document.getElementById("chatBody").hasChildNodes()) {
        appendChatMessage(
            "bot",
            "Hi! I'm your scam safety assistant. Ask me about the " +
            titles[activeToolSection].toLowerCase() +
            " tool, or pick one of the questions below."
        );
    }
}

function goTo(id) {
    const index = {link:2, message:3, offer:4, image:5}[id];
    showSection(id, document.querySelectorAll(".nav-button")[index]);
}

function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function showLoading(resultId) {
    document.getElementById(resultId).innerHTML =
        '<div class="loading">🔍 AI is analyzing the information...</div>';
}

function showError(resultId, message) {
    document.getElementById(resultId).innerHTML =
        `<div class="error">${escapeHtml(message)}</div>`;
}

function renderResult(resultId, data) {
    const risk = String(data.risk_level || "MEDIUM").toUpperCase();
    const riskClass = risk.toLowerCase();

    let percent = parseInt(data.risk_percentage, 10);
    if (isNaN(percent)) percent = 50;
    percent = Math.max(0, Math.min(100, percent));

    document.getElementById(resultId).innerHTML = `
        <div class="result-box">
            <div class="result-top">
                <h2>Security Analysis Result</h2>
                <span class="risk ${riskClass}">${escapeHtml(risk)} RISK</span>
            </div>
            <div class="risk-gauge-wrap">
                <div class="risk-gauge-label">
                    <span>How risky is this?</span>
                    <span>${percent}%</span>
                </div>
                <div class="risk-gauge-track">
                    <div class="risk-gauge-fill ${riskClass}" style="width:${percent}%"></div>
                </div>
            </div>
            <div class="ask-chatbot-cta">
                <p>Want to know exactly what's wrong and what to do next?<br>Ask the Chatbot Assistant for the full breakdown.</p>
                <button type="button" class="ask-chatbot-btn" onclick="goAskChatbot()">💬 Ask Chatbot</button>
            </div>
        </div>`;
}

function goAskChatbot() {
    const chatButton = document.querySelectorAll(".nav-button")[1];
    showSection("chat", chatButton);
    setTimeout(() => {
        sendChatMessage("What exactly is wrong with this, and what should I do?");
    }, 150);
}

async function analyzeText(type) {
    const map = {
        url: {input:"urlInput", result:"urlResult", button:"urlButton", label:"URL or website"},
        message: {input:"messageInput", result:"messageResult", button:"messageButton", label:"message"},
        offer: {input:"offerInput", result:"offerResult", button:"offerButton", label:"offer"}
    };

    const config = map[type];
    const value = document.getElementById(config.input).value.trim();

    if (!value) {
        showError(config.result, `Please enter a ${config.label} first.`);
        return;
    }

    const button = document.getElementById(config.button);
    button.disabled = true;
    showLoading(config.result);

    try {
        const response = await fetch("/analyze/text", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({type:type, content:value})
        });

        const data = await response.json();

        if (!response.ok || data.error) {
            throw new Error(data.error || "Analysis failed.");
        }

        renderResult(config.result, data);

        const sectionMap = {url: "link", message: "message", offer: "offer"};
        lastAnalysis[sectionMap[type]] = {content: value, analysis: data};
    } catch (error) {
        showError(config.result, error.message || "Unable to analyze the information.");
    } finally {
        button.disabled = false;
    }
}

document.getElementById("imageInput").addEventListener("change", function() {
    const file = this.files[0];
    const preview = document.getElementById("preview");

    if (!file) {
        preview.innerHTML = "";
        return;
    }

    const reader = new FileReader();
    reader.onload = event => {
        preview.innerHTML = `<img src="${event.target.result}" alt="Selected image preview">`;
    };
    reader.readAsDataURL(file);
});

async function analyzeImage() {
    const input = document.getElementById("imageInput");
    const resultId = "imageResult";
    const button = document.getElementById("imageButton");

    if (!input.files || input.files.length === 0) {
        showError(resultId, "Please upload an image first.");
        return;
    }

    const formData = new FormData();
    formData.append("image", input.files[0]);

    button.disabled = true;
    showLoading(resultId);

    try {
        const response = await fetch("/analyze/image", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok || data.error) {
            throw new Error(data.error || "Image analysis failed.");
        }

        renderResult(resultId, data);

        lastAnalysis["image"] = {
            content: "Uploaded screenshot image (see prior analysis result for details).",
            analysis: data
        };
    } catch (error) {
        showError(resultId, error.message || "Unable to analyze the image.");
    } finally {
        button.disabled = false;
    }
}

function updateChatContext() {
    document.getElementById("chatContext").textContent = "Ask about: " + titles[activeToolSection];
    renderChatSuggestions();
}

function renderChatSuggestions() {
    const questions = SECTION_QUESTIONS[activeToolSection] || SECTION_QUESTIONS.dashboard;
    const container = document.getElementById("chatSuggestions");
    container.innerHTML = "";

    questions.forEach(question => {
        const chip = document.createElement("div");
        chip.className = "chat-chip";
        chip.textContent = question;
        chip.onclick = () => sendChatMessage(question);
        container.appendChild(chip);
    });
}

function appendChatMessage(role, text) {
    const body = document.getElementById("chatBody");
    const msg = document.createElement("div");
    msg.className = "chat-msg " + role;
    msg.textContent = text;
    body.appendChild(msg);
    body.scrollTop = body.scrollHeight;
}

async function sendChatMessage(presetQuestion) {
    const input = document.getElementById("chatInput");
    const question = (typeof presetQuestion === "string" ? presetQuestion : input.value.trim());

    if (!question) return;

    appendChatMessage("user", question);
    input.value = "";

    const sendBtn = document.getElementById("chatSendBtn");
    sendBtn.disabled = true;

    const body = document.getElementById("chatBody");
    const typing = document.createElement("div");
    typing.className = "chat-typing";
    typing.id = "chatTyping";
    typing.textContent = "Assistant is typing...";
    body.appendChild(typing);
    body.scrollTop = body.scrollHeight;

    const context = lastAnalysis[activeToolSection] || {};

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                section: activeToolSection,
                question: question,
                content: context.content || null,
                analysis: context.analysis || null
            })
        });

        const data = await response.json();
        const typingEl = document.getElementById("chatTyping");
        if (typingEl) typingEl.remove();

        if (!response.ok || data.error) {
            appendChatMessage("bot", data.error || "Sorry, something went wrong.");
        } else {
            appendChatMessage("bot", data.answer);
        }
    } catch (error) {
        const typingEl = document.getElementById("chatTyping");
        if (typingEl) typingEl.remove();
        appendChatMessage("bot", "Sorry, I could not reach the server. Please try again.");
    } finally {
        sendBtn.disabled = false;
    }
}
</script>
</body>
</html>
''')


@app.route("/analyze/text", methods=["POST"])
def analyze_text():
    data = request.get_json(silent=True) or {}
    content = str(data.get("content", "")).strip()
    analysis_type = str(data.get("type", "")).strip().lower()

    if not content:
        return jsonify({"error": "No content was provided."}), 400

    labels = {
        "url": "URL or website",
        "message": "message",
        "offer": "online offer"
    }

    label = labels.get(analysis_type, "content")
    prompt = f"Analyze the following {label} for possible scam or fraud signs.\n\nCONTENT:\n{content}"

    return jsonify(analyze_with_ai(prompt))


@app.route("/analyze/image", methods=["POST"])
def analyze_image():
    if "image" not in request.files:
        return jsonify({"error": "No image was uploaded."}), 400

    file = request.files["image"]

    if not file or file.filename == "":
        return jsonify({"error": "Please select an image."}), 400

    try:
        image = Image.open(file.stream)
        image.load()
    except Exception:
        return jsonify({"error": "The uploaded file is not a valid image."}), 400

    prompt = (
        "Analyze this uploaded screenshot or image for possible scam, phishing, "
        "fraud, fake offers, impersonation, suspicious payment requests, UPI or "
        "OTP fraud. Inspect only information visibly present in the image."
    )

    return jsonify(analyze_with_ai(prompt, image=image))


@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    section = str(data.get("section", "general")).strip().lower() or "general"
    question = str(data.get("question", "")).strip()
    content = data.get("content")
    analysis = data.get("analysis")

    if not question:
        return jsonify({"error": "Please enter a question."}), 400

    answer = chat_with_ai(section, question, content=content, analysis=analysis)
    return jsonify({"answer": answer})


if __name__ == "__main__":
    app.run(debug=True)
