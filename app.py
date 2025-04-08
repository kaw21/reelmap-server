from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import os

app = Flask(__name__)

AIML_API_KEY = os.environ.get("AIMLAPI_KEY")

def extract_ig_data(url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept-Language": "en-US,en;q=0.9"
    }
    r = requests.get(url, headers=headers)
    soup = BeautifulSoup(r.text, "html.parser")
    desc, thumb = "", ""

    for tag in soup.find_all("meta"):
        if tag.get("property") == "og:description":
            desc = tag.get("content")
        elif tag.get("property") == "og:image":
            thumb = tag.get("content")

    # Fallback for testing
    if not desc:
        desc = "This Instagram post features a travel destination or food experience shared by a user."

    return desc, thumb

def analyze_with_llm(desc):
    prompt = f"""
You are an Instagram Reels analyzer. Given the content below, extract and return:

- title (short summary)
- description (1–2 sentences)
- tags (3–5 relevant keywords)
- location (city or place)
- geocode (Google Maps friendly location string)

Content:
\"{desc}\"

Output in JSON only.
"""

    payload = {
        "prompt": prompt,
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 512
    }

    headers = {
        "Content-Type": "application/json",
        "X-API-Key": AIML_API_KEY
    }

    r = requests.post(
    	"https://api.aimlapi.com/v1/completions",
    	json={
        	"model": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
        	"prompt": prompt,
        	"temperature": 0.7,
        	"top_p": 0.9,
        	"max_tokens": 512
    	},
    	headers=headers
	)


    return r.json()

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    url = data.get("link", "")
    user = data.get("user", "")

    description, thumbnail = extract_ig_data(url)
    llm_result = analyze_with_llm(description)

    return jsonify({
        "user": user,
        "link": url,
        "thumbnail": thumbnail,
        "description": description,
        "llm": llm_result
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
