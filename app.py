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
    "recorder_01": {"name": "Recorder 01", "password_hash": hashlib.sha256("lisan@1".encode()).hexdigest(), "folder": "recorder_01"},
    "recorder_02": {"name": "Recorder 02", "password_hash": hashlib.sha256("lisan@2".encode()).hexdigest(), "folder": "recorder_02"},
    "recorder_03": {"name": "Recorder 03", "password_hash": hashlib.sha256("lisan@3".encode()).hexdigest(), "folder": "recorder_03"},
    "recorder_04": {"name": "Recorder 04", "password_hash": hashlib.sha256("lisan@4".encode()).hexdigest(), "folder": "recorder_04"},
    "recorder_05": {"name": "Recorder 05", "password_hash": hashlib.sha256("lisan@5".encode()).hexdigest(), "folder": "recorder_05"},
    "recorder_06": {"name": "Recorder 06", "password_hash": hashlib.sha256("lisan@6".encode()).hexdigest(), "folder": "recorder_06"},
    "recorder_07": {"name": "Recorder 07", "password_hash": hashlib.sha256("lisan@7".encode()).hexdigest(), "folder": "recorder_07"},
    "recorder_08": {"name": "Recorder 08", "password_hash": hashlib.sha256("lisan@8".encode()).hexdigest(), "folder": "recorder_08"},
    "recorder_09": {"name": "Recorder 09", "password_hash": hashlib.sha256("lisan@9".encode()).hexdigest(), "folder": "recorder_09"},
    "recorder_10": {"name": "Recorder 10", "password_hash": hashlib.sha256("lisan@10".encode()).hexdigest(), "folder": "recorder_10"},
    "recorder_11": {"name": "Recorder 11", "password_hash": hashlib.sha256("lisan@11".encode()).hexdigest(), "folder": "recorder_11"},
    "recorder_12": {"name": "Recorder 12", "password_hash": hashlib.sha256("lisan@12".encode()).hexdigest(), "folder": "recorder_12"},
    "recorder_13": {"name": "Recorder 13", "password_hash": hashlib.sha256("lisan@13".encode()).hexdigest(), "folder": "recorder_13"},
    "recorder_14": {"name": "Recorder 14", "password_hash": hashlib.sha256("lisan@14".encode()).hexdigest(), "folder": "recorder_14"},
    "recorder_15": {"name": "Recorder 15", "password_hash": hashlib.sha256("lisan@15".encode()).hexdigest(), "folder": "recorder_15"},
    "admin":        {"name": "Admin",       "password_hash": hashlib.sha256("admin@lisan".encode()).hexdigest(), "folder": None, "is_admin": True},
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
    res = service.files().list(q=q, fields="files(id,name)", orderBy="name").execute()
    return res.get("files", [])

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
    """Upload audio bytes to a specific Drive folder."""
    media = MediaIoBaseUpload(io.BytesIO(audio_bytes), mimetype=mime_type, resumable=False)
    meta = {"name": filename, "parents": [folder_id]}
    file = service.files().create(body=meta, media_body=media, fields="id,name").execute()
    return file



# ─────────────────────────────────────────────────────────────────────────────
# FOLDER ID CACHE  (so we don't re-query Drive on every rerun)
# ─────────────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=300)
def get_folder_ids(user_folder_name):
    """Return (root_id, user_id, texts_id, audios_id) for a recorder."""
    service = get_drive_service()
    root_id    = drive_get_or_create_folder(service, ROOT_FOLDER_NAME)
    user_id_f  = drive_get_or_create_folder(service, user_folder_name, root_id)
    texts_id   = drive_get_or_create_folder(service, "texts",  user_id_f)
    audios_id  = drive_get_or_create_folder(service, "audios", user_id_f)
    return root_id, user_id_f, texts_id, audios_id

@st.cache_data(ttl=60)
def get_text_files(texts_folder_id):
    service = get_drive_service()
    return drive_list_files(service, texts_folder_id, ".txt")

@st.cache_data(ttl=60)
def get_audio_files(audios_folder_id):
    service = get_drive_service()
    # empty string for extension grabs all files
    return drive_list_files(service, audios_folder_id, "")

