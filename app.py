import streamlit as st
import os
os.environ["REQUESTS_CA_BUNDLE"] = ""
os.environ["CURL_CA_BUNDLE"] = ""
import hashlib
import json
import io
import os
import tempfile
import wave
import time
from datetime import datetime
from pathlib import Path

# Google Drive
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# ─────────────────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Lisan ud Dawat — Voice Recorder",
    page_icon="🎙️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ─────────────────────────────────────────────────────────────────────────────
# USERS  (username → password + Drive folder name)
# To change a password:
#   python3 -c "import hashlib; print(hashlib.sha256('NEWPASS'.encode()).hexdigest())"
# ─────────────────────────────────────────────────────────────────────────────
USERS = {
    # Passwords are unique per recorder — share each row ONLY with that person
    # Format: memorable word + separator + unique code
    "recorder_01": {"name": "Recorder 01", "password_hash": hashlib.sha256("Falak#7mw9".encode()).hexdigest(), "folder": "recorder_01"},
    "recorder_02": {"name": "Recorder 02", "password_hash": hashlib.sha256("Zarqa!4nt2".encode()).hexdigest(), "folder": "recorder_02"},
    "recorder_03": {"name": "Recorder 03", "password_hash": hashlib.sha256("Noor$8vk3x".encode()).hexdigest(), "folder": "recorder_03"},
    "recorder_04": {"name": "Recorder 04", "password_hash": hashlib.sha256("Dawat%6ry1".encode()).hexdigest(), "folder": "recorder_04"},
    "recorder_05": {"name": "Recorder 05", "password_hash": hashlib.sha256("Qalam@3bz7".encode()).hexdigest(), "folder": "recorder_05"},
    "recorder_06": {"name": "Recorder 06", "password_hash": hashlib.sha256("Ilm#5ph2w".encode()).hexdigest(),  "folder": "recorder_06"},
    "recorder_07": {"name": "Recorder 07", "password_hash": hashlib.sha256("Safar!9dj4".encode()).hexdigest(), "folder": "recorder_07"},
    "recorder_08": {"name": "Recorder 08", "password_hash": hashlib.sha256("Huda$2cx6q".encode()).hexdigest(), "folder": "recorder_08"},
    "recorder_09": {"name": "Recorder 09", "password_hash": hashlib.sha256("Badar%7ym5".encode()).hexdigest(), "folder": "recorder_09"},
    "recorder_10": {"name": "Recorder 10", "password_hash": hashlib.sha256("Zikr@1wf8n".encode()).hexdigest(), "folder": "recorder_10"},
    "recorder_11": {"name": "Recorder 11", "password_hash": hashlib.sha256("Lisan#4kp3".encode()).hexdigest(), "folder": "recorder_11"},
    "recorder_12": {"name": "Recorder 12", "password_hash": hashlib.sha256("Kitab!6tz9".encode()).hexdigest(), "folder": "recorder_12"},
    "recorder_13": {"name": "Recorder 13", "password_hash": hashlib.sha256("Rawh$3mj7v".encode()).hexdigest(), "folder": "recorder_13"},
    "recorder_14": {"name": "Recorder 14", "password_hash": hashlib.sha256("Sunn%8rx2g".encode()).hexdigest(), "folder": "recorder_14"},
    "recorder_15": {"name": "Recorder 15", "password_hash": hashlib.sha256("Hilal@5nb1".encode()).hexdigest(), "folder": "recorder_15"},
    "admin":        {"name": "Admin",       "password_hash": hashlib.sha256("LisanAdmin#2025".encode()).hexdigest(), "folder": None, "is_admin": True},
}

# ─────────────────────────────────────────────────────────────────────────────
# GOOGLE DRIVE  — reads credentials from Streamlit secrets
# In Streamlit Cloud: Settings → Secrets → paste your service account JSON
# Locally: create .streamlit/secrets.toml with [gcp_service_account] section
# ─────────────────────────────────────────────────────────────────────────────
ROOT_FOLDER_NAME = "TRANSCRIBER_DATASET"   # The folder you created in your Drive

@st.cache_resource
def get_drive_service():
    """
    Authenticates as the Drive OWNER using OAuth2 refresh token.
    This means files are uploaded to the owner's Drive with their quota.
    Works with free Gmail — no Google Workspace needed.

    secrets.toml must have:
    [oauth_credentials]
    client_id     = "..."
    client_secret = "..."
    refresh_token = "..."
    """
    o = dict(st.secrets["oauth_credentials"])
    creds = Credentials(
        token=None,
        refresh_token=o["refresh_token"],
        client_id=o["client_id"],
        client_secret=o["client_secret"],
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/drive"]
    )
    creds.refresh(Request())   # get a fresh access token
    return build("drive", "v3", credentials=creds)

