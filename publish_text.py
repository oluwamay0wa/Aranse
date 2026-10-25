import asyncio
import json
import os

import httpx

# Resolve absolute paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "linkedin_token.json")
URN_PATH = os.path.join(BASE_DIR, "linkedin_urn.txt")


def to_unicode_bold(text: str) -> str:
    """Converts standard text to Unicode bold characters for LinkedIn."""
    bold_text = ""
    for char in text:
        if "A" <= char <= "Z":
            bold_text += chr(ord(char) - ord("A") + 0x1D5D4)
        elif "a" <= char <= "z":
            bold_text += chr(ord(char) - ord("a") + 0x1D5EE)
        else:
            bold_text += char
    return bold_text


async def publish_text_post():
    """Publish a text-only test post to LinkedIn using saved credentials."""
    try:
        with open(TOKEN_PATH, "r") as f:
            access_token = json.load(f).get("access_token")
        with open(URN_PATH, "r") as f:
            person_urn = f.read().strip()
    except FileNotFoundError:
        print("Missing credentials files. Run auth_server.py and get_urn.py first.")
        return

    # 2. Format your text using the workarounds
    headline = to_unicode_bold("Automated API Test")

    # Use \n\n to force a full empty line space in the UI
    body_text = f"{headline}\n\nThis is the first paragraph.\n\nThis is the second paragraph, separated by a full blank line. When you eventually build your UI, replacing standard UI line breaks with '\\n' before passing it to this payload will preserve your spacing."

    # 3. Configure the API Request
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-RestLi-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    # shareMediaCategory must be "NONE" for text-only posts
    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {
                    "text": body_text
                },
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }

    # 4. Fire the post
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code == 201:
        print("Successfully published text post to LinkedIn!")
    else:
        print(f"Failed to post: {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    asyncio.run(publish_text_post())