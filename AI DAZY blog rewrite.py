# AI DAZY v2512190305_2.0
# SEO Blog Generator with Title+Meta JSON & Markdown Body

import streamlit as st
import zipfile
import os
import openai
import json
import hashlib
import re
import shutil
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from hdbscan import HDBSCAN

# ============================
# 🔧 Recursive Settings
# ============================
MAX_FILES_PER_CLUSTER = 25
MAX_RECURSION_DEPTH = 2

# ============================
# 🔐 Token Store
# ============================
TOKEN_STORE = {}
TOKEN_EXPIRE_HOURS = 3

# ----------------------------
# 🌈 Page Config
# ----------------------------
st.set_page_config(
    page_title="AI DAZY SEO Blog Generator",
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
            <div style="background:#444;padding:2rem;border-radius:16px;
                        text-align:center;color:white;">
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
# 🔑 API Key Input
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

openai.api_key = st.session_state.api_key

# ============================
# 📁 File Uploader State
# ============================
if "uploader_key" not in st.session_state:
    st.session_state.uploader_key = 0

# ============================
# 🧠 Cache
# ============================
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

def load_cache(p):
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except Exception:
        return {}

def save_cache(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

TITLE_META_CACHE = CACHE_DIR / "title_meta.json"
ARTICLE_CACHE = CACHE_DIR / "articles.json"

title_meta_cache = load_cache(TITLE_META_CACHE)
article_cache = load_cache(ARTICLE_CACHE)

def h(t: str):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

# ============================
# ✨ Utils
# ============================
def sanitize_filename(name: str) -> str:
    name = re.sub(r"[^\w가-힣\s]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_")[:80]

# ============================
# 🧠 Title + Meta Generator
# ============================
def generate_title_meta(keyword: str, count: int = 3):
    key = h(keyword)
    if key in title_meta_cache:
        return title_meta_cache[key]

    prompt = f"""
당신은 SEO 최적화 블로그 전략가입니다. 사용자 키워드에 대해 검색 의도와 카테고리를 고려하여 클릭을 유도하는 한국어 제목과 메타 설명을 작성하세요.
요구사항:
- 결과 수: {count}
- 각 결과는 JSON 객체 형식으로 출력하세요. 필드: title(문자열), meta_description(문자열), tags(문자열 배열)
- 제목은 45~60자 내외, 메타 설명은 120~155자 내외
- 키워드: '{keyword}'
- 상업적/정보/내비게이션 의도 중 적절히 혼합
- 중복 없이 다양하게
출력은 반드시 JSON 배열 형식만으로 제공하세요.
"""

    r = openai.ChatCompletion.create(
        model="gpt-5-nano",
        messages=[
            {"role": "system", "content": "너는 SEO 전문가다."},
            {"role": "user", "content": prompt},
        ],
    )

    data = json.loads(r["choices"][0]["message"]["content"])
    title_meta_cache[key] = data
    save_cache(TITLE_META_CACHE, title_meta_cache)
    return data

# ============================
# ✍️ Blog Body Generator
# ============================
def generate_blog_body(keyword, title, meta_description, tags):
    key = h(keyword + title)
    if key in article_cache:
        return article_cache[key]

    prompt = f"""
당신은 전문 테크 라이터이자 SEO 전문가입니다. 아래 초안을 바탕으로 한국어 블로그 본문을 마크다운으로 작성하세요.
요구사항:
- H1은 제목 1개만, H2/H3로 체계적으로 구성
- 도입부에서 독자 문제 정의와 해결 약속
- 핵심 섹션에 사례/목록/표를 적절히 활용
- 결론에 핵심 요약, 행동 유도(CTA) 포함
- 자연스러운 키워드 배치, 과도한 반복 금지
- 길이: 1,200~1,800자 내외
- 코드나 표가 있다면 마크다운 서식을 준수
입력 초안:
- 키워드: {keyword}
- 제목: {title}
- 메타 설명: {meta_description}
- 태그: {', '.join(tags)}
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 전문 블로그 작가다."},
            {"role": "user", "content": prompt},
        ],
    )

    content = r["choices"][0]["message"]["content"].strip()
    article_cache[key] = content
    save_cache(ARTICLE_CACHE, article_cache)
    return content

# ============================
# 📁 UI
# ============================
st.subheader("AI DAZY SEO Blog Generator")
st.caption("키워드 기반 제목·메타·본문을 자동 생성합니다")

keyword = st.text_input("🔑 핵심 키워드 입력", placeholder="예: 소자본 피부미용 창업")

zip_placeholder = st.empty()

# ============================
# 🚀 Process
# ============================
if keyword:
    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    title_meta_list = generate_title_meta(keyword, count=3)

    # 대표 제목 = 첫 번째
    main = title_meta_list[0]

    body = generate_blog_body(
        keyword=keyword,
        title=main["title"],
        meta_description=main["meta_description"],
        tags=main["tags"],
    )

    safe = sanitize_filename(main["title"])

    # 본문 저장
    (output_dir / f"{safe}.md").write_text(body, encoding="utf-8")

    # 제목/메타 후보 JSON 저장
    (output_dir / f"{safe}_TITLE_META_CANDIDATES.json").write_text(
        json.dumps(title_meta_list, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    zip_path = "seo_blog_result.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for f in output_dir.glob("*"):
            z.write(f, f.name)

    zip_placeholder.download_button(
        "📦 결과 다운로드",
        open(zip_path, "rb"),
        file_name="seo_blog_result.zip",
        mime="application/zip",
        use_container_width=True,
    )
