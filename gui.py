"""Àránṣẹ́ Dashboard — CustomTkinter UI for scheduling LinkedIn posts."""

import os
import time
import customtkinter as ctk
from tkcalendar import Calendar
from datetime import datetime
from supabase import create_client, Client
import db_manager

# Load environment variables for Supabase Storage
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase_client: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)

db_manager.init_db()

current_edit_id = None

def to_unicode_bold(text: str) -> str:
    return "".join(chr(ord(c) - ord('A') + 0x1D5D4) if 'A' <= c <= 'Z' else chr(
        ord(c) - ord('a') + 0x1D5EE) if 'a' <= c <= 'z' else c for c in text)


def to_unicode_italic(text: str) -> str:
    return "".join(chr(ord(c) - ord('A') + 0x1D608) if 'A' <= c <= 'Z' else chr(
        ord(c) - ord('a') + 0x1D622) if 'a' <= c <= 'z' else c for c in text)


def apply_format(format_type: str, textbox: ctk.CTkTextbox):
    try:
        first_index = textbox.tk.call(textbox._name, "index", "sel.first")
        last_index = textbox.tk.call(textbox._name, "index", "sel.last")
        selected = textbox.get(first_index, last_index)
        new_text = to_unicode_bold(selected) if format_type == "bold" else to_unicode_italic(selected)
        textbox.delete(first_index, last_index)
        textbox.insert(first_index, new_text)
        update_char_count()  # Update count after formatting
    except ctk.tkinter.TclError:
        pass


def open_calendar():
    top = ctk.CTkToplevel(app)
    top.title("Select Date")
    top.geometry("300x250")
    top.grab_set()
    cal = Calendar(top, selectmode='day', date_pattern='yyyy-mm-dd')
    cal.pack(pady=20, padx=20, fill="both", expand=True)

    def confirm_date():
        date_entry.delete(0, "end")
        date_entry.insert(0, cal.get_date())
        top.destroy()

    ctk.CTkButton(top, text="Confirm Date", command=confirm_date).pack(pady=10)


def select_image():
    file_path = ctk.filedialog.askopenfilename(
        title="Select Media",
        filetypes=[("Media files", "*.jpg *.jpeg *.png *.pdf")]
    )
    if file_path:
        image_path_var.set(file_path)


def refresh_queue_display():
    queue_textbox.configure(state="normal")
    queue_textbox.delete("0.0", "end")
    pending_posts = db_manager.get_all_pending_posts()

    if not pending_posts:
        queue_textbox.insert("0.0", "No posts scheduled.\n\nQueue is empty.")
    else:
        queue_textbox.insert("0.0", f"Total Scheduled: {len(pending_posts)}\n")
        queue_textbox.insert("end", "=" * 25 + "\n\n")
        for post in pending_posts:
            post_id, post_name, run_time, content = post
            queue_textbox.insert("end", f"[{post_id}] {post_name}\n📅 {run_time}\n\n")
    queue_textbox.configure(state="disabled")


def update_char_count(event=None):
    """Updates the character counter label on every keystroke."""
    content = post_textbox.get("0.0", "end-1c")  # end-1c ignores Tkinter's trailing newline
    count = len(content)
    char_label.configure(text=f"{count}/3000")

    if count > 3000:
        char_label.configure(text_color="red")
    else:
        char_label.configure(text_color="gray")


def load_for_editing(id_entry: ctk.CTkEntry, status_lbl: ctk.CTkLabel):
    global current_edit_id
    post_id_str = id_entry.get().strip()
    if not post_id_str.isdigit():
        status_lbl.configure(text="Error: Enter a valid numerical ID.", text_color="red")
        return

    post_id = int(post_id_str)
    post_data = db_manager.get_post_by_id(post_id)
    if not post_data:
        status_lbl.configure(text=f"Error: Post ID {post_id} not found.", text_color="red")
        return

    post_name, content, run_time, img_path = post_data
    date_part, time_part = run_time.split(" ")

    name_entry.delete(0, "end")
    name_entry.insert(0, post_name)

    date_entry.delete(0, "end")
    date_entry.insert(0, date_part)

    time_entry.delete(0, "end")
    time_entry.insert(0, time_part)

    image_path_var.set(img_path if img_path else "")

    post_textbox.delete("0.0", "end")
    post_textbox.insert("0.0", content)

    current_edit_id = post_id
    schedule_btn.configure(text="Update Post")
    status_lbl.configure(text=f"Editing Post ID {post_id}...", text_color="blue")
    id_entry.delete(0, "end")

    update_char_count()  # Refresh counter for loaded text