# ─────────────────────────────────────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────────────────────────────────────
def check_login(username, password):
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
    font-size: 2.2rem !important;
    line-height: 2.0 !important; 
    color: #111827 !important; /* Very dark slate for high readability */
    direction: rtl !important; 
    text-align: center !important;
    background: #ffffff; 
    border: 1px solid rgba(0,0,0,0.05);
    box-shadow: 0 10px 30px rgba(0,0,0,0.06);
    padding: 2.5rem;
    border-radius: 16px; 
    margin: 1.0rem 0;
    position: relative;
    /* Removed max-height so text appears fully without a scroll box */
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

    # ── header
    c1, c2 = st.columns([5, 1])
    with c1:
        st.markdown('<div class="title-main">لسان الدعوت</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="subtitle">Session — {user["name"]}</div>', unsafe_allow_html=True)
    with c2:
        if st.button("Logout"):
            for k in ["logged_in","user_id","recorded_audio","recorded_name","current_txt_index"]:
                st.session_state[k] = False if k == "logged_in" else None
            st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    # ── get Drive folder IDs
    with st.spinner("Connecting to Google Drive..."):
        _, user_folder_id, texts_folder_id, audios_folder_id = get_folder_ids(user["folder"])
        text_files = get_text_files(texts_folder_id)
        audio_files = get_audio_files(audios_folder_id)

    if not text_files:
        st.warning("No text files found in your Drive texts folder. Ask admin to upload them.")
        return

    # ── calculate progress directly from Drive folders
    total = len(text_files)
    # Get stems of all uploaded audio files (e.g., "001.wav" -> "001")
    done_stems = {Path(af["name"]).stem for af in audio_files}
    
    # A text is done if its stem exists in the audio folder
    done_set = {tf["name"] for tf in text_files if Path(tf["name"]).stem in done_stems}
    done = len(done_set)
    remaining = total - done

    # ── stats
    c1, c2, c3 = st.columns(3)
    pct = int(done / total * 100) if total else 0
    with c1: st.markdown(f'<div class="stat-box"><div class="stat-num">{done}</div><div class="stat-label">Recorded</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="stat-box"><div class="stat-num">{remaining}</div><div class="stat-label">Remaining</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="stat-box"><div class="stat-num">{pct}%</div><div class="stat-label">Complete</div></div>', unsafe_allow_html=True)
    st.progress(pct / 100)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── find next text
    next_txt = None
    for tf in text_files:
        if tf["name"] not in done_set:
            next_txt = tf
            break

    if next_txt is None:
        st.success("🎉 All recordings complete! Excellent work.")
        st.balloons()
        return

    txt_name  = next_txt["name"]               # e.g. "001.txt"
    txt_stem  = Path(txt_name).stem            # e.g. "001"
    audio_name = f"{txt_stem}.webm"            # e.g. "001.webm"  ← SAME NAME

    # ── instructions
    st.markdown("""
    <div style="font-size:0.75rem; color:#7a7670; line-height:2;">
    ① &nbsp;Press the <strong style="color:#c9a84c;">🎙️ mic button</strong> below to start recording<br>
    ② &nbsp;Press it again to <strong style="color:#c9a84c;">stop</strong> — then listen to your preview<br>
    ③ &nbsp;If good, click <strong style="color:#c9a84c;">☁️ UPLOAD TO DRIVE &amp; NEXT</strong><br>
    ④ &nbsp;If not good, press the mic button again to re-record
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    # ── Native Streamlit audio recorder ABOVE the text
    audio_value = st.audio_input(
        "🎙️ Press to record — press again to stop",
        key=f"audio_input_{txt_stem}"
    )

    if audio_value is not None:
        audio_bytes = audio_value.read()
        
        # ── Check Audio Duration
        try:
            with wave.open(io.BytesIO(audio_bytes), 'rb') as f:
                frames = f.getnframes()
                rate = f.getframerate()
                duration = frames / float(rate)
        except:
            duration = 0
            
        st.markdown("**▶ Preview your recording:**")
        st.audio(audio_bytes)
        
        if duration > 30.5:  # giving 0.5s buffer
            st.error(f"❌ Recording is too long ({int(duration)} seconds). The maximum allowed is 30 seconds.")
            st.warning("Please click the mic button above to re-record a shorter version.")
        else:
            st.markdown(f'<div style="color:#10b981; font-size:0.8rem;">✓ Perfect length: {duration:.1f} seconds</div>', unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                upload_btn = st.button(
                    "☁️ UPLOAD TO DRIVE & NEXT",
                    key=f"upload_btn_{txt_stem}",
                    use_container_width=True
                )
            with col2:
                st.button(
                    "↺ RE-RECORD (press mic again)",
                    key=f"rerecord_hint_{txt_stem}",
                    use_container_width=True,
                    disabled=True
                )

            if upload_btn:
                final_name  = f"{txt_stem}.wav"   # st.audio_input returns wav
                
                try:
                    with st.spinner(f"⏳ Uploading {final_name} to your Google Drive..."):
                        drive_upload_audio(service, audio_bytes, final_name, audios_folder_id, "audio/wav")
                        # Clear caches so we fetch the updated lists from Drive
                        get_text_files.clear()
                        get_audio_files.clear()
                    st.success(f"✅ {final_name} saved to YOUR Google Drive! Loading next text...")
                    import time; time.sleep(1.5)
                    st.rerun()
                except Exception as e:
                    st.error(f"❌ Upload failed: {str(e)}")
                    st.info("Please wait a moment and click upload again.")
    else:
        st.markdown(
            '<div style="color:#7a7670;font-size:0.78rem;margin-top:0.5rem;">'
            '⬆ Press the mic button above to start recording</div>',
            unsafe_allow_html=True
        )

    st.markdown("---")

    # ── read text from Drive and display BELOW recorder
    with st.spinner("Loading text..."):
        text_content = drive_read_text_file(service, next_txt["id"])

    st.markdown(f'**[ TEXT: `{txt_stem}` ]**')
    st.markdown(f'<div class="arabic-text">{text_content}</div>', unsafe_allow_html=True)

    # ── sidebar progress list
    with st.sidebar:
        st.markdown("**[ TEXTS ]**")
        for tf in text_files:
            stem = Path(tf["name"]).stem
            if tf["name"] in done_set:
                st.markdown(f'<span class="badge done">✓</span> `{stem}`', unsafe_allow_html=True)
            elif tf == next_txt:
                st.markdown(f'<span class="badge now">NOW</span> `{stem}`', unsafe_allow_html=True)
            else:
                st.markdown(f'<span class="pending">○</span> `{stem}`', unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
# ADMIN
# ═════════════════════════════════════════════════════════════════════════════
def show_admin():
    service = get_drive_service()
    st.markdown('<div class="title-main">Admin Dashboard</div>', unsafe_allow_html=True)
    st.markdown('<div class="subtitle">Lisan ud Dawat — Collection Progress</div>', unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("→ LOGOUT"):
        st.session_state.logged_in = False
        st.session_state.user_id = None
        st.rerun()

    total_done = 0
    total_texts = 0
    rows = []

    for uid, user in USERS.items():
        if user.get("is_admin") or not user.get("folder"):
            continue
        try:
            _, user_folder_id, texts_folder_id, audios_folder_id = get_folder_ids(user["folder"])
            texts = get_text_files(texts_folder_id)
            audios = get_audio_files(audios_folder_id)
            
            t = len(texts)
            done_stems = {Path(af["name"]).stem for af in audios}
            d = len([tf for tf in texts if Path(tf["name"]).stem in done_stems])
            
            total_done  += d
            total_texts += t
            rows.append((user["name"], uid, d, t))
        except:
            rows.append((user["name"], uid, 0, "?"))

    pct_all = int(total_done / total_texts * 100) if total_texts else 0

    c1, c2, c3 = st.columns(3)
    with c1: st.markdown(f'<div class="stat-box"><div class="stat-num">{total_done}</div><div class="stat-label">Total Recorded</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="stat-box"><div class="stat-num">{total_texts}</div><div class="stat-label">Total Texts</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="stat-box"><div class="stat-num">{pct_all}%</div><div class="stat-label">Overall Done</div></div>', unsafe_allow_html=True)
    st.progress(pct_all / 100)
    st.markdown("<br>**[ PER RECORDER ]**")
    st.markdown("---")

    for name, uid, d, t in rows:
        pct = int(d / t * 100) if isinstance(t, int) and t else 0
        c1, c2, c3, c4 = st.columns([2,1,1,3])
        with c1: st.markdown(f"**{name}**")
        with c2: st.markdown(f"`{d}/{t}`")
        with c3: st.markdown(f'<span class="badge {"done" if pct==100 else "now"}">{pct}%</span>', unsafe_allow_html=True)
        with c4: st.progress(pct / 100)

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