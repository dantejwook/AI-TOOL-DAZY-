# AI DAZY testmode
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
from hdbscan import HDBSCAN


# ============================
# 🔧 Recursive Split Settings
# ============================
MAX_FILES_PER_CLUSTER = 25
MAX_RECURSION_DEPTH = 2

# ============================
# 🔐 Token Store (Server Memory)
# ============================
TOKEN_STORE = {}
TOKEN_EXPIRE_HOURS = 3

# ----------------------------
# 🌈 기본 페이지 설정
# ----------------------------
st.set_page_config(
    page_title="AI dazy test mode",
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

# 토큰 있으면 인증된 것으로 간주
if token:
    st.session_state.authenticated = True

# 비인증 상태 → 비밀번호 입력
if not st.session_state.authenticated:
    st.markdown("<br><br><br><br>", unsafe_allow_html=True)
    col = st.columns([1, 2, 1])[1]

    with col:
        st.markdown(
            """
            <div style="
                background:var(--secondary-background-color);
                padding:2rem;
                border-radius:16px;
                text-align:center;
                color:var(--text-color);">
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
            openai.Model.list()  # 유효성 검사

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

# ============================
# 🎨 스타일
# ============================
st.markdown(
"""
<style>

/* =========================
   앱 기본 배경
========================= */
body {
    background-color: var(--background-color);
    font-family: 'Pretendard', sans-serif;
}

/* =========================
   버튼 스타일
========================= */
.stButton>button {
    border-radius: 10px;
    background-color: var(--primary-color);
    color: var(--text-color);

    /* 밝은 배경에서 가독성 확보 */
    text-shadow: 0 1px 1px rgba(0,0,0,0.15);
    
    border: none;
    padding: 0.6em 1.2em;
    font-weight: 600;

    /* 버튼 전용 그림자 */
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.18);

    transition:
        transform 0.15s ease,
        box-shadow 0.15s ease,
        filter 0.15s ease;
}

.stButton>button:hover {
    transform: translateY(-1px);
    box-shadow: 0 6px 14px rgba(0, 0, 0, 0.22);
    filter: brightness(0.97);
}

.stButton>button:active {
    transform: translateY(0);
    box-shadow: 0 3px 6px rgba(0, 0, 0, 0.25);
}

/* =========================
   상태바
========================= */
.status-bar {
    background-color: var(--secondary-background-color);
    color: var(--text-color);
    border-radius: 6px;
    padding: 0.5em;
    margin-top: 10px;
    font-size: 0.9em;

    /* 버튼처럼 보이게 하는 요소 제거 */
    box-shadow: none;
    border: none;
}

/* =========================
   로그 박스 (카드 유지)
========================= */
.log-box {
    background-color: #dbede6;
    color: #050505;
    padding: 0.8em;
    margin-top: 10px;
    height: 120px;
    overflow-y: auto;
    font-size: 0.85em;

    /* 반응형 */
    border-radius: 12px;

    /* ❌ border 제거 */
    border: none;

    /* ✅ Streamlit 대응 윤곽 */
    outline-offset: -1px;
    box-shadow: none;
}

/* =========================
   테마 미세 조정(상태바 제외)
========================= */
@media (prefers-color-scheme: dark) {
    .log-box {
        outline: 1.5px solid rgba(255, 255, 255, 0.16);
    }
}

@media (prefers-color-scheme: light) {
    .log-box {
        outline: 1.5px solid rgba(0, 0, 0, 0.28);
    }
}

</style>
""",
unsafe_allow_html=True,
)

# ============================
# 사이드바 설정 부분
# ============================

# ----------------------------
# 캐시
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
    output_dir = Path("output_docs")
    zip_path = Path("result_documents.zip")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    if zip_path.exists():
        zip_path.unlink()

st.sidebar.markdown(
    """

"""
)

# ============================
#  사이드바 UI
# ============================

# ----------------------------
# ✅ API Session Active (Sidebar)
# ----------------------------
openai.api_key = st.session_state.api_key

with st.sidebar:
    st.success("API 인증 성공")

# ----------------------------
# 🔒 Logout Button
# ----------------------------
st.sidebar.title("⚙️ Setting")
col1, col2 = st.sidebar.columns([1, 1], gap="small")

with col1:
    if st.button("API Key 변경", use_container_width=True):
        st.session_state.pop("api_key", None)
        st.rerun()

with col2:
    if st.button("로그아웃", use_container_width=True):
    # 인증 상태 제거
        st.session_state.pop("authenticated", None)
        st.session_state.pop("api_key", None)

    # URL 토큰 제거
        st.experimental_set_query_params()

    # 전체 리셋
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

# ============================
# 📁 메인 UI
# ============================
left_col, right_col = st.columns([1, 1])

st.subheader("AI auto file analyzer")
st.caption("문서를 분석하고 자동으로 구조화합니다")

with left_col:
    st.subheader("File upload")
    uploaded_files = st.file_uploader(
        "📁문서를 업로드하세요 (.md, .pdf, .txt)",
        accept_multiple_files=True,
        type=["md", "pdf", "txt"],
        key=f"uploader_{st.session_state.uploader_key}",
    )
    if st.button("Upload File Reset", use_container_width=True):
        st.session_state.uploader_key += 1
        st.rerun()
    # ✅ 반드시 여기 안에서
    col2, col3 = st.columns([1, 1], gap="small")

    with col2:
        if st.button("Cache Reset", use_container_width=True):
            reset_cache()
            st.rerun()
            
    with col3:
        if st.button("Download Reset", use_container_width=True):
            reset_output()
            st.rerun()


with right_col:
    st.subheader("ZIP Download")
    st.caption("📁 문서 정리 후 다운로드 버튼이 활성화 됩니다.")

    zip_placeholder = st.empty()   # 👈 위에 두고


# ============================
# ⚙️ 상태 / 로그
# ============================
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

def h(t: str):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# =====================================================
# ✨ 유틸
# =====================================================

def sanitize_folder_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^\w가-힣\s\[\]]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_") or "기타_문서"


def title_from_filename(file_name: str) -> str:
    base = file_name.rsplit(".", 1)[0]
    base = re.sub(r"[_\-]+", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def build_readme_header(folder_path: str) -> str:
    return f"""<!--
README_소속_폴더: {folder_path}
-->
"""


def readme_filename(folder_name: str, is_gap_report=False) -> str:
    if is_gap_report:
        return f"★README_{folder_name}_보강_리포트.md"
    return f"★README_{folder_name}.md"


# =====================================================
# 🧠 GPT EXPAND (카테고리 기준 의미 분석)
# =====================================================

def expand_document_with_gpt(file, category_readme_text):
    key = h(file.name + category_readme_text)
    if key in expand_cache:
        return expand_cache[key]

    fallback = title_from_filename(file.name)

    prompt = f"""
너는 블로그 콘텐츠 분류를 위한 의미 분석기다.

[블로그 카테고리 및 세부 주제 기준]
{category_readme_text}

[분석 대상 블로그 초안]
파일명: {file.name}

출력(JSON 하나만):
{{
  "canonical_title": "...",
  "parent_category": "대분류 카테고리명",
  "sub_topic": "세부 주제명",
  "relation_reason": "주제와의 연관성",
  "synergy": "같이 묶일 때의 시너지",
  "goal_alignment": "공통 목표 방향성",
  "embedding_text": "..."
}}
"""

    try:
        r = openai.ChatCompletion.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "너는 블로그 콘텐츠 분석기다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        data = json.loads(r["choices"][0]["message"]["content"])
    except Exception:
        data = {
            "canonical_title": fallback,
            "parent_category": "기타",
            "sub_topic": "기타",
            "relation_reason": "",
            "synergy": "",
            "goal_alignment": "",
            "embedding_text": fallback,
        }

    expand_cache[key] = data
    save_cache(EXPAND_CACHE, expand_cache)
    return data


def expand_documents_parallel(files, category_readme_text, max_workers=5):
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(expand_document_with_gpt, f, category_readme_text): f
            for f in files
        }
        for future in as_completed(futures):
            f = futures[future]
            results[f] = future.result()
    return results


# =====================================================
# 📄 README 생성
# =====================================================

def generate_topic_readme(category_title, topic, metas, folder_path):
    header = build_readme_header(folder_path)
    titles = [m["canonical_title"] for m in metas]

    prompt = f"""
카테고리 '{category_title}'의 세부 주제 '{topic}'에 속한 글들이다.

README를 작성하라.

반드시 포함:
- 주제 설명
- 각 글과의 연관성
- 글들 간 시너지
- 공통 목표 방향성

글 목록:
{chr(10).join(titles)}
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 한국어로 README를 작성한다."},
            {"role": "user", "content": prompt},
        ],
    )

    return header + "\n" + r["choices"][0]["message"]["content"].strip()


