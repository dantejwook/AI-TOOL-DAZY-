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
    page_icon="📝",
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
            # ❗ 구버전 SDK 호환용: 사전 검증 제거
            st.session_state.api_key = api_key_input
            st.success("API Key 인증 완료")
            st.rerun()
        except Exception:
            st.error("❌ 유효하지 않은 API Key입니다.")

    st.stop()

openai.api_key = st.session_state.api_key

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

    # 🔹 기존 UI 흐름 유지 + 최소 입력
  
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
# 🧩 JSON 안전 파서 (필수)
# ----------------------------
def safe_json_loads(text: str):
    """
    모델이 여러 JSON / 잡문을 섞어 출력해도
    '첫 번째 유효한 JSON'만 정확히 파싱한다.
    """
    if not text:
        raise ValueError("Empty response")

    t = text.strip()

    # ```json ... ``` 코드펜스 제거
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)

    decoder = json.JSONDecoder()

    # 배열이 먼저면 배열 시도
    t_strip = t.lstrip()
    if t_strip.startswith("["):
        obj, _ = decoder.raw_decode(t_strip)
        return obj

    # 객체 시도
    if t_strip.startswith("{"):
        obj, _ = decoder.raw_decode(t_strip)
        return obj

    # 중간에 JSON이 있는 경우를 위해 '{' 또는 '[' 이후부터 재시도
    for idx, ch in enumerate(t):
        if ch in "{[":
            try:
                obj, _ = decoder.raw_decode(t[idx:])
                return obj
            except Exception:
                continue

    raise ValueError("No valid JSON found")

# ==================================================
# 🧠 3-STEP BLOG REWRITE LOGIC (복구 완료)
# ==================================================

# ① 초안 병합 (JSON)
def merge_drafts(drafts_text):
    prompt = f"""
당신은 전문 테크 블로그 에디터입니다.
아래 여러 개의 블로그 초안을 하나의 글로 통합하기 위한
'편집용 정리본'을 작성하세요.

요구사항:
- 최종 글 작성 금지
- 설명 금지
- 반드시 JSON 하나만 출력

출력 형식:
{{
  "core_topic": "...",
  "search_intent": "...",
  "key_points": ["...", "..."],
  "recommended_structure": ["도입", "본문1", "본문2", "결론"],
  "merged_notes": "..."
}}


초안:
{drafts_text}
"""
    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return safe_json_loads(r["choices"][0]["message"]["content"])

# ② SEO 제목 / 메타 (JSON)
def generate_titles_meta(keyword, count=5):
    # keyword가 비어있으면 JSON 출력이 흔들릴 수 있어 최소 방어
    keyword = (keyword or "").strip()
    if not keyword:
        keyword = "기술 블로그"

    prompt = f"""
<제목, 메타 프롬프트>

당신은 SEO 최적화 블로그 전략가입니다. 사용자 키워드에 대해 검색 의도와 카테고리를 고려하여 클릭을 유도하는 한국어 제목과 메타 설명을 작성하세요.
요구사항:
- 결과 수: {count}
- 각 결과는 JSON 객체 형식으로 출력하세요. 필드: title(문자열), meta_description(문자열), tags(문자열 배열)
- 제목은 45~60자 내외, 메타 설명은 120~155자 내외
- 키워드: '{keyword}'
- 상업적/정보/내비게이션 의도 중 적절히 혼합
- 중복 없이 다양하게
출력은 반드시 JSON 배열 형식만으로 제공하세요.

중요:
- 설명/서문/코드펜스/추가 텍스트 절대 금지
- 반드시 '[' 로 시작해서 ']' 로 끝나는 JSON 배열만 출력
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 오직 JSON 배열만 출력한다. 다른 텍스트를 절대 출력하지 않는다."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    raw = r["choices"][0]["message"]["content"]
    try:
        data = safe_json_loads(raw)
        # 최소 검증: 배열이어야 함
        if not isinstance(data, list) or len(data) == 0:
            raise ValueError("Not a non-empty JSON array")
        return data
    except Exception:
        # 로그에 원문 일부만 남기면 디버깅 쉬움 (UI 변경 없이 log 사용)
        log("⚠️ SEO JSON 파싱 실패 → 결과 재시도")
        # 1회 재시도(temperature 낮게)
        r2 = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "JSON 배열만 출력. 다른 글자 출력 금지."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
        )
        raw2 = r2["choices"][0]["message"]["content"]
        data2 = safe_json_loads(raw2)
        if not isinstance(data2, list) or len(data2) == 0:
            raise ValueError("SEO JSON still invalid")
        return data2
        
# ----------------------------
# 🚀 메인 처리 (UI 흐름 유지)
# ----------------------------
if uploaded_files:
    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    progress = progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)
    log("파일 업로드 완료")

    drafts_text = ""
    for f in uploaded_files:
        drafts_text += f"\n\n---\n\n{f.getvalue().decode('utf-8')}"

    # ① 병합
    merged = merge_drafts(drafts_text)
    progress.progress(30)
    log("초안 병합 완료")

    # ② 제목/메타
    keyword = merged.get("core_topic", "")
    seo_list = generate_titles_meta(keyword, 5)
    chosen = seo_list[0]
    progress.progress(60)
    log("SEO 제목/메타 생성 완료")

    # ③ 본문
    blog_md = generate_blog_body(
        merged,
        keyword,
        chosen["title"],
        chosen["meta_description"],
    )
    progress.progress(85)
    log("본문 리라이트 완료")

    (output_dir / "blog_post.md").write_text(blog_md, encoding="utf-8")
    (output_dir / "seo_titles.json").write_text(
        json.dumps(seo_list, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    zip_path = Path("result_documents.zip")
    with zipfile.ZipFile(zip_path, "w") as z:
        for f in output_dir.iterdir():
            z.write(f, f.name)

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
