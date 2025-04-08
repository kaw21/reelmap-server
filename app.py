from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import os
import json

app = Flask(__name__)

# 🔐 Load environment variables
AIML_API_KEY = os.environ.get("AIMLAPI_KEY")
PARSE_SERVER_URL = os.environ.get("PARSE_SERVER_URL")
PARSE_APP_ID = os.environ.get("PARSE_APP_ID")
PARSE_API_KEY = os.environ.get("PARSE_API_KEY")

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

    if not desc:
        desc = "This Instagram post features a travel destination or food experience shared by a user."

    return desc, thumb

def analyze_with_llm(desc):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {AIML_API_KEY}"
    }

    body = {
        "model": "meta-llama/Llama-3.2-3B-Instruct-Turbo",
        "messages": [
            {
                "role": "system",
                "content": "You are an Instagram Reels analyzer. Given a user-written post or caption, return a JSON object with the following keys: title, description, tags (as a list), location, and geocode. Respond ONLY with JSON."
            },
            {
                "role": "user",
                "content": desc
            }
        ],
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 512
    }

    r = requests.post("https://api.aimlapi.com/v1/chat/completions", headers=headers, json=body)
    return r.json()

def save_to_parse(user, link, summary, thumbnail_url):
    headers = {
        "X-Parse-Application-Id": PARSE_APP_ID,
        "X-Parse-REST-API-Key": PARSE_API_KEY,
        "Content-Type": "application/json"
    }

    location_data = summary.get("location", {})
    geo_point = None
    if isinstance(location_data, dict) and "lat" in location_data and "lng" in location_data:
        geo_point = {
            "__type": "GeoPoint",
            "latitude": location_data["lat"],
            "longitude": location_data["lng"]
        }

    data = {
        "username": user,
        "ig_link": link,
        "title": summary["title"],
        "description": summary["description"],
        "tags": summary["tags"],
        "location": summary["geocode"],  # string version
        "geocode": geo_point,             # GeoPoint for mapping
        "thumbnail_url": thumbnail_url
    }

    r = requests.post(PARSE_SERVER_URL, headers=headers, json=data)
    print("Parse response:", r.status_code, r.text)
    return r.status_code, r.text

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    url = data.get("link", "")
    user = data.get("user", "")
    print("Request received for:", url)

    description, thumbnail_url = extract_ig_data(url)
    print("Extracted description:", description[:100])

    llm_result = analyze_with_llm(description)
    print("LLM raw response:", llm_result)

    summary_json = json.loads(llm_result["choices"][0]["message"]["content"])
    print("Parsed summary:", summary_json)

    print("Saving to Parse...")
    status, response = save_to_parse(user, url, summary_json, thumbnail_url)

    tags_str = ", ".join([f"#{tag}" for tag in summary_json["tags"]])
    reply_text = f"🚀 Saved!\n📍 {summary_json['title']}\n🌍 Location: {summary_json['geocode']}\n📄 Tags: {tags_str}\n📷 [View Post]({url})"

    return jsonify({
        "messages": [
            {"text": reply_text}
        ]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
