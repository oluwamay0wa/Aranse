import os
import sys
import time
import socket
import signal
import tempfile
import logging
from datetime import datetime
import httpx
from dotenv import load_dotenv
import db_manager

# --- Environment & Logging Setup ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

LINKEDIN_TOKEN = os.getenv("LINKEDIN_ACCESS_TOKEN")
LINKEDIN_AUTHOR_URN = os.getenv("LINKEDIN_AUTHOR_URN")  # e.g., "urn:li:person:XXXXXX"
MAX_RETRIES = 3
POLL_INTERVAL_SECONDS = 30

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(BASE_DIR, "daemon.log"), encoding="utf-8")
    ]
)

# --- Single Instance Lock ---
class SingleInstanceLock:
    """Ensures only one instance of the daemon runs simultaneously."""
    def __init__(self, port: int = 47382):
        self.port = port
        self.sock = None

    def acquire(self) -> bool:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.bind(("127.0.0.1", self.port))
            return True
        except socket.error:
            return False

    def release(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass


# --- Network & Captive Portal Resilience ---
def is_internet_available() -> bool:
    """
    Verifies actual internet connectivity by checking against a known endpoint
    and detecting campus Wi-Fi (e.g. Covenant University) portal redirects.
    """
    try:
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            response = client.get("https://www.linkedin.com")
            # If redirected to CU portal (e.g. https://internetlogin.cu.edu.ng/portal?)
            if response.status_code in (301, 302, 303, 307):
                redirect_loc = response.headers.get("location", "")
                if "internetlogin" in redirect_loc or "portal" in redirect_loc:
                    logging.warning("Captive portal detected (Campus Wi-Fi login required). Waiting...")
                    return False
            return response.status_code < 500
    except Exception as e:
        logging.warning(f"Network connectivity check failed: {e}")
        return False


# --- Cloud Media Handler ---
def download_cloud_media(url: str) -> str:
    """
    Downloads a cloud asset (Supabase Storage URL) to a temporary local file.
    Returns the file path.
    """
    if not url or not url.startswith(("http://", "https://")):
        return url

    ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=ext)

    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(url)
        resp.raise_for_status()
        temp_file.write(resp.content)
        temp_file.close()

    return temp_file.name


# --- LinkedIn Publishing API ---
def upload_image_asset(client: httpx.Client, headers: dict, file_path: str) -> str:
    """
    Executes the LinkedIn 3-step image asset registration & upload workflow.
    Returns the image asset URN.
    """
    # Step 1: Register Upload
    register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
    payload = {
        "registerUploadRequest": {
            "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
            "owner": LINKEDIN_AUTHOR_URN,
            "serviceRelationships": [
                {
                    "relationshipType": "OWNER",
                    "identifier": "urn:li:userGeneratedContent"
                }
            ]
        }
    }
    reg_resp = client.post(register_url, headers=headers, json=payload)
    reg_resp.raise_for_status()
    reg_data = reg_resp.json()

    upload_url = reg_data["value"]["uploadMechanism"][
        "com.linkedin.digitalmedia.uploading.VectorAssetUploadMechanism"
    ]["uploadUrl"]
    asset_urn = reg_data["value"]["asset"]

    # Step 2: Upload Binary Bytes
    with open(file_path, "rb") as f:
        image_bytes = f.read()

    upload_headers = {"Authorization": headers["Authorization"], "Content-Type": "application/octet-stream"}
    upload_resp = client.put(upload_url, headers=upload_headers, content=image_bytes)
    upload_resp.raise_for_status()

    return asset_urn


def publish_post_to_linkedin(content: str, media_url: str = None):
    """Publishes text or image posts to LinkedIn via UGC Posts API."""
    if not LINKEDIN_TOKEN or not LINKEDIN_AUTHOR_URN:
        raise ValueError("LINKEDIN_ACCESS_TOKEN and LINKEDIN_AUTHOR_URN must be set in .env")

    headers = {
        "Authorization": f"Bearer {LINKEDIN_TOKEN}",
        "X-Restli-Protocol-Version": "2.0.0",
        "Content-Type": "application/json"
    }

    local_temp_file = None
    try:
        with httpx.Client(timeout=60.0) as client:
            share_media_category = "NONE"
            media_attachments = []

            if media_url:
                logging.info(f"Downloading cloud media: {media_url}")
                local_temp_file = download_cloud_media(media_url)
                asset_urn = upload_image_asset(client, headers, local_temp_file)
                share_media_category = "IMAGE"
                media_attachments = [{"status": "READY", "media": asset_urn}]

            post_body = {
                "author": LINKEDIN_AUTHOR_URN,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": content},
                        "shareMediaCategory": share_media_category,
                        "media": media_attachments
                    }
                },
                "visibility": {
                    "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
                }
            }

            post_url = "https://api.linkedin.com/v2/ugcPosts"
            response = client.post(post_url, headers=headers, json=post_body)
            response.raise_for_status()
            logging.info("LinkedIn API accepted post payload.")

    finally:
        if local_temp_file and os.path.exists(local_temp_file):
            os.remove(local_temp_file)


# --- Core Daemon Execution Loop ---
class DaemonRunner:
    def __init__(self):
        self.running = True
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

    def shutdown(self, signum, frame):
        logging.info("Shutdown signal received. Exiting daemon safely...")
        self.running = False

    def process_queue(self):
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
        pending_posts = db_manager.get_pending_posts(now_str)

        if not pending_posts:
            return

        logging.info(f"Found {len(pending_posts)} post(s) due for publishing.")

        for post in pending_posts:
            post_id, content, media_url, retry_count = post

            if retry_count >= MAX_RETRIES:
                logging.error(f"Post {post_id} exceeded max retries. Marking as FAILED.")
                db_manager.mark_failed(post_id, "FAILED_EXCEEDED_RETRIES")
                continue

            try:
                logging.info(f"Executing Post ID: {post_id}...")
                publish_post_to_linkedin(content, media_url)
                db_manager.mark_published(post_id)
                logging.info(f"Post ID {post_id} successfully published and marked PUBLISHED.")

            except Exception as e:
                logging.error(f"Error publishing Post ID {post_id}: {e}")
                db_manager.increment_retry(post_id)

    def start(self):
        logging.info("Aranse Background Daemon initialized.")
        db_manager.init_db()

        while self.running:
            try:
                if is_internet_available():
                    self.process_queue()
                else:
                    logging.info("Waiting for internet connection / portal auth...")

            except Exception as e:
                logging.critical(f"Unhandled exception in daemon loop: {e}", exc_info=True)

            # Sleep in small increments for rapid signal response on exit
            for _ in range(POLL_INTERVAL_SECONDS):
                if not self.running:
                    break
                time.sleep(1)


if __name__ == "__main__":
    lock = SingleInstanceLock()
    if not lock.acquire():
        logging.warning("Another instance of Aranse daemon is already running. Exiting.")
        sys.exit(0)

    try:
        runner = DaemonRunner()
        runner.start()
    finally:
        lock.release()