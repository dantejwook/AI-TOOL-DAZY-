import streamlit as st
import zipfile
import os
from pathlib import Path
import openai
from hdbscan import HDBSCAN
import json
import hashlib
import re
import shutil

# ============================
# 🔧 재분해 설정
# ============================
MAX_FILES_PER_CLUSTER = 25
MAX_RECURSION_DEPTH = 2
AUTO_SPLIT_NOTICE = "⚠️ 이 폴더는 파일 수 제한(25개)으로 인해 자동 분해되었습니다.\n\n"

# ----------------------------
# 🌈 기본 페이지 설정
# ----------------------------
st.set_page_config(
    page_title="AI dazy document sorter",
    page_icon="🗂️",
    layout="wide",
)

# ----------------------------
# 🔐 OpenAI API 키 설정
# ----------------------------
openai.api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    st.sidebar.error("🚨 OpenAI API Key가 없습니다.")
    st.stop()
else:
    st.sidebar.success("✅ OpenAI Key 로드 완료")

# ----------------------------
# 🎨 스타일
# ----------------------------
st.markdown(
    """
    <style>
    body { background-color: #f8f9fc; font-family: 'Pretendard', sans-serif; }
    .stButton>button {
        border-radius: 10px; background-color: #4a6cf7; color: white;
        border: none; padding: 0.6em 1.2em; font-weight: 600;
    }
    .stButton>button:hover { background-color: #3451c1; }
    .status-bar {
        background-color: #595656; border-radius: 6px;
        padding: 0.5em; margin-top: 20px; font-size: 0.9em;
    }
    .log-box {
        background-color: #595656; border-radius: 6px;
        padding: 0.8em; margin-top: 10px;
        height: 120px; overflow-y: auto; font-size: 0.85em;
        border: 1px solid #dee2e6;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------
# 🧭 사이드바
# ----------------------------
st.sidebar.title("⚙️ 설정")
lang = st.sidebar.selectbox("🌐 언어 선택", ["한국어", "English"])

# ----------------------------
# 🧠 캐시
# ----------------------------
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

def load_cache(p):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}

def save_cache(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

EMBED_CACHE = CACHE_DIR / "embeddings.json"
GROUP_CACHE = CACHE_DIR / "group_names.json"
README_CACHE = CACHE_DIR / "readmes.json"
EXPAND_CACHE = CACHE_DIR / "expands.json"

embedding_cache = load_cache(EMBED_CACHE)
group_cache = load_cache(GROUP_CACHE)
readme_cache = load_cache(README_CACHE)
expand_cache = load_cache(EXPAND_CACHE)

def reset_cache():
    if CACHE_DIR.exists():
        shutil.rmtree(CACHE_DIR)
    CACHE_DIR.mkdir(exist_ok=True)
    embedding_cache.clear()
    group_cache.clear()
    readme_cache.clear()
    expand_cache.clear()

def reset_output():
    if Path("output_docs").exists():
        shutil.rmtree("output_docs")
    if Path("result_documents.zip").exists():
        Path("result_documents.zip").unlink()

if st.sidebar.button("🧹 캐시 초기화"):
    reset_cache()
    st.sidebar.success("✅ 캐시 초기화 완료")
    st.rerun()

if st.sidebar.button("🗑️ 결과 폴더 초기화"):
    reset_output()
    st.sidebar.success("✅ 결과 폴더 초기화 완료")
    st.rerun()

def h(t: str):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

# ----------------------------
# 📁 메인 UI
# ----------------------------
left_col, right_col = st.columns([1, 1])

# ▶ session_state 초기화
if "uploaded_files_data" not in st.session_state:
    st.session_state["uploaded_files_data"] = []

if "uploader_ver" not in st.session_state:
    st.session_state["uploader_ver"] = 0

with left_col:
    header_col, action_col = st.columns([4, 1])

    with header_col:
        st.subheader("📤 파일 업로드")

    uploaded = st.file_uploader(
        "문서를 업로드하세요 (.md, .pdf, .txt)",
        accept_multiple_files=True,
        type=["md", "pdf", "txt"],
        key=f"uploader_widget_{st.session_state['uploader_ver']}",
    )

    st.session_state["uploaded_files_data"] = uploaded or []

with right_col:
    st.subheader("📦 ZIP 다운로드")
    zip_placeholder = st.empty()

uploaded_files = st.session_state["uploaded_files_data"]

# ----------------------------
# ⚙️ 상태 / 로그
# ----------------------------
progress_placeholder = st.empty()
progress_text = st.empty()
log_box = st.empty()
logs = []

def log(msg):
    logs.append(msg)
    log_box.markdown(
        "<div class='log-box'>" + "<br>".join(logs[-10:]) + "</div>",
        unsafe_allow_html=True,
    )

# ----------------------------
# ✨ 유틸
# ----------------------------
def sanitize_folder_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^\w가-힣\s]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_") or "기타_문서"

def title_from_filename(file_name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", file_name.rsplit(".", 1)[0])).strip()

# ----------------------------
# 🚀 메인 처리 (간단 버전)
# ----------------------------
if uploaded_files:
    reset_output()
    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    log("파일 업로드 완료")

    for f in uploaded_files:
        (output_dir / f.name).write_bytes(f.getvalue())

    with zipfile.ZipFile("result_documents.zip", "w") as z:
        for f in uploaded_files:
            z.write(output_dir / f.name, arcname=f.name)

    zip_placeholder.download_button(
        "📥 정리된 ZIP 파일 다운로드",
        open("result_documents.zip", "rb"),
        file_name="result_documents.zip",
        mime="application/zip",
    )

    log("ZIP 생성 완료")

else:
    log_box.markdown("<div class='log-box'>대기 중...</div>", unsafe_allow_html=True)
