# AI DAZY v2512190245_1.1 (BLOG REWRITER MODE)

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
# 🔐 Token Store (Server Memory)
# ============================
TOKEN_STORE = {}
TOKEN_EXPIRE_HOURS = 3

# ----------------------------
# 🌈 기본 페이지 설정 (유지)
# ----------------------------
st.set_page_config(
    page_title="AI dazy document sorter",
    page_icon="🗂️",
    layout="wide",
)

# ============================
# 🔒 Password + Token Gate (유지)
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
# 🔑 API Key Input (유지)
# ============================
if "api_key" not in st.session_state:
    st.markdown("### 🔑 OpenAI API Key")

    api_key_input = st.text_input(
        "OpenAI API Key",
        type="password",
        placeholder="sk-xxxxxxxxxxxxxxxxxxxxxxxx",
        label_visibility="collapsed",
    )

    if api_key_input:
        try:
            openai.api_key = api_key_input
            openai.Model.list()
            st.session_state.api_key = api_key_input
            st.success("API Key 인증 완료")
            st.rerun()
        except Exception:
            st.error("❌ 유효하지 않은 API Key입니다.")

    st.stop()

openai.api_key = st.session_state.api_key

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
    .status-bar {
        background-color: #0e1117; border-radius: 6px;
        padding: 0.5em; margin-top: 10px; font-size: 0.9em;
    }
    .log-box {
        background-color: #262A32; border-radius: 6px;
        padding: 0.8em; margin-top: 10px;
        height: 120px; overflow-y: auto; font-size: 0.85em;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------
# 🧭 사이드바 (유지)
# ----------------------------
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
            st.session_state.clear()
            st.experimental_set_query_params()
            st.rerun()

    st.sidebar.markdown("### 💡 사용 팁")
    st.sidebar.markdown(
        """
- 📁 여러 블로그 초안을 업로드하세요
- 🧠 AI가 하나의 글로 병합합니다
- ✍️ SEO 제목/메타/본문 자동 생성
- 📦 ZIP으로 다운로드
"""
    )

# ----------------------------
# 📁 메인 UI (유지)
# ----------------------------
left_col, right_col = st.columns([1, 1])

st.subheader("AI auto file analyzer")
st.caption("블로그 초안을 하나의 SEO 글로 리라이트합니다")

with left_col:
    st.subheader("File upload")
    uploaded_files = st.file_uploader(
        "📁블로그 초안 업로드 (.md, .txt)",
        accept_multiple_files=True,
        type=["md", "txt"],
    )

with right_col:
    st.subheader("ZIP Download")
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
# 🧠 GPT FUNCTIONS (리라이터 전용)
# ----------------------------
def merge_drafts(drafts, keyword):
    prompt = f"""
당신은 전문 테크 블로그 에디터입니다.
아래 여러 블로그 초안을 하나의 글로 통합하기 위한 편집용 정리본을 만드세요.

요구사항:
- 최종 글 작성 금지
- 설명 금지
- 반드시 JSON 하나만 출력

출력 형식:
{{
  "core_topic": "...",
  "search_intent": "...",
  "key_points": ["...", "..."],
  "recommended_structure": ["도입", "본문", "결론"],
  "merged_notes": "..."
}}

키워드: {keyword}

초안:
{drafts}
"""
    r = openai.ChatCompletion.create(
        model="gpt-5-nano",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return json.loads(r["choices"][0]["message"]["content"])

def generate_titles(keyword, count):
    prompt = f"""
당신은 SEO 최적화 블로그 전략가입니다.
요구사항:
- 결과 수: {count}
- JSON 배열만 출력
- title, meta_description, tags 포함
- 제목 45~60자
- 메타 설명 120~155자
- 키워드: '{keyword}'
"""
    r = openai.ChatCompletion.create(
        model="gpt-5-nano",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return json.loads(r["choices"][0]["message"]["content"])

def generate_blog(merged, keyword, title, meta):
    prompt = f"""
당신은 전문 테크 라이터이자 SEO 전문가입니다.

요구사항:
- H1 1개
- H2/H3 구조
- 1,200~1,800자
- 마크다운
- 결론에 CTA 포함

키워드: {keyword}
제목: {title}
메타 설명: {meta}

정리본:
{json.dumps(merged, ensure_ascii=False)}
"""
    r = openai.ChatCompletion.create(
        model="gpt-5-nano",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.45,
    )
    return r["choices"][0]["message"]["content"]

# ----------------------------
# 🚀 메인 실행
# ----------------------------
if uploaded_files:
    keyword = st.text_input("SEO 키워드 입력")

    if keyword:
        progress = progress_placeholder.progress(0)
        progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)

        drafts = ""
        for f in uploaded_files:
            drafts += f"\n\n---\n\n{f.getvalue().decode('utf-8')}"

        log("초안 병합 중...")
        merged = merge_drafts(drafts, keyword)
        progress.progress(30)

        log("SEO 제목 생성 중...")
        titles = generate_titles(keyword, 5)
        progress.progress(60)

        chosen = titles[0]
        log("본문 작성 중...")
        blog_md = generate_blog(merged, keyword, chosen["title"], chosen["meta_description"])
        progress.progress(90)

        output_dir = Path("output_docs")
        output_dir.mkdir(exist_ok=True)

        (output_dir / "blog_post.md").write_text(blog_md, encoding="utf-8")
        (output_dir / "seo_titles.json").write_text(
            json.dumps(titles, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        zip_path = Path("result_documents.zip")
        with zipfile.ZipFile(zip_path, "w") as z:
            for f in output_dir.iterdir():
                z.write(f, f.name)

        zip_placeholder.download_button(
            "[ Download ]",
            open(zip_path, "rb"),
            file_name="blog_result.zip",
            mime="application/zip",
            use_container_width=True,
        )

        progress.progress(100)
        progress_text.markdown("<div class='status-bar'>[100% complete]</div>", unsafe_allow_html=True)
        log("✅ 블로그 생성 완료")

else:
    progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[대기 중]</div>", unsafe_allow_html=True)
    log_box.markdown("<div class='log-box'>대기 중...</div>", unsafe_allow_html=True)
