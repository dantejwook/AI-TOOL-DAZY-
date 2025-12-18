# AI DAZY BLOG REWRITER v251219

import streamlit as st
import zipfile
import os
import openai
import json
import shutil
import secrets
from datetime import datetime, timedelta
from pathlib import Path

# ============================
# 🔐 Token Store
# ============================
TOKEN_STORE = {}
TOKEN_EXPIRE_HOURS = 3

# ============================
# 🌈 Page Config
# ============================
st.set_page_config(
    page_title="AI dazy blog rewriter",
    page_icon="✍️",
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
            <div style="background:#444;padding:2rem;border-radius:16px;
                        text-align:center;color:white;">
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
                st.rerun()
            else:
                st.error("비밀번호 오류")

    st.stop()

# ============================
# 🔑 OpenAI API Key
# ============================
if "api_key" not in st.session_state:
    st.markdown("### 🔑 OpenAI API Key")
    api_key_input = st.text_input("OpenAI API Key", type="password", label_visibility="collapsed")

    if api_key_input:
        try:
            openai.api_key = api_key_input
            openai.Model.list()
            st.session_state.api_key = api_key_input
            st.success("API Key 인증 완료")
            st.rerun()
        except Exception:
            st.error("❌ 유효하지 않은 API Key")

    st.stop()

openai.api_key = st.session_state.api_key

# ============================
# 🎨 Style
# ============================
st.markdown(
    """
    <style>
    .log-box {background:#262A32;border-radius:6px;padding:0.8em;
              height:140px;overflow-y:auto;font-size:0.85em;}
    </style>
    """,
    unsafe_allow_html=True,
)

# ============================
# 📁 Output Reset
# ============================
def reset_output():
    if Path("output_blog").exists():
        shutil.rmtree("output_blog")
    if Path("result_blog.zip").exists():
        os.remove("result_blog.zip")

# ============================
# 🧭 Sidebar
# ============================
with st.sidebar:
    st.success("API 인증 성공")
    if st.button("로그아웃"):
        st.session_state.clear()
        st.experimental_set_query_params()
        st.rerun()

    st.markdown("### 💡 사용 방법")
    st.markdown("""
- 여러 블로그 초안을 업로드
- 하나의 SEO 글로 병합
- 제목/메타 자동 생성
- ZIP 다운로드
""")

# ============================
# 🧠 GPT FUNCTIONS
# ============================
def merge_drafts(drafts, keyword):
    prompt = f"""
당신은 전문 테크 블로그 에디터입니다.
아래 여러 개의 블로그 초안을 하나의 글로 통합하기 위한
편집용 정리본을 작성하세요.

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

SEO 키워드: {keyword}

초안:
{drafts}
"""

    r = openai.ChatCompletion.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "JSON만 출력"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )

    return json.loads(r["choices"][0]["message"]["content"])


def generate_titles(keyword, count):
    prompt = f"""
당신은 SEO 최적화 블로그 전략가입니다.

요구사항:
- 결과 수: {count}
- JSON 배열만 출력
- 필드: title, meta_description, tags
- 제목 45~60자
- 메타 설명 120~155자
- 키워드: "{keyword}"
"""

    r = openai.ChatCompletion.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "JSON 배열만 출력"},
            {"role": "user", "content": prompt},
        ],
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

입력:
키워드: {keyword}
제목: {title}
메타 설명: {meta}

정리본:
{json.dumps(merged, ensure_ascii=False)}
"""

    r = openai.ChatCompletion.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "마크다운 블로그 작성"},
            {"role": "user", "content": prompt},
        ],
        temperature=0.45,
    )

    return r["choices"][0]["message"]["content"]

# ============================
# 📁 Main UI
# ============================
st.subheader("✍️ AI Blog Draft Merger")

keyword = st.text_input("SEO 키워드")
title_count = st.slider("제목 후보 수", 3, 10, 5)

uploaded_files = st.file_uploader(
    "블로그 초안 업로드 (.txt, .md)",
    type=["txt", "md"],
    accept_multiple_files=True,
)

logs = []
log_box = st.empty()

def log(msg):
    logs.append(msg)
    log_box.markdown(
        "<div class='log-box'>" + "<br>".join(logs[-10:]) + "</div>",
        unsafe_allow_html=True,
    )

if uploaded_files and keyword:
    if st.button("🚀 블로그 생성 시작"):
        reset_output()
        os.makedirs("output_blog", exist_ok=True)

        drafts_text = ""
        for f in uploaded_files:
            drafts_text += f"\n\n---\n\n{f.getvalue().decode('utf-8')}"

        log("초안 병합 중...")
        merged = merge_drafts(drafts_text, keyword)

        log("SEO 제목 생성 중...")
        seo_variants = generate_titles(keyword, title_count)

        chosen = seo_variants[0]

        log("본문 작성 중...")
        blog_md = generate_blog(
            merged,
            keyword,
            chosen["title"],
            chosen["meta_description"],
        )

        Path("output_blog/blog_post.md").write_text(blog_md, encoding="utf-8")
        Path("output_blog/seo_variants.json").write_text(
            json.dumps(seo_variants, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        with zipfile.ZipFile("result_blog.zip", "w") as z:
            for f in Path("output_blog").iterdir():
                z.write(f, f.name)

        log("✅ 완료")

        st.download_button(
            "📦 ZIP 다운로드",
            open("result_blog.zip", "rb"),
            file_name="blog_result.zip",
            mime="application/zip",
        )

else:
    log_box.markdown("<div class='log-box'>대기 중...</div>", unsafe_allow_html=True)
