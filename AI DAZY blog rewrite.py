# AI DAZY v2512190245_1.1

import streamlit as st
import zipfile
import os
import openai
import json
import hashlib
import re
import shutil
import secrets
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

# ============================
# 🔧 기존 설정값 (유지)
# ============================
MAX_FILES_PER_CLUSTER = 25
MAX_RECURSION_DEPTH = 2

# ============================
# 🔐 Token Store (Server Memory)
# ============================
TOKEN_STORE = {}
TOKEN_EXPIRE_HOURS = 3

# ----------------------------
# 🌈 기본 페이지 설정 (유지)
# ----------------------------
st.set_page_config(
    page_title="AI dazy Blog Rewriter",
    page_icon="🗂️",
    layout="wide",
)

# ============================
# 🔒 Password + Token Gate
# ============================
APP_PASSWORD = st.secrets.get("APP_PASSWORD") or os.getenv("APP_PASSWORD")

params = st.experimental_get_query_params()
token = params.get("auth", [None])[0]

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if token:
    st.session_state.authenticated = True

if not st.session_state.authenticated:
    st.markdown("<br><br><br><br>", unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]

    with col:
        st.markdown(
            """
            <div style="
                background:#444;
                padding:2rem;
                border-radius:16px;
                text-align:center;
                color:white;">
                <h2>🔒 Access Password</h2>
                <p>이 앱은 제한된 사용자만 접근할 수 있습니다.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        pw = st.text_input("Password", type="password", label_visibility="collapsed")

        if pw:
            if pw == APP_PASSWORD:
                new_token = secrets.token_hex(16)
                st.experimental_set_query_params(auth=new_token)
                st.session_state.authenticated = True
                st.success("접근 허용")
                st.rerun()
            else:
                st.error("비밀번호가 올바르지 않습니다.")

    st.stop()

# ============================
# 🔑 API Key Input (First Time)
# ============================
if "api_key" not in st.session_state:
    st.markdown("### 🔑 OpenAI API Key")

    api_key_input = st.text_input(
        "OpenAI API Key",
        type="password",
        placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx",
        label_visibility="collapsed",
    )
    st.caption("1️⃣ 해당앱은 chat gpt / openai를 사용합니다. ")
    st.caption("2️⃣ openai 에서 발급한 api key 를 사용해주세요.")
    st.caption("3️⃣ api key 발급 받기 : [ https://openai.com/ko-KR/api/ ]")

    if api_key_input:
        try:
            openai.api_key = api_key_input
            openai.Model.list()

            TOKEN_STORE[token] = {
                "api_key": api_key_input,
                "expires_at": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
            }

            st.session_state.api_key = api_key_input
            st.success("API Key 인증 완료")
            st.rerun()
        except Exception:
            st.error("❌ 유효하지 않은 API Key입니다.")

    st.stop()

# ============================
# 📁 File Uploader State (초기 1회)
# ============================
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# ----------------------------
# 🎨 스타일 (유지)
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
        background-color: #0e1117; border-radius: 6px;
        padding: 0.5em; margin-top: 10px; font-size: 0.9em;
    }
    .log-box {
        background-color: #262A32; border-radius: 6px;
        padding: 0.8em; margin-top: 10px;
        height: 120px; overflow-y: auto; font-size: 0.85em;
        border: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------
# 🧭 사이드바 (유지)
# ----------------------------
openai.api_key = st.session_state.api_key

with st.sidebar:
    st.success("API 인증 성공")

st.sidebar.title("⚙️ Setting")
col1, col2 = st.sidebar.columns([1, 1], gap="small")

with col1:
    if st.button("API Key 변경", use_container_width=True):
        st.session_state.pop("api_key", None)
        st.rerun()

with col2:
    if st.button("로그아웃", use_container_width=True):
        st.session_state.pop("authenticated", None)
        st.session_state.pop("api_key", None)
        st.experimental_set_query_params()
        st.rerun()

st.sidebar.markdown("### 💡 사용 팁")
st.sidebar.markdown(
    """
- 📁 파일을 **업로드하면 자동으로 시작** 됩니다.
- 📂 **여러 문서를 한 번에 업로드**할 수 있습니다.
- 🧠 문서는 **AI가 하나의 블로그 글로 병합**합니다.
- ✍️ SEO 제목 / 메타 / 본문을 자동 생성합니다.
- ⏳ 문서 수가 많을수록 처리 시간이 늘어납니다.
- 📦 완료 후 **ZIP 파일로 한 번에 다운로드**할 수 있습니다.
"""
)

# ----------------------------
# 📁 메인 UI (유지)
# ----------------------------
left_col, right_col = st.columns([1, 1])

st.subheader("AI auto file analyzer")
st.caption("문서를 분석하고 자동으로 구조화합니다")

with left_col:
    st.subheader("File upload")
    uploaded_files = st.file_uploader(
        "📁문서를 업로드하세요 (.md, .pdf, .txt)",
        accept_multiple_files=True,
        type=["md", "txt"],
        key=f"uploader_{st.session_state.uploader_key}",
    )
    if st.button("Upload File Reset", use_container_width=True):
        st.session_state.uploader_key += 1
        st.rerun()

    col2, col3 = st.columns([1, 1], gap="small")

    with col2:
        if st.button("Cache Reset", use_container_width=True):
            st.rerun()

    with col3:
        if st.button("Download Reset", use_container_width=True):
            if Path("output_docs").exists():
                shutil.rmtree("output_docs")
            if Path("result_documents.zip").exists():
                os.remove("result_documents.zip")
            st.rerun()

with right_col:
    st.subheader("ZIP Download")
    st.caption("📁 문서 정리 후 다운로드 버튼이 활성화 됩니다.")
    zip_placeholder = st.empty()

# ----------------------------
# ⚙️ 상태 / 로그 (유지)
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
# 🧠 블로그 리라이터 로직 (교체)
# ----------------------------
def merge_and_rewrite(files):
    drafts = ""
    for f in files:
        drafts += f"\n\n---\n\n{f.getvalue().decode('utf-8')}"

    prompt = f"""
당신은 전문 테크 라이터이자 SEO 전문가입니다.

아래 여러 개의 블로그 초안을 하나의 글로 병합하고
SEO 최적화된 한국어 블로그 글을 작성하세요.

요구사항:
- H1 1개
- H2/H3 구조
- 도입부 문제 정의 + 해결 약속
- 결론에 핵심 요약 + CTA
- 1,200~1,800자
- 마크다운
"""

    r = openai.ChatCompletion.create(
        model="gpt-4-mini",
        messages=[{"role": "user", "content": prompt + drafts}],
        temperature=0.4,
    )
    return r["choices"][0]["message"]["content"]

# ----------------------------
# 🚀 메인 처리 (유지)
# ----------------------------
if uploaded_files:
    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    progress = progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)
    log("파일 업로드 완료")

    blog_md = merge_and_rewrite(uploaded_files)
    progress.progress(80)
    log("블로그 병합 및 리라이트 완료")

    (output_dir / "blog_post.md").write_text(blog_md, encoding="utf-8")

    zip_path = Path("result_documents.zip")
    with zipfile.ZipFile(zip_path, "w") as z:
        z.write(output_dir / "blog_post.md", "blog_post.md")

    zip_placeholder.download_button(
        "[ Download ]",
        open(zip_path, "rb"),
        file_name="result_documents.zip",
        mime="application/zip",
        use_container_width=True,
        key="zip_download",
    )

    progress.progress(100)
    progress_text.markdown("<div class='status-bar'>[100% complete]</div>", unsafe_allow_html=True)
    log("모든 문서 정리 완료")

else:
    progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[대기 중]</div>", unsafe_allow_html=True)
    log_box.markdown("<div class='log-box'>대기 중...</div>", unsafe_allow_html=True)