# =====================================================
# 📄 카테고리 → 기대 주제 추출
# =====================================================

def extract_expected_topics(category_readme_text):
    prompt = f"""
다음 문서에서 대분류와 세부 주제를 구조적으로 추출하라.
JSON만 출력하라.

형식:
{{ "대분류": ["세부주제1", "세부주제2"] }}

문서:
{category_readme_text}
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 문서 구조 분석기다."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )

    return json.loads(r["choices"][0]["message"]["content"])


def collect_actual_topics(expanded_docs):
    result = {}
    for meta in expanded_docs.values():
        result.setdefault(meta["parent_category"], set()).add(meta["sub_topic"])
    return {k: sorted(v) for k, v in result.items()}


def find_missing_topics(expected, actual):
    gaps = {}
    for parent, exp in expected.items():
        act = set(actual.get(parent, []))
        missing = [t for t in exp if t not in act]
        if missing:
            gaps[parent] = {
                "expected": exp,
                "actual": list(act),
                "missing": missing,
            }
    return gaps


def generate_gap_report_readme(category_title, gap_report, folder_path):
    header = build_readme_header(folder_path)

    prompt = f"""
블로그 카테고리 '{category_title}'의 콘텐츠 보강 리포트를 작성하라.

포함:
1. 현재 구성 요약
2. 부족한 세부 주제
3. 왜 중요한지
4. 보강 전략

