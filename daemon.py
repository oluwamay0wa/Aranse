import asyncio
import json
import os
import subprocess
import time

from datetime import datetime

import httpx
import pystray
from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv
from PIL import Image
from plyer import notification

import db_manager

# 1. Resolve all absolute paths at the top
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, "linkedin_token.json")
URN_PATH = os.path.join(BASE_DIR, "linkedin_urn.txt")
ICON_PATH = os.path.join(BASE_DIR, "aranse_icon.png")
ENV_PATH = os.path.join(BASE_DIR, ".env")

# 2. Load the .env file using the absolute path
load_dotenv(ENV_PATH)
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

MAX_NETWORK_RETRIES = 30

def load_credentials():
    try:
        # 3. Use the absolute paths here
        with open(TOKEN_PATH, "r") as f:
            token_data = json.load(f)
            access_token = token_data.get("access_token")
        with open(URN_PATH, "r") as f:
            person_urn = f.read().strip()
        return access_token, person_urn
    except FileNotFoundError:
        return None, None

def create_icon_image():
    """Loads the custom Aranse icon from a local file using an absolute path."""
    try:
        # 4. Use the absolute path for the tray icon
        return Image.open(ICON_PATH)
    except FileNotFoundError:
        return Image.new('RGB', (64, 64), color=(0, 0, 0))

def verify_json_response(response):
    """Checks if the Wi-Fi portal intercepted the request before parsing JSON."""
    content_type = response.headers.get("Content-Type", "")

    # If the response isn't JSON, we've been redirected to the CU login portal
    if "application/json" not in content_type:
        raise httpx.RequestError(f"Captive portal intercept detected. Content-Type: {content_type}")

    try:
        return response.json()
    except json.JSONDecodeError:
        raise httpx.RequestError("Invalid JSON received. Network likely intercepted.")

def alert_user(title: str, message: str):
    try:
        notification.notify(title=title, message=message, app_name="LinkedIn Scheduler", timeout=10)
    except Exception:
        pass


def refresh_access_token() -> bool:
    """Exchanges the 365-day refresh token for a new 60-day access token."""
    try:
        with open(TOKEN_PATH, "r") as f:
            token_data = json.load(f)

        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            return False

        url = "https://www.linkedin.com/oauth/v2/accessToken"
        payload = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        response = httpx.post(url, data=payload)
        if response.status_code == 200:
            new_tokens = verify_json_response(response)
            # Update the dictionary while preserving the original refresh token if a new one wasn't issued
            token_data.update(new_tokens)
            with open(TOKEN_PATH, "w") as f:
                json.dump(token_data, f)
            return True
        else:
            print(f"Refresh failed: {response.text}")
            return False
    except Exception as e:
        print(f"Error during token refresh: {e}")
        return False