def drive_find_folder(service, name, parent_id=None):
    """Find a folder by name, optionally inside a parent."""
    q = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        q += f" and '{parent_id}' in parents"
    res = service.files().list(q=q, fields="files(id,name)", spaces="drive").execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None

def drive_create_folder(service, name, parent_id=None):
    """Create a folder in Drive."""
    meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        meta["parents"] = [parent_id]
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]

def drive_get_or_create_folder(service, name, parent_id=None):
    fid = drive_find_folder(service, name, parent_id)
    if not fid:
        fid = drive_create_folder(service, name, parent_id)
    return fid

def drive_list_files(service, folder_id, extension=".txt"):
    """List files in a folder with given extension."""
    q = f"'{folder_id}' in parents and trashed=false and name contains '{extension}'"
    files = []
    page_token = None
    while True:
        res = service.files().list(q=q, fields="nextPageToken, files(id,name)", orderBy="name", pageSize=1000, pageToken=page_token).execute()
        files.extend(res.get("files", []))
        page_token = res.get("nextPageToken", None)
        if page_token is None:
            break
    return files

def drive_read_text_file(service, file_id):
    """Download and read a text file from Drive."""
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue().decode("utf-8").strip()

def drive_file_exists(service, folder_id, filename):
    """Check if a file already exists in a folder."""
    q = f"'{folder_id}' in parents and name='{filename}' and trashed=false"
    res = service.files().list(q=q, fields="files(id,name)").execute()
    return len(res.get("files", [])) > 0

def drive_upload_audio(service, audio_bytes, filename, folder_id, mime_type="audio/webm"):
    """Upload audio bytes to a specific Drive folder. Overwrites if exists."""
    q = f"'{folder_id}' in parents and name='{filename}' and trashed=false"
    res = service.files().list(q=q, fields="files(id)").execute()
    existing = res.get("files", [])
    
    media = MediaIoBaseUpload(io.BytesIO(audio_bytes), mimetype=mime_type, resumable=False)
    
    if existing:
        # Overwrite the first existing file
        file = service.files().update(fileId=existing[0]["id"], media_body=media, fields="id,name").execute()
        # Clean up any accidental duplicates
        for dup in existing[1:]:
            try: service.files().delete(fileId=dup["id"]).execute()
            except: pass
        return file
    else:
        # Create new
        meta = {"name": filename, "parents": [folder_id]}
        file = service.files().create(body=meta, media_body=media, fields="id,name").execute()
        return file

def drive_delete_file(service, file_id):
    """Permanently delete a file from Drive (used on reject)."""
    service.files().delete(fileId=file_id).execute()


# ─────────────────────────────────────────────────────────────────────────────
# FOLDER ID CACHE  (so we don't re-query Drive on every rerun)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_folder_ids(user_folder_name):
    """Return (root_id, user_id, texts_id, audios_id) for a recorder."""
    for attempt in range(3):
        try:
            service = get_drive_service()
            root_id    = drive_get_or_create_folder(service, ROOT_FOLDER_NAME)
            user_id_f  = drive_get_or_create_folder(service, user_folder_name, root_id)
            texts_id   = drive_get_or_create_folder(service, "texts",  user_id_f)
            audios_id  = drive_get_or_create_folder(service, "audios", user_id_f)
            return root_id, user_id_f, texts_id, audios_id
        except Exception as e:
            if attempt == 2: raise e
            time.sleep(1)

@st.cache_data(ttl=60)
def get_text_files(texts_folder_id):
    for attempt in range(3):
        try:
            service = get_drive_service()
            return drive_list_files(service, texts_folder_id, ".txt")
        except Exception as e:
            if attempt == 2: raise e
            time.sleep(1)

@st.cache_data(ttl=60)
def get_audio_files(audios_folder_id):
    for attempt in range(3):
        try:
            service = get_drive_service()
            return drive_list_files(service, audios_folder_id, "")
        except Exception as e:
            if attempt == 2: raise e
            time.sleep(1)

# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────
def check_login(username, password):
    username = username.strip()
    password = password.strip()
    if username in USERS:
        if USERS[username]["password_hash"] == hashlib.sha256(password.encode()).hexdigest():
            return True
    return False

