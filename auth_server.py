import json
import os
import urllib.parse

import httpx
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import RedirectResponse

# Resolve absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "linkedin_token.json")

# Load variables from the .env file
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = FastAPI()

# Pull credentials securely from environment variables
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URI = "http://localhost:8000/callback"

# The scopes required to sign in and post to your personal feed
SCOPES = "openid profile email w_member_social"


@app.get("/login")
def login_to_linkedin():
    """Step 1: Redirect the browser to LinkedIn's authorization page."""
    if not CLIENT_ID or not CLIENT_SECRET:
        return {"error": "Missing credentials. Check your .env file."}

    auth_url = "https://www.linkedin.com/oauth/v2/authorization"
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": "random_string_for_security_123",
        "scope": SCOPES
    }
    url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return RedirectResponse(url)


from typing import Optional


@app.get("/callback")
async def linkedin_callback(
    state: str,
    code: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
):
    """Step 2: Catch the redirect from LinkedIn and swap the code for a token."""
    if error:
        return {"error": error, "description": error_description}

    if not code:
        return {"error": "Missing code", "description": "No authorization code was provided by LinkedIn."}

    token_url = "https://www.linkedin.com/oauth/v2/accessToken"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET
    }

    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with httpx.AsyncClient() as client:
        response = await client.post(token_url, data=data, headers=headers)

    if response.status_code == 200:
        token_data = response.json()

        # Save the token locally to a JSON file
        with open(TOKEN_PATH, "w") as f:
            json.dump(token_data, f, indent=4)

        return {
            "message": "Success! Access token saved to linkedin_token.json",
            "expires_in_seconds": token_data.get("expires_in"),
        }
    else:
        return {"error": "Failed to retrieve token", "details": response.json()}


if __name__ == "__main__":
    # Run the local server on port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000)