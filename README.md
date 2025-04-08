# ReelMap Analyzer (HTML → AI → JSON)

A simple Flask API that:
1. Receives an Instagram Reels/Post link
2. Extracts the HTML metadata
3. Sends a description to AIMLAPI (LLaMA 3.2 Turbo)
4. Returns a structured JSON result

## Endpoint

POST `/analyze`

### Request Body

```json
{
  "user": "username",
  "link": "https://www.instagram.com/reel/xyz/"
}