# ─────────────────────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Amiri:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --bg-main: #f3f4f6; 
    --bg-panel: rgba(255, 255, 255, 0.85);
    --border-color: rgba(0, 0, 0, 0.08);
    --gold-primary: #b8860b; /* Dark goldenrod for contrast */
    --gold-glow: rgba(184, 134, 11, 0.15);
    --text-main: #1f2937;
    --text-muted: #6b7280;
    --accent-success: #059669;
}

/* Base Global Styles */
html, body, [data-testid="stAppViewContainer"] {
    background-color: var(--bg-main) !important; 
    color: var(--text-main) !important;
    font-family: 'Inter', sans-serif !important;
}
[data-testid="block-container"] {
    padding-top: 1.5rem !important;
    padding-bottom: 1rem !important;
}
.stMarkdown { margin-bottom: -0.5rem !important; }
hr { margin: 0.5rem 0 !important; }

/* Animated Soft Background */
[data-testid="stAppViewContainer"]::before {
    content: "";
    position: fixed;
    top: -50%; left: -50%; width: 200%; height: 200%;
    background: radial-gradient(circle at 50% 50%, rgba(184, 134, 11, 0.04) 0%, transparent 60%),
                radial-gradient(circle at 80% 20%, rgba(184, 134, 11, 0.03) 0%, transparent 40%);
    z-index: -1;
    animation: slowSpin 60s linear infinite;
}

@keyframes slowSpin { 100% { transform: rotate(360deg); } }

/* Clean UI - Hide defaults */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }

/* Inputs */
.stTextInput input {
    background: rgba(255, 255, 255, 0.9) !important; 
    color: var(--text-main) !important;
    border: 1px solid var(--border-color) !important; 
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    padding: 0.75rem 1rem !important;
    transition: all 0.3s ease !important;
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.02);
}
.stTextInput input:focus { 
    border-color: var(--gold-primary) !important; 
    box-shadow: 0 0 10px var(--gold-glow), inset 0 2px 4px rgba(0,0,0,0.02) !important; 
    background: #ffffff !important;
}

/* Premium Buttons */
.stButton > button {
    background: #ffffff !important;
    color: var(--gold-primary) !important;
    border: 1px solid rgba(184, 134, 11, 0.4) !important; 
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important; 
    font-weight: 600 !important;
    letter-spacing: 0.05em !important; 
    text-transform: uppercase;
    padding: 0.6rem 1.5rem !important;
    transition: all 0.3s ease !important;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
}
.stButton > button:hover { 
    background: var(--gold-primary) !important; 
    color: #ffffff !important; 
    border-color: var(--gold-primary) !important;
    box-shadow: 0 4px 15px var(--gold-glow) !important;
    transform: translateY(-2px);
}
.stButton > button:active { transform: translateY(1px); }

/* Progress Bar */
.stProgress > div > div > div > div { background-color: var(--gold-primary) !important; }

/* Text & Typography */
hr { border-color: var(--border-color) !important; margin: 2rem 0; }
label, .stMarkdown p { color: var(--text-main) !important; font-size: 0.95rem !important; font-weight: 400; }
strong { color: var(--gold-primary); font-weight: 600; }

/* Arabic Text Box (Premium Light Glassmorphism) */
.arabic-text {
    font-family: 'Amiri', serif !important; 
    font-size: 1.9rem !important;
    line-height: 1.8 !important; 
    color: #111827 !important; /* Very dark slate for high readability */
    direction: rtl !important; 
    text-align: center !important;
    background: #ffffff; 
    border: 1px solid rgba(0,0,0,0.05);
    box-shadow: 0 4px 15px rgba(0,0,0,0.04);
    padding: 1.2rem;
    border-radius: 12px; 
    margin: 0.5rem 0;
    position: relative;
}
.arabic-text::before {
    content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
    background: linear-gradient(90deg, transparent, var(--gold-primary), transparent); opacity: 0.8;
}

/* Cards & Containers */
.card { 
    background: var(--bg-panel); 
    border: 1px solid var(--border-color); 
    border-radius: 12px; 
    padding: 2rem; 
    margin: 1rem 0;
    backdrop-filter: blur(10px);
    box-shadow: 0 4px 20px rgba(0,0,0,0.05);
}