async def upload_media_to_linkedin(media_path: str, access_token: str, person_urn: str) -> str:
    if not os.path.exists(media_path):
        raise FileNotFoundError(f"Media not found at {media_path}")

    # Dynamically select the recipe based on the file extension
    is_pdf = media_path.lower().endswith('.pdf')
    recipe = "urn:li:digitalmediaRecipe:feedshare-document" if is_pdf else "urn:li:digitalmediaRecipe:feedshare-image"

    register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "X-RestLi-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }
    register_payload = {
        "registerUploadRequest": {
            "recipes": [recipe],
            "owner": person_urn,
            "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}]
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        reg_response = await client.post(register_url, headers=headers, json=register_payload)
        if reg_response.status_code == 401: return "ERROR_401"
        if reg_response.status_code != 200: raise Exception(f"Registration failed: {reg_response.text}")

        reg_data = verify_json_response(reg_response)
        upload_url = reg_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"][
            "uploadUrl"]
        asset_urn = reg_data["value"]["asset"]

        with open(media_path, "rb") as media_file:
            media_data = media_file.read()

        upload_headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/octet-stream"}
        upload_response = await client.put(upload_url, headers=upload_headers, content=media_data)
        if upload_response.status_code not in (200, 201): raise Exception(
            f"Media upload failed: {upload_response.text}")

        return asset_urn


async def publish_to_linkedin(content: str, media_path: str, access_token: str, person_urn: str) -> str:
    asset_urn = None
    media_category = "NONE"

    if media_path and media_path.strip():
        asset_urn = await upload_media_to_linkedin(media_path, access_token, person_urn)
        if asset_urn == "ERROR_401": return "ERROR_401"

        # Set the correct UGC post category
        media_category = "DOCUMENT" if media_path.lower().endswith('.pdf') else "IMAGE"

    share_content = {"shareCommentary": {"text": content}, "shareMediaCategory": media_category}

    if asset_urn:
        # Use the actual filename as the document title (looks better in the LinkedIn feed)
        file_title = os.path.basename(media_path)
        share_content["media"] = [{
            "status": "READY",
            "description": {"text": "Scheduled via Custom UI"},
            "media": asset_urn,
            "title": {"text": file_title}
        }]

    payload = {
        "author": person_urn, "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }

    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {"Authorization": f"Bearer {access_token}", "X-RestLi-Protocol-Version": "2.0.0",
               "Content-Type": "application/json"}

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    if response.status_code == 201:
        return "SUCCESS"
    elif response.status_code == 401:
        return "ERROR_401"
    elif response.status_code == 429:
        return "ERROR_429"
    else:
        return f"ERROR_{response.status_code}"

def check_and_publish():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    pending_posts = db_manager.get_pending_posts(now_str)
    if not pending_posts: return

    access_token, person_urn = load_credentials()
    if not access_token or not person_urn:
        alert_user("LinkedIn Scheduler Error", "Missing credentials. Run auth_server.py")
        return

    for post in pending_posts:
        post_id, content, image_path, retry_count = post
        print(f"\n[{now_str}] Executing post ID: {post_id}...")

        try:
            status = asyncio.run(publish_to_linkedin(content, image_path, access_token, person_urn))

            if status == "SUCCESS":
                db_manager.mark_published(post_id)
                print(f"Post {post_id} published successfully.")
            elif status == "ERROR_401":
                print("Access token expired. Attempting automated refresh...")
                if refresh_access_token():
                    print("Token refreshed successfully! Post will execute on the next minute cycle.")
                    # Notice we DO NOT mark it as failed here. It stays PENDING.
                else:
                    db_manager.mark_failed(post_id, "FAILED - EXPIRED TOKEN")
                    alert_user("LinkedIn Token Expired", "Automated refresh failed. Please log in manually.")
            elif status == "ERROR_429":
                db_manager.mark_failed(post_id, "FAILED - RATE LIMIT")
                alert_user("LinkedIn Rate Limit Hit", "You reached the 100 posts/day limit.")
            else:
                db_manager.mark_failed(post_id, f"FAILED - {status}")

        except httpx.RequestError:
            new_attempts = retry_count + 1
            if new_attempts <= MAX_NETWORK_RETRIES:
                print(
                    f"Network error on post {post_id} (Attempt {new_attempts}/{MAX_NETWORK_RETRIES}). Leaving as PENDING.")
                db_manager.increment_retry(post_id)
            else:
                db_manager.mark_failed(post_id, "FAILED - NETWORK TIMEOUT")
                alert_user("Post Failed", f"Network unavailable for {MAX_NETWORK_RETRIES} minutes. Post cancelled.")
        except Exception as e:
            db_manager.mark_failed(post_id, "FAILED - SCRIPT ERROR")


def on_open_ui(icon, item):
    """Launches the CustomTkinter UI dashboard."""
    gui_path = os.path.join(BASE_DIR, "gui.py")
    subprocess.Popen(["python", gui_path], shell=True)


def on_quit(icon, item):
    """Safely shuts down the scheduler and removes the tray icon."""
    print("Shutting down daemon...")
    scheduler.shutdown(wait=False)
    icon.stop()


if __name__ == "__main__":
    print("Daemon started. Check your system tray for the Aranse icon.")

    # Start the background scheduler — checks for pending posts every 60 seconds
    scheduler = BackgroundScheduler()
    scheduler.add_job(check_and_publish, "interval", seconds=60)
    scheduler.start()

    # Build the system tray menu
    menu = pystray.Menu(
        pystray.MenuItem("Open UI Dashboard", on_open_ui),
        pystray.MenuItem("Quit Scheduler", on_quit),
    )

    # Create and run the tray icon (this blocks and keeps the script alive)
    try:
        tray_icon = pystray.Icon(
            "LinkedInScheduler",
            create_icon_image(),
            "Àránṣẹ́ — LinkedIn Scheduler",
            menu,
        )
        tray_icon.run()
    finally:
        scheduler.shutdown(wait=False)