데이터:
{json.dumps(gap_report, ensure_ascii=False, indent=2)}
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 블로그 전략 컨설턴트다."},
            {"role": "user", "content": prompt},
        ],
    )

    return header + "\n" + r["choices"][0]["message"]["content"].strip()


# =====================================================
# 📁 전체 구조 생성 (엔트리 포인트)
# =====================================================

def build_structure(base_dir, category_title, category_readme_text, files):
    expanded = expand_documents_parallel(files, category_readme_text)

    root_name = f"폴더_{sanitize_folder_name(category_title)}"
    root_dir = os.path.join(base_dir, root_name)
    os.makedirs(root_dir, exist_ok=True)

    grouped = {}
    for file, meta in expanded.items():
        grouped.setdefault(
            (meta["parent_category"], meta["sub_topic"]),
            []
        ).append((file, meta))

    # 🔹 주제 폴더 + README
    for (parent, topic), items in grouped.items():
        parent_name = f"하위폴더_{sanitize_folder_name(parent)}"
        topic_name = f"주제_{sanitize_folder_name(topic)}"

        parent_dir = os.path.join(root_dir, parent_name)
        topic_dir = os.path.join(parent_dir, topic_name)
        os.makedirs(topic_dir, exist_ok=True)

        metas = []
        for file, meta in items:
            os.rename(file.path, os.path.join(topic_dir, file.name))
            metas.append(meta)

        folder_path = f"{root_name} / {parent_name} / {topic_name}"
        readme = generate_topic_readme(
            category_title,
            topic,
            metas,
            folder_path
        )

        with open(
            os.path.join(topic_dir, readme_filename(topic_name)),
            "w",
            encoding="utf-8"
        ) as f:
            f.write(readme)

    # 🔹 최상위 README
    top_header = build_readme_header(root_name)
    with open(
        os.path.join(root_dir, readme_filename(root_name)),
        "w",
        encoding="utf-8"
    ) as f:
        f.write(top_header + f"\n# {category_title}\n")

    # 🔹 보강 리포트
    expected = extract_expected_topics(category_readme_text)
    actual = collect_actual_topics(expanded)
    gaps = find_missing_topics(expected, actual)

    if gaps:
        gap_readme = generate_gap_report_readme(
            category_title,
            gaps,
            root_name
        )
        with open(
            os.path.join(
                root_dir,
                readme_filename(root_name, is_gap_report=True)
            ),
            "w",
            encoding="utf-8"
        ) as f:
            f.write(gap_readme)


#------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------

# ----------------------------
# 🚀 메인 처리 (카테고리 기준 버전)
# ----------------------------
if uploaded_files:
    uploaded_files = [f for f in uploaded_files if f and f.name.strip()]
    if not uploaded_files:
        st.stop()

    reset_output()

    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    progress = progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)

    log("[파일 업로드 완료]")

    # 🔹 카테고리 README / 초안 분리
    category_file = None
    draft_files = []

    for f in uploaded_files:
        if "README" in f.name:
            category_file = f
        else:
            draft_files.append(f)

    if not category_file or not draft_files:
        st.error("카테고리 README 1개와 블로그 초안 파일들이 필요합니다.")
        st.stop()

    category_text = category_file.getvalue().decode("utf-8")

    # 🔹 임시 파일 객체 생성 (기존 코드 호환)
    class TempFile:
        def __init__(self, f):
            self.name = f.name
            self.path = output_dir / f.name
            self._data = f.getvalue()
            self.path.write_bytes(self._data)

    temp_files = [TempFile(f) for f in draft_files]

    total = len(temp_files)
    done = 0
    pct = 30

    progress.progress(pct)
    progress_text.markdown(
        f"<div class='status-bar'>| 카테고리 분석중… | [ {pct}%  ({done} / {total} file) ]</div>",
        unsafe_allow_html=True
    )

    # ✅ 추가: 실제 진행률 콜백 (이것만 추가됨)
    def progress_cb(done, total, phase):
        pct = int(done / total * 100) if total else 100
        progress.progress(pct)
        progress_text.markdown(
            f"<div class='status-bar'>| {phase} | [ {pct}%  ({done} / {total} file) ]</div>",
            unsafe_allow_html=True
        )

        build_structure(
            base_dir=output_dir,
            category_title=category_file.name.rsplit(".", 1)[0],
            category_readme_text=category_text,
            files=temp_files,
            progress_cb=progress_cb,   # ✅ 추가
        )

    done = total
    pct = 80
    progress.progress(pct)
    progress_text.markdown(
        f"<div class='status-bar'>| 정리 중… | [ {pct}%  ({done} / {total} file) ]</div>",
        unsafe_allow_html=True
    )

    # 🔹 ZIP 생성
    zip_path = Path("result_documents.zip")
    with zipfile.ZipFile(zip_path, "w") as z:
        for root, _, files in os.walk(output_dir):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, arcname=os.path.relpath(p, output_dir))

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
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)
    log_box.markdown("<div class='log-box'>......</div>", unsafe_allow_html=True)