/* Stats */
.stat-box { 
    text-align: center; 
    background: #ffffff; 
    border: 1px solid var(--border-color); 
    border-radius: 12px; 
    padding: 1.5rem 1rem; 
    box-shadow: 0 2px 10px rgba(0,0,0,0.03);
    transition: transform 0.3s ease, border-color 0.3s ease;
}
.stat-box:hover { transform: translateY(-5px); border-color: rgba(184, 134, 11, 0.4); }
.stat-num { font-size: 2.5rem; font-weight: 700; color: var(--gold-primary); line-height: 1; margin-bottom: 0.5rem; }
.stat-label { font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.15em; font-weight: 600; }

/* Headers */
.title-main { 
    font-family: 'Amiri', serif; 
    font-size: 3rem; 
    color: var(--gold-primary); 
    text-align: center;
    margin-bottom: 0.2rem;
}
.subtitle { 
    font-size: 0.85rem; 
    color: var(--text-muted); 
    text-align: center; 
    letter-spacing: 0.2em; 
    text-transform: uppercase; 
    font-weight: 600;
}

/* Badges */
.badge { 
    display: inline-block; padding: 0.25rem 0.6rem; border-radius: 4px; 
    font-size: 0.65rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; 
}
.done { background: rgba(5,150,105,0.1); color: var(--accent-success); border: 1px solid rgba(5,150,105,0.2); }
.now { background: rgba(184,134,11,0.1); color: var(--gold-primary); border: 1px solid rgba(184,134,11,0.3); animation: pulse 2s infinite; }
.pending { color: #9ca3af; }

@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(184,134,11,0.2); } 70% { box-shadow: 0 0 0 6px rgba(184,134,11,0); } 100% { box-shadow: 0 0 0 0 rgba(184,134,11,0); } }

