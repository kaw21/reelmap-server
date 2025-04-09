from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import os
import json
import base64
from PIL import Image
from io import BytesIO
from urllib.parse import urlparse

app = Flask(__name__)

# Load environment variables
AIML_API_KEY = os.environ.get("AIMLAPI_KEY")
PARSE_SERVER_URL = os.environ.get("PARSE_SERVER_URL")
PARSE_APP_ID = os.environ.get("PARSE_APP_ID")
PARSE_API_KEY = os.environ.get("PARSE_API_KEY")

# Data extraction and transformation functions
def extract_ig_data(url):
    headers = {
        "User-Agent": "Mozilla/5.0",
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
            {"role": "system", "content": "You are an Instagram Reels analyzer...Respond ONLY with JSON."},
            {"role": "user", "content": desc}
        ],
        "temperature": 0.7,
        "top_p": 0.9,
        "max_tokens": 512
    }
    r = requests.post("https://api.aimlapi.com/v1/chat/completions", headers=headers, json=body)
    return r.json()

def upload_image_to_parse(thumbnail_url):
    try:
        image_response = requests.get(thumbnail_url)
        if image_response.status_code == 200:
            image = Image.open(BytesIO(image_response.content)).convert("RGB")
            width, height = image.size
            if width > height and width > 1024:
                image = image.resize((1024, int((1024 / width) * height)))
            elif height > 1024:
                image = image.resize((int((1024 / height) * width), 1024))

            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            encoded_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            file_payload = {
                "base64": encoded_image,
                "contentType": "image/jpeg",
                "name": "thumbnail.jpg"
            }
            file_upload = requests.post(
                f"{PARSE_SERVER_URL.rstrip('/')}/files/thumbnail.jpg",
                headers={
                    "X-Parse-Application-Id": PARSE_APP_ID,
                    "X-Parse-REST-API-Key": PARSE_API_KEY,
                    "Content-Type": "application/json"
                },
                json=file_payload
            )
            if file_upload.status_code == 201:
                return file_upload.json()
    except Exception as e:
        print("Thumbnail upload failed:", e)
    return None

def save_to_parse(user, link, summary, thumbnail_url):
    geo = summary.get("geocode")
    geo_point = {"__type": "GeoPoint", "latitude": geo["lat"], "longitude": geo["lng"]} if geo else None
    parse_file = upload_image_to_parse(thumbnail_url)

    data = {
        "username": user,
        "ig_link": link,
        "title": summary["title"],
        "description": summary["description"],
        "tags": summary["tags"],
        "location": summary.get("location") or f"{geo['lat']},{geo['lng']}" if geo else "",
        "geocode": geo_point,
        "thumbnail_url": thumbnail_url
    }
    if parse_file:
        data["thumbnail"] = {"__type": "File", "name": parse_file.get("name")}

    full_url = f"{PARSE_SERVER_URL.rstrip('/')}/classes/aRM_ReelsData"
    r = requests.post(full_url, headers={
        "X-Parse-Application-Id": PARSE_APP_ID,
        "X-Parse-REST-API-Key": PARSE_API_KEY,
        "Content-Type": "application/json"
    }, json=data)
    return r.status_code, r.text

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    url = urlparse(data.get("link", ""))
    full_url = f"{url.scheme}://{url.netloc}{url.path}"
    description, thumbnail = extract_ig_data(full_url)
    result = analyze_with_llm(description)
    content = json.loads(result["choices"][0]["message"]["content"])
    content["image"] = thumbnail
    return jsonify(content)

@app.route("/save", methods=["POST"])
def save():
    data = request.json
    user = data.get("user")
    link = data.get("link")
    summary = data.get("summary")
    thumbnail = data.get("thumbnail")
    status, response = save_to_parse(user, link, summary, thumbnail)
    return jsonify({"status": status, "response": response})

@app.route("/analyzeSave", methods=["POST"])
def analyze_save():
    data = request.json
    url = urlparse(data.get("link", ""))
    full_url = f"{url.scheme}://{url.netloc}{url.path}"
    user = data.get("user", "")
    description, thumbnail = extract_ig_data(full_url)
    llm_result = analyze_with_llm(description)
    summary_json = json.loads(llm_result["choices"][0]["message"]["content"])
    status, response = save_to_parse(user, full_url, summary_json, thumbnail)

    tags_str = ", ".join([f"#{tag}" for tag in summary_json["tags"]])
    reply_text = f"🚀 Saved!\n📍 {summary_json['title']}\n🌍 Location: {summary_json.get('location') or summary_json['geocode']}\n📄 Tags: {tags_str}\n📷 [View Post]({full_url})"

    return jsonify({"messages": [{"text": reply_text}]})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
