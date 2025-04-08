from flask import Flask, request, jsonify
import requests
from bs4 import BeautifulSoup
import os
import json
import base64

app = Flask(__name__)

# 🔐 Load environment variables
AIML_API_KEY = os.environ.get("AIMLAPI_KEY")
PARSE_SERVER_URL = os.environ.get("PARSE_SERVER_URL")  # should be like: https://pg-app-xxx.scalabl.cloud/1
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

    location_data = summary.get("geocode")
    if isinstance(location_data, str):
        location_data = None
    geo_point = None
    if isinstance(location_data, dict) and "lat" in location_data and "lng" in location_data:
        geo_point = {
            "__type": "GeoPoint",
            "latitude": location_data["lat"],
            "longitude": location_data["lng"]
        }

    # Fetch and convert thumbnail image to base64 for Parse File
    parse_file = None
    try:
        image_response = requests.get(thumbnail_url)
        if image_response.status_code == 200:
            from PIL import Image
            from io import BytesIO

            image = Image.open(BytesIO(image_response.content)).convert("RGB")
            width, height = image.size
            if width > height:
                if width > 1024:
                    new_height = int((1024 / width) * height)
                    image = image.resize((1024, new_height))
            else:
                if height > 1024:
                    new_width = int((1024 / height) * width)
                    image = image.resize((new_width, 1024))

            buffer = BytesIO()
            image.save(buffer, format="JPEG", quality=85)
            encoded_image = base64.b64encode(buffer.getvalue()).decode('utf-8')
            file_payload = {
                "base64": encoded_image,
                "contentType": "image/jpeg",
                "name": "thumbnail.jpg"
            }
            file_upload = requests.post(
                PARSE_SERVER_URL.rstrip("/") + "/files/thumbnail.jpg",
                headers={
                    "X-Parse-Application-Id": PARSE_APP_ID,
                    "X-Parse-REST-API-Key": PARSE_API_KEY,
                    "Content-Type": "application/json"
                },
                json=file_payload
            )
            if file_upload.status_code == 201:
                parse_file = file_upload.json()
    except Exception as e:
        print("Thumbnail upload failed:", e)

    data = {
        "username": user,
        "ig_link": link,
        "title": summary["title"],
        "description": summary["description"],
        "tags": summary["tags"],
        "location": summary["geocode"],  # string version
        "geocode": geo_point,
        "thumbnail_url": thumbnail_url,
        "media_url": summary.get("media_url") if summary.get("media_url", "").startswith("https://lookaside.fbsbx.com/") else None
    }

    if parse_file:
        data["thumbnail"] = {
            "__type": "File",
            "name": parse_file.get("name")
        }

    full_url = PARSE_SERVER_URL.rstrip("/") + "/classes/aRM_ReelsData"
    r = requests.post(full_url, headers=headers, json=data)
    print("Parse response:", r.status_code, r.text)
    return r.status_code, r.text

@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.json
    url = data.get("link", "")
    user = data.get("user", "")
    media_url = data.get("media_url", "")
    print("Request received for:", url)

    description, thumbnail_url = extract_ig_data(url)
    print("Extracted description:", description[:100])

    llm_result = analyze_with_llm(description)
    print("LLM raw response:", llm_result)

    summary_json = json.loads(llm_result["choices"][0]["message"]["content"])

    if media_url.startswith("https://lookaside.fbsbx.com/"):
        summary_json["media_url"] = media_url

    print("Parsed summary:", summary_json)

    print("Saving to Parse...")
    status, response = save_to_parse(user, url, summary_json, thumbnail_url)

    tags_str = ", ".join([f"#{tag}" for tag in summary_json["tags"]])
    reply_text = f"\ud83d\ude80 Saved!\n\ud83d\udccd {summary_json['title']}\n\ud83c\udf0d Location: {summary_json['geocode']}\n\ud83d\udcc4 Tags: {tags_str}\n\ud83d\udcf7 [View Post]({url})"

    return jsonify({
        "messages": [
            {"text": reply_text}
        ]
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