/* Audio Input UI override */
[data-testid="stAudioInput"] {
    background: #ffffff;
    border: 1px solid var(--border-color);
    border-radius: 12px;
    padding: 1.5rem;
    box-shadow: 0 4px 15px rgba(0,0,0,0.03);
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
for key, val in [("logged_in", False), ("user_id", None), ("recorded_audio", None),
                 ("recorded_name", None), ("current_txt_index", None)]:
    if key not in st.session_state:
        st.session_state[key] = val

# ═════════════════════════════════════════════════════════════════════════════
# LOGIN
# ═════════════════════════════════════════════════════════════════════════════
def show_login():
    st.markdown('<div class="title-main">لسان الدعوت</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Voice Data Collection System</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        with st.container():
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown("**[ SECURE LOGIN ]**")
            st.markdown("---")
            username = st.text_input("Username", placeholder="recorder_01")
            password = st.text_input("Password", type="password", placeholder="••••••••")
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("→ LOGIN", use_container_width=True):
                if check_login(username, password):
                    st.session_state.logged_in = True
                    st.session_state.user_id = username
                    st.session_state.recorded_audio = None
                    st.session_state.recorded_name = None
                    st.rerun()
                else:
                    st.error("Invalid username or password.")
            st.markdown('</div>', unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# RECORDER PAGE
# ═════════════════════════════════════════════════════════════════════════════
def show_recorder():
    service = get_drive_service()
    user_id = st.session_state.user_id
    user    = USERS[user_id]

    # ── get Drive folder IDs
    with st.spinner("Connecting..."):
        _, user_folder_id, texts_folder_id, audios_folder_id = get_folder_ids(user["folder"])
        text_files = get_text_files(texts_folder_id)
        audio_files = get_audio_files(audios_folder_id)

    if not text_files:
        st.warning("No text files found in your Drive texts folder. Ask admin to upload them.")
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()
        return

    # ── calculate progress
    total = len(text_files)
    done_stems = {Path(af["name"]).stem for af in audio_files if not af["name"].endswith(".json")}
    done_set = {tf["name"] for tf in text_files if Path(tf["name"]).stem in done_stems}
    done = len(done_set)
    pct = int(done / total * 100) if total else 0

    if done == total and total > 0:
        st.success("🎉 All recordings complete! Excellent work.")
        st.balloons()
        if st.button("Logout"):
            st.session_state.logged_in = False
            st.rerun()
        return

    # ── header & progress inline
    c1, c2, c3 = st.columns([3, 4, 1.5])
    with c1: 
        st.markdown(f'<div style="font-family:\'Amiri\',serif; font-size:1.6rem; color:#b8860b; font-weight:bold; line-height:1.2;">لسان الدعوت</div><div style="font-size:0.75rem; color:#6b7280; text-transform:uppercase;">{user["name"]}</div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div style="font-size:0.85rem; margin-bottom:0.2rem; font-weight:600;">Progress: {done}/{total} ({pct}%)</div>', unsafe_allow_html=True)
        st.progress(pct / 100)
    with c3:
        if st.button("Logout", use_container_width=True):
            for k in ["logged_in","user_id","recorded_audio","recorded_name","current_txt_index"]:
                st.session_state[k] = False if k == "logged_in" else None
            st.rerun()

    # ── Navigation
    if "rec_nav_index" not in st.session_state or st.session_state.get("rec_nav_user") != user_id:
        st.session_state.rec_nav_index = next((i for i, tf in enumerate(text_files) if tf["name"] not in done_set), 0)
        st.session_state.rec_nav_user  = user_id

    idx = max(0, min(st.session_state.rec_nav_index, total - 1))
    st.session_state.rec_nav_index = idx
    cur_txt = text_files[idx]
    
    st.markdown("<hr style='margin: 0.5rem 0;'>", unsafe_allow_html=True)

    nav_col1, nav_col2, nav_col3, nav_col4 = st.columns([1, 3, 1, 2])
    with nav_col1:
        if st.button("◀ Prev", key="nav_prev", use_container_width=True, disabled=(idx == 0)):
            st.session_state.rec_nav_index = idx - 1
            st.rerun()
    with nav_col2:
        labels = [f"{'✓' if tf['name'] in done_set else '○'} {i+1:03d}. {Path(tf['name']).stem}" for i, tf in enumerate(text_files)]
        chosen = st.selectbox("Jump", options=range(total), format_func=lambda i: labels[i], index=idx, key="nav_select", label_visibility="collapsed")
        if chosen != idx:
            st.session_state.rec_nav_index = chosen
            st.rerun()
    with nav_col3:
        if st.button("Next ▶", key="nav_next", use_container_width=True, disabled=(idx == total - 1)):
            st.session_state.rec_nav_index = idx + 1
            st.rerun()
    with nav_col4:
        next_unrecorded = next((i for i, tf in enumerate(text_files) if tf["name"] not in done_set), None)
        if st.button("⏭ Next Unrecorded", key="nav_jump", use_container_width=True, disabled=(next_unrecorded is None or next_unrecorded == idx)):
            st.session_state.rec_nav_index = next_unrecorded
            st.rerun()

    txt_name = cur_txt["name"]
    txt_stem = Path(txt_name).stem
    is_done  = cur_txt["name"] in done_set

    status_badge = '<span style="color:#059669; font-weight:bold; font-size:0.8rem;">✓ RECORDED</span>' if is_done else '<span style="color:#d97706; font-weight:bold; font-size:0.8rem;">○ PENDING</span>'
    st.markdown(f'<div style="display:flex; justify-content:space-between; align-items:center; margin-top:0.5rem;"><div><span style="font-size:0.9rem; font-weight:600;">📄 File: {txt_name}</span> &nbsp; {status_badge}</div></div>', unsafe_allow_html=True)
    
    # ── Instructions and limit
    st.markdown(f'<div style="background:#fff3cd; color:#856404; padding:0.4rem 0.8rem; border-radius:6px; font-size:0.85rem; font-weight:600; text-align:center; border:1px solid #ffeeba; margin-bottom: 0.5rem;">⚠️ IMPORTANT: Audio MUST be 30 seconds or less! Over 30s will NOT be submitted. Record & track time in your mind.</div>', unsafe_allow_html=True)

    # ── Audio Recorder
    audio_value = st.audio_input("🎙️ Record (Max 30s)", key=f"audio_input_{txt_stem}")

    if audio_value is not None:
        audio_bytes = audio_value.read()
        try:
            with wave.open(io.BytesIO(audio_bytes), 'rb') as f:
                duration = f.getnframes() / float(f.getframerate())
        except: duration = 0

        if duration > 30.5:
            st.error(f"❌ Audio is {int(duration)}s. MAX LIMIT IS 30 SECONDS! Please re-record a shorter version.")
        else:
            st.markdown(f'<div style="color:#10b981; font-size:0.85rem; font-weight:600; text-align:center; margin-bottom: 0.5rem;">✓ Duration: {duration:.1f}s (Acceptable)</div>', unsafe_allow_html=True)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("☁️ UPLOAD TO DRIVE", key=f"upload_btn_{txt_stem}", use_container_width=True):
                    final_name = f"{txt_stem}.wav"
                    try:
                        with st.spinner(f"Uploading {final_name}..."):
                            drive_upload_audio(service, audio_bytes, final_name, audios_folder_id, "audio/wav")
                            get_text_files.clear()
                            get_audio_files.clear()
                        st.success("✅ Saved!")
                        nxt = next((i for i, tf in enumerate(text_files) if tf["name"] not in done_set and i != idx), None)
                        if nxt is not None: st.session_state.rec_nav_index = nxt
                        time.sleep(1.0)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Upload failed: {str(e)}")
            with col2:
                if st.button("▶ Next Text", key=f"skip_next_{txt_stem}", use_container_width=True, disabled=(idx == total - 1)):
                    st.session_state.rec_nav_index = idx + 1
                    st.rerun()

    # ── Text Display
    with st.spinner("Loading text..."):
        text_content = drive_read_text_file(service, cur_txt["id"])

    st.markdown(f'<div class="arabic-text">{text_content}</div>', unsafe_allow_html=True)

    # ── Sidebar
    with st.sidebar:
        st.markdown("**[ TEXTS ]**")
        for i, tf in enumerate(text_files):
            stem = Path(tf["name"]).stem
            if tf["name"] in done_set and i == idx:
                st.markdown(f'<span class="badge done">✓ NOW</span> `{stem}`', unsafe_allow_html=True)
            elif tf["name"] in done_set:
                st.markdown(f'<span class="badge done">✓</span> `{stem}`', unsafe_allow_html=True)
            elif i == idx:
                st.markdown(f'<span class="badge now">NOW</span> `{stem}`', unsafe_allow_html=True)
            else:
                st.markdown(f'<span class="pending">○</span> `{stem}`', unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# ADMIN HELPERS — review status stored as JSON in Drive (audio never deleted)
# ═════════════════════════════════════════════════════════════════════════════
REVIEW_FILENAME = "_review_status.json"

def admin_load_review(service, audios_folder_id):
    """Load the review JSON from Drive. Returns dict {stem: 'approved'|'rejected'}."""
    q = f"'{audios_folder_id}' in parents and name='{REVIEW_FILENAME}' and trashed=false"
    res = service.files().list(q=q, fields="files(id)").execute()
    files = res.get("files", [])
    if not files:
        return {}
    fid = files[0]["id"]
    request = service.files().get_media(fileId=fid)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    try:
        return json.loads(buf.getvalue().decode("utf-8"))
    except Exception:
        return {}

def admin_save_review(service, audios_folder_id, review_dict):
    """Save/overwrite the review JSON file in Drive."""
    data = json.dumps(review_dict, indent=2).encode("utf-8")
    q = f"'{audios_folder_id}' in parents and name='{REVIEW_FILENAME}' and trashed=false"
    res = service.files().list(q=q, fields="files(id)").execute()
    files = res.get("files", [])
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype="application/json", resumable=False)
    if files:
        service.files().update(fileId=files[0]["id"], media_body=media).execute()
    else:
        meta = {"name": REVIEW_FILENAME, "parents": [audios_folder_id]}
        service.files().create(body=meta, media_body=media, fields="id").execute()

def admin_get_audio_bytes(service, file_id):
    """Stream audio bytes from Drive for playback."""
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    downloader = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buf.getvalue()

# ═════════════════════════════════════════════════════════════════════════════
# ADMIN CSS
# ═════════════════════════════════════════════════════════════════════════════
st.markdown("""
<style>
.admin-recorder-card {
    background: #ffffff;
    border: 1px solid rgba(0,0,0,0.07);
    border-radius: 14px;
    padding: 1.2rem 1.5rem;
    margin: 0.5rem 0;
    box-shadow: 0 2px 12px rgba(0,0,0,0.04);
    transition: all 0.25s ease;
    cursor: pointer;
}
.admin-recorder-card:hover {
    border-color: rgba(184,134,11,0.45);
    box-shadow: 0 6px 20px rgba(184,134,11,0.08);
    transform: translateY(-2px);
}
.admin-audio-row {
    background: #fafaf8;
    border: 1px solid rgba(0,0,0,0.06);
    border-radius: 10px;
    padding: 1rem 1.2rem;
    margin: 0.4rem 0;
}
.review-approved { color: #059669; font-weight: 700; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.1em; }
.review-rejected { color: #dc2626; font-weight: 700; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.1em; }
.review-pending  { color: #9ca3af; font-weight: 600; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.1em; }
.admin-back-btn { margin-bottom: 1rem; }
</style>
""", unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# ADMIN — RECORDER DETAIL VIEW
# ═════════════════════════════════════════════════════════════════════════════
def show_admin_recorder_detail(uid):
    """Full detail view for one recorder: all audios, playback, approve/reject."""
    service = get_drive_service()
    user = USERS[uid]

    # ── back button
    if st.button("← Back to Dashboard", key="admin_back"):
        st.session_state.admin_selected = None
        get_audio_files.clear()
        st.rerun()

    st.markdown(f'<div class="title-main" style="font-size:2rem;">{user["name"]}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="subtitle">Audio Review Panel — {uid}</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── fetch Drive data
    with st.spinner("Loading recorder data from Drive..."):
        _, user_folder_id, texts_folder_id, audios_folder_id = get_folder_ids(user["folder"])
        texts  = get_text_files(texts_folder_id)
        audios = get_audio_files(audios_folder_id)
        # filter out the review JSON itself
        audios = [a for a in audios if a["name"] != REVIEW_FILENAME]
        review = admin_load_review(service, audios_folder_id)

    total   = len(texts)
    done    = len(audios)
    pct     = int(done / total * 100) if total else 0
    ap_cnt  = sum(1 for v in review.values() if v == "approved")
    rj_cnt  = sum(1 for v in review.values() if v == "rejected")
    pnd_cnt = done - ap_cnt - rj_cnt

    # ── stats row
    c1, c2, c3, c4, c5 = st.columns(5)
    for col, num, lbl in [
        (c1, total, "Total Texts"),
        (c2, done,  "Uploaded"),
        (c3, ap_cnt,"Approved"),
        (c4, rj_cnt,"Rejected"),
        (c5, pnd_cnt,"Pending Review"),
    ]:
        with col:
            st.markdown(f'<div class="stat-box"><div class="stat-num">{num}</div><div class="stat-label">{lbl}</div></div>', unsafe_allow_html=True)

    st.progress(pct / 100)
    st.markdown("<br>", unsafe_allow_html=True)

    if not audios:
        st.info("No audio files uploaded yet by this recorder.")
        return

    st.markdown("**[ AUDIO FILES — Listen & Review ]**")
    st.markdown("---")

    # ── per-audio rows
    for af in sorted(audios, key=lambda x: x["name"]):
        stem   = Path(af["name"]).stem
        status = review.get(stem, "pending")

        with st.container():
            st.markdown(f'<div class="admin-audio-row">', unsafe_allow_html=True)
            col_name, col_status, col_audio, col_approve, col_reject = st.columns([1.5, 1, 3, 1, 1])

            with col_name:
                st.markdown(f"**`{af['name']}`**")

            with col_status:
                if status == "approved":
                    st.markdown('<span class="review-approved">✓ Approved</span>', unsafe_allow_html=True)
                elif status == "rejected":
                    st.markdown('<span class="review-rejected">✗ Rejected</span>', unsafe_allow_html=True)
                else:
                    st.markdown('<span class="review-pending">⏳ Pending</span>', unsafe_allow_html=True)

            with col_audio:
                try:
                    audio_bytes = admin_get_audio_bytes(service, af["id"])
                    st.audio(audio_bytes, key=f"play_{uid}_{stem}")
                except Exception as e:
                    st.warning(f"Cannot load audio: {e}")

            with col_approve:
                if st.button("✅ Approve", key=f"approve_{uid}_{stem}",
                             use_container_width=True,
                             disabled=(status == "approved")):
                    review[stem] = "approved"
                    admin_save_review(service, audios_folder_id, review)
                    get_audio_files.clear()
                    st.rerun()

            with col_reject:
                if st.button("❌ Reject & Delete", key=f"reject_{uid}_{stem}",
                             use_container_width=True,
                             disabled=(status == "rejected")):
                    # Delete audio file from Drive permanently
                    try:
                        drive_delete_file(service, af["id"])
                    except Exception:
                        pass
                    # Remove from review JSON (file is gone)
                    review.pop(stem, None)
                    admin_save_review(service, audios_folder_id, review)
                    get_audio_files.clear()
                    st.rerun()

            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    # ── bulk actions
    col_ap_all, col_rj_all, col_reset = st.columns(3)
    with col_ap_all:
        if st.button("✅ Approve ALL", key=f"approve_all_{uid}", use_container_width=True):
            for af in audios:
                review[Path(af["name"]).stem] = "approved"
            admin_save_review(service, audios_folder_id, review)
            st.rerun()
    with col_rj_all:
        if st.button("❌ Reject ALL & Delete", key=f"reject_all_{uid}", use_container_width=True):
            for af in audios:
                try:
                    drive_delete_file(service, af["id"])
                except Exception:
                    pass
            # Clear review JSON entries for deleted files
            admin_save_review(service, audios_folder_id, {})
            get_audio_files.clear()
            st.rerun()
    with col_reset:
        if st.button("↺ Reset ALL to Pending", key=f"reset_all_{uid}", use_container_width=True):
            review = {}
            admin_save_review(service, audios_folder_id, review)
            st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# ADMIN — OVERVIEW DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════
def show_admin():
    # ── session state for which recorder is selected
    if "admin_selected" not in st.session_state:
        st.session_state.admin_selected = None

    # ── if a recorder is selected, show its detail view
    if st.session_state.admin_selected:
        show_admin_recorder_detail(st.session_state.admin_selected)
        return

    # ── header
    service = get_drive_service()
    c_title, c_logout = st.columns([5, 1])
    with c_title:
        st.markdown('<div class="title-main">Admin Dashboard</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Lisan ud Dawat — Full Control Panel</div>', unsafe_allow_html=True)
    with c_logout:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Logout", key="admin_logout"):
            st.session_state.logged_in = False
            st.session_state.user_id = None
            st.session_state.admin_selected = None
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── gather all recorder stats
    total_done = 0
    total_texts = 0
    rows = []

    with st.spinner("Loading all recorder data..."):
        for uid, user in USERS.items():
            if user.get("is_admin") or not user.get("folder"):
                continue
            try:
                _, _, texts_folder_id, audios_folder_id = get_folder_ids(user["folder"])
                texts  = get_text_files(texts_folder_id)
                audios = [a for a in get_audio_files(audios_folder_id) if a["name"] != REVIEW_FILENAME]
                t = len(texts)
                done_stems = {Path(af["name"]).stem for af in audios}
                d = len([tf for tf in texts if Path(tf["name"]).stem in done_stems])
                total_done  += d
                total_texts += t

                # quick review counts
                review = admin_load_review(service, audios_folder_id)
                ap  = sum(1 for v in review.values() if v == "approved")
                rj  = sum(1 for v in review.values() if v == "rejected")
                rows.append((user["name"], uid, d, t, ap, rj))
            except Exception:
                rows.append((user["name"], uid, 0, "?", 0, 0))

    pct_all = int(total_done / total_texts * 100) if total_texts else 0

    # ── global stats
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.markdown(f'<div class="stat-box"><div class="stat-num">15</div><div class="stat-label">Total Recorders</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="stat-box"><div class="stat-num">{total_done}</div><div class="stat-label">Total Uploaded</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="stat-box"><div class="stat-num">{total_texts}</div><div class="stat-label">Total Texts</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="stat-box"><div class="stat-num">{pct_all}%</div><div class="stat-label">Overall Progress</div></div>', unsafe_allow_html=True)
    st.progress(pct_all / 100)
    st.markdown("<br>**[ ALL RECORDERS — Click any card to review their audios ]**")
    st.markdown("---")

    # ── recorder cards (2 per row)
    recorder_list = rows
    for i in range(0, len(recorder_list), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if i + j >= len(recorder_list):
                break
            name, uid, d, t, ap, rj = recorder_list[i + j]
            pct = int(d / t * 100) if isinstance(t, int) and t else 0
            pnd = d - ap - rj

            with col:
                badge_color = "done" if pct == 100 else "now"
                st.markdown(f"""
<div class="admin-recorder-card">
  <div style="display:flex; justify-content:space-between; align-items:center;">
    <span style="font-weight:700; font-size:1rem;">{name}</span>
    <span class="badge {badge_color}">{pct}%</span>
  </div>
  <div style="font-size:0.8rem; color:#6b7280; margin: 0.4rem 0;">
    Uploaded: <strong>{d}/{t}</strong> &nbsp;|&nbsp;
    ✅ {ap} &nbsp; ❌ {rj} &nbsp; ⏳ {pnd}
  </div>
</div>
""", unsafe_allow_html=True)
                if st.button(f"🔍 Review {name}", key=f"sel_{uid}", use_container_width=True):
                    st.session_state.admin_selected = uid
                    st.rerun()

# ═════════════════════════════════════════════════════════════════════════════
# ROUTER
# ═════════════════════════════════════════════════════════════════════════════
if not st.session_state.logged_in:
    show_login()
else:
    uid = st.session_state.user_id
    if USERS[uid].get("is_admin"):
        show_admin()
    else:
        show_recorder()