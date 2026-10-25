# Àránṣẹ́ — LinkedIn Post Scheduler

> A local-first desktop application for scheduling and automating LinkedIn posts, with resilient background execution and system tray integration.

**Àránṣẹ́** (Yorùbá for "helper" or "support") eliminates the friction of manual LinkedIn posting. Draft and queue posts locally through a modern desktop UI, then let the background daemon handle publishing — automatically recovering from network drops, captive portals, and expired tokens.

---

## ✨ Features

- **Decoupled architecture** — Close the UI anytime; the daemon runs silently in your system tray (< 40 MB RAM).
- **Network resilience** — Persistent retry counter survives Wi-Fi dropouts and captive portal redirects, pausing for up to 30 minutes until connectivity is restored.
- **Automated token refresh** — Intercepts 401 errors and exchanges your OAuth refresh token for a fresh access token without manual re-authentication.
- **Full CRUD queue management** — Schedule, edit, delete, and inspect pending posts with an ID-based selector.
- **Dual media support** — Attach images (`.jpg`, `.png`) or swipeable PDF carousels via LinkedIn's asset API.
- **Text formatting** — Apply **bold** and *italic* using Unicode math characters that render natively on LinkedIn.
- **Live character counter** — Enforces LinkedIn's 3,000-character limit in real time.
- **Toast notifications** — Native Windows notifications for post success, failures, and rate-limit alerts.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **UI** | CustomTkinter (hardware-accelerated dark/light theme) + tkcalendar |
| **Scheduler** | APScheduler (interval-based background jobs) |
| **HTTP** | httpx (async client with timeout support) |
| **Database** | SQLite with WAL mode for concurrent read/write |
| **Auth** | FastAPI + uvicorn (local OAuth 2.0 callback server) |
| **System Tray** | pystray + Pillow (custom icon) |
| **Notifications** | plyer (Windows Toast) |

---

## 📂 Project Structure

```
LinkedIn-Scheduler/
│
├── gui.py                # CustomTkinter dashboard for scheduling posts
├── daemon.py             # Background worker, system tray, and publish loop
├── db_manager.py         # SQLite connection handler (WAL mode)
├── auth_server.py        # Local OAuth 2.0 callback server (FastAPI)
├── get_urn.py            # One-shot script to fetch your LinkedIn profile URN
├── publish_text.py       # Standalone test script for text-only posts
├── requirements.txt      # Python dependencies
├── .env                  # LinkedIn API credentials (git-ignored)
├── aranse_icon.png       # System tray icon
└── README.md
```

---

## 🚀 Getting Started

### 1. Clone and install

```bash
git clone https://github.com/your-username/LinkedIn-Scheduler.git
cd LinkedIn-Scheduler
pip install -r requirements.txt
```

### 2. Configure credentials

Create a `.env` file in the project root with your LinkedIn Developer App credentials:

```env
CLIENT_ID=your_linkedin_client_id
CLIENT_SECRET=your_linkedin_client_secret
```

### 3. Authenticate (first run)

Start the local OAuth server and navigate to `http://localhost:8000/login` in your browser:

```bash
python auth_server.py
```

After authorizing, your access token is saved to `linkedin_token.json`.

### 4. Fetch your profile URN

```bash
python get_urn.py
```

This saves your LinkedIn profile URN to `linkedin_urn.txt`.

### 5. Run the application

Start the background daemon (adds an icon to your system tray):

```bash
python daemon.py
```

Then open the UI dashboard to schedule posts:

```bash
python gui.py
```

You can close the UI at any time — the daemon continues running in the tray.

---

## 📝 Usage

1. **Compose** — Enter a post name, write your content, and optionally attach media.
2. **Schedule** — Pick a future date and time, then click "Schedule Post."
3. **Manage** — Use the right panel to view your queue, edit posts by ID, or cancel scheduled posts.
4. **Publish** — The daemon checks every 60 seconds and publishes any posts whose scheduled time has arrived.

---

## ⚠️ Important Notes

- **LinkedIn API limits** — The free tier allows approximately 100 posts per day. The daemon will alert you if you hit the rate limit.
- **Token expiry** — Access tokens expire after ~60 days. The daemon automatically refreshes them using your stored refresh token.
- **Captive portals** — If your network redirects API calls to a login page, the daemon detects this and retries automatically.

---

## 🛡️ License

Distributed under the MIT License. See `LICENSE` for details.

---

## 🙏 Acknowledgments

Built for developers and professionals who want to maintain a consistent LinkedIn presence without the manual overhead.