def cancel_post(id_entry: ctk.CTkEntry, status_lbl: ctk.CTkLabel):
    global current_edit_id
    post_id_str = id_entry.get().strip()
    if not post_id_str.isdigit():
        status_lbl.configure(text="Error: Enter a valid numerical ID.", text_color="red")
        return

    post_id = int(post_id_str)
    db_manager.delete_post(post_id)

    if current_edit_id == post_id:
        reset_form()

    id_entry.delete(0, "end")
    status_lbl.configure(text=f"Post ID {post_id} successfully deleted.", text_color="green")
    refresh_queue_display()


def reset_form():
    global current_edit_id
    current_edit_id = None
    name_entry.delete(0, "end")
    post_textbox.delete("0.0", "end")
    image_path_var.set("")
    schedule_btn.configure(text="Schedule Post")
    update_char_count()

def upload_media_if_local(local_path: str) -> str:
    """
    Uploads a local file to Supabase Storage and returns its public HTTPS URL.
    If the path is already a URL or empty, returns it as-is.
    """
    if not local_path or local_path.startswith("http://") or local_path.startswith("https://"):
        return local_path

    if not os.path.exists(local_path):
        raise FileNotFoundError(f"Selected media file not found: {local_path}")

    if not supabase_client:
        raise ValueError("Supabase storage client is not configured in .env")

    bucket_name = "post-media"
    file_ext = os.path.splitext(local_path)[1]
    timestamp = int(time.time())
    # Unique remote filename to avoid collisions
    cloud_filename = f"media_{timestamp}{file_ext}"

    with open(local_path, "rb") as f:
        supabase_client.storage.from_(bucket_name).upload(
            file=f,
            path=cloud_filename,
            file_options={"content-type": "auto"}
        )

    # Get the public HTTPS URL for the uploaded file
    public_url = supabase_client.storage.from_(bucket_name).get_public_url(cloud_filename)
    return public_url

def queue_job(status_lbl: ctk.CTkLabel):
    global current_edit_id
    post_name = name_entry.get().strip()
    content = post_textbox.get("0.0", "end-1c").strip()
    target_str = f"{date_entry.get().strip()} {time_entry.get().strip()}"
    img_path = image_path_var.get()

    if not post_name or not content:
        status_lbl.configure(text="Error: Post Name and Content are required.", text_color="red")
        return

    if len(content) > 3000:
        status_lbl.configure(text="Error: Content exceeds 3000 characters.", text_color="red")
        return

    try:
        target_dt = datetime.strptime(target_str, "%Y-%m-%d %H:%M")
        if target_dt < datetime.now():
            status_lbl.configure(text="Error: Cannot schedule posts in the past.", text_color="red")
            return

        status_lbl.configure(text="Uploading media to cloud...", text_color="orange")
        app.update()

        # Upload local image to Supabase Storage if present
        final_img_url = upload_media_if_local(img_path)

        if current_edit_id:
            db_manager.update_post(current_edit_id, post_name, content, target_str, final_img_url)
            status_lbl.configure(text=f"Success! Post {current_edit_id} updated.", text_color="green")
        else:
            db_manager.add_post(post_name, content, target_str, final_img_url)
            status_lbl.configure(text=f"Success! '{post_name}' queued.", text_color="green")

        reset_form()
        refresh_queue_display()

    except Exception as e:
        status_lbl.configure(text=f"Error: {str(e)}", text_color="red")

# --- UI Layout ---
app = ctk.CTk()
app.title("Àránṣẹ́")

screen_width = app.winfo_screenwidth()
screen_height = app.winfo_screenheight()

window_width = int(screen_width * 0.75)
window_height = int(screen_height * 0.75)

# Lowered safe minimums for standard laptop displays
window_width = max(window_width, 700)
window_height = max(window_height, 550)

# Prevent the window from exceeding the screen workspace (accounts for taskbar)
window_width = min(window_width, screen_width - 40)
window_height = min(window_height, screen_height - 80)

center_x = int((screen_width / 2) - (window_width / 2))
center_y = int((screen_height / 2) - (window_height / 2))

app.geometry(f"{window_width}x{window_height}+{center_x}+{center_y}")
app.minsize(700, 550)

left_frame = ctk.CTkFrame(app, fg_color="transparent")
left_frame.pack(side="left", fill="both", expand=True, padx=10, pady=10)

right_frame = ctk.CTkFrame(app, width=250)
right_frame.pack(side="right", fill="y", padx=10, pady=10)

# --- LEFT FRAME (Scheduling Tools) ---
toolbar = ctk.CTkFrame(left_frame)
toolbar.pack(pady=5, fill="x")
ctk.CTkButton(toolbar, text="Bold", width=60, command=lambda: apply_format("bold", post_textbox)).pack(
    side="left", padx=5
)
ctk.CTkButton(toolbar, text="Italic", width=60, command=lambda: apply_format("italic", post_textbox)).pack(
    side="left", padx=5
)

name_frame = ctk.CTkFrame(left_frame)
name_frame.pack(pady=5, fill="x")
ctk.CTkLabel(name_frame, text="Post Name:").pack(side="left", padx=5)
name_entry = ctk.CTkEntry(name_frame, width=300, placeholder_text="e.g., Q3 Launch Announcement")
name_entry.pack(side="left", padx=5, fill="x", expand=True)

datetime_frame = ctk.CTkFrame(left_frame)
datetime_frame.pack(pady=5, fill="x")
ctk.CTkLabel(datetime_frame, text="Date:").pack(side="left", padx=5)
date_entry = ctk.CTkEntry(datetime_frame, width=100)
date_entry.insert(0, datetime.now().strftime("%Y-%m-%d"))
date_entry.pack(side="left", padx=5)
ctk.CTkButton(datetime_frame, text="🗓️", width=30, command=open_calendar).pack(side="left", padx=2)

ctk.CTkLabel(datetime_frame, text="Time (HH:MM):").pack(side="left", padx=(15, 5))
time_entry = ctk.CTkEntry(datetime_frame, width=60)
time_entry.insert(0, datetime.now().strftime("%H:%M"))
time_entry.pack(side="left", padx=5)

image_frame = ctk.CTkFrame(left_frame)
image_frame.pack(pady=5, fill="x")
image_path_var = ctk.StringVar(value="")
ctk.CTkButton(image_frame, text="Attach Media", width=120, command=select_image).pack(side="left", padx=5)
ctk.CTkLabel(image_frame, textvariable=image_path_var, text_color="gray").pack(side="left", padx=5)

post_textbox = ctk.CTkTextbox(left_frame, height=120, wrap="word")
post_textbox.pack(pady=5, fill="both", expand=True)
post_textbox.bind("<KeyRelease>", update_char_count)

# Character count label
char_label = ctk.CTkLabel(left_frame, text="0/3000", text_color="gray")
char_label.pack(anchor="e", padx=10)

status_label = ctk.CTkLabel(left_frame, text="")
status_label.pack(pady=5)
schedule_btn = ctk.CTkButton(left_frame, text="Schedule Post", command=lambda: queue_job(status_label))
schedule_btn.pack(pady=10)

# --- RIGHT FRAME (Dashboard) ---
ctk.CTkLabel(right_frame, text="Upcoming Queue", font=("Arial", 16, "bold")).pack(pady=10)
queue_textbox = ctk.CTkTextbox(right_frame, width=230, wrap="word")
queue_textbox.pack(pady=5, padx=10, fill="both", expand=True)

action_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
action_frame.pack(pady=5, fill="x")
ctk.CTkLabel(action_frame, text="ID:").pack(side="left", padx=(5, 2))
action_entry = ctk.CTkEntry(action_frame, width=35)
action_entry.pack(side="left", padx=2)

ctk.CTkButton(
    action_frame, text="Edit", width=50,
    command=lambda: load_for_editing(action_entry, status_label),
).pack(side="left", padx=2)
ctk.CTkButton(
    action_frame, text="Delete", fg_color="red", hover_color="#8B0000", width=50,
    command=lambda: cancel_post(action_entry, status_label),
).pack(side="left", padx=2)

refresh_queue_display()
app.mainloop()