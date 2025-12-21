# AI DAZY TEST MODE

# 기본 영역 ----------------------------------------------------------------------------------------------------------------------------------------------------

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

# ------------------------------------------
# 🌈 기본 페이지 설정
# ------------------------------------------
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

# ------------------------------------------
# 캐시
# ------------------------------------------
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

# ------------------------------------------
# ✅ API Session Active (Sidebar)
# ------------------------------------------
openai.api_key = st.session_state.api_key

with st.sidebar:
    st.success("API 인증 성공")

# ------------------------------------------
# 🔒 Logout Button
# ------------------------------------------
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
- 🧠 문서는 **AI가 자동으로 주제별 분류**합니다.
- 📁 폴더 수가 많으면 **자동으로 하위 폴더로 분해**됩니다.
- ⏳ 문서 수가 많을수록 처리 시간이 늘어납니다.
- 📦 완료 후 **ZIP 파일로 한 번에 다운로드**할 수 있습니다.
"""
)

# ============================
# 📁 메인 UI
# ============================

left_col, right_col = st.columns([1, 1])

if st.button("🚀 실행", use_container_width=True):
    if not api_key or not readme_file or not content_files:
        st.warning("README 파일, 초안 파일을 모두 업로드하세요.")
    else:
        with st.spinner("AI가 문서를 분석하고 있습니다... 잠시만요!"):
            result_zip = process_documents(readme_file, content_files, api_key)
            st.success("✅ 처리 완료! 아래에서 ZIP을 다운로드하세요.")
            st.download_button("📦 결과 ZIP 다운로드", open(result_zip, "rb"), file_name="AI_Blog_Sorted.zip")

st.subheader("AI auto file analyzer")
st.caption("문서를 분석하고 자동으로 구조화합니다")

with left_col:
    st.subheader("File upload")
    readme_file = st.file_uploader("📘 블로그 카테고리 README 파일 업로드", type=["md"])
    content_files = st.file_uploader("📄 블로그 초안 파일 업로드 (복수 가능)"
    (
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

# 기본 영역 ----------------------------------------------------------------------------------------------------------------------------------------------------

# 기능 영역 ----------------------------------------------------------------------------------------------------------------------------------------------------



# -------------------------------------------
# ✨ 유틸 [경로, 캐시, 파일명, 해시 등 공통 함수]
# -------------------------------------------

def h(text): 
    return sha256(text.encode("utf-8")).hexdigest()

def sanitize_folder_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^\w가-힣\s\-\_]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_") or "기타_문서"

def unique_folder_name(base: str, existing: set) -> str:
    if base not in existing:
        return base
    i = 1
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"

def save_text(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def load_text(file):
    if file.name.endswith(".pdf"):
        import fitz
        text = ""
        with fitz.open(stream=file.read(), filetype="pdf") as doc:
            for page in doc:
                text += page.get_text("text")
        return text
    else:
        return file.read().decode("utf-8", errors="ignore")


# ------------------------------------------
# 📘 카테고리 README 기반 폴더 생성
# ------------------------------------------

def parse_readme_structure(readme_text: str) -> dict:
    structure = {}
    current_main, current_sub = None, None
    for line in readme_text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            current_main = line[2:].strip()
            structure[current_main] = {}
        elif line.startswith("## "):
            current_sub = line[3:].strip()
            structure[current_main][current_sub] = []
        elif line.startswith("### "):
            topic = line[4:].strip()
            structure[current_main].setdefault(current_sub, []).append(topic)
    return structure


# ---------------------------------------------------
# 🧠 0차 GPT EXPAND [각 문서를 의미적으로 정규화하는 단계]
# ---------------------------------------------------

def expand_document_with_gpt(file, api_key):
    openai.api_key = api_key
    content = load_text(file)
    prompt = f"""
    아래 문서는 블로그 초안입니다.
    문서의 핵심 내용을 3~4줄로 요약하고, 의미 기반 벡터화를 위한 요약 텍스트를 만들어주세요.
    출력 형식(JSON):
    {{
      "title": "문서의 대표 제목",
      "summary": "문서의 핵심 요약",
      "embedding_text": "의미 기반 벡터화를 위한 확장 텍스트"
    }}
    """
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "너는 블로그 문서 의미 분석 전문가다."},
                {"role": "user", "content": prompt + "\n\n" + content[:2500]}
            ],
            temperature=0.2,
        )
        data = json.loads(response["choices"][0]["message"]["content"])
        return data
    except Exception as e:
        return {"title": file.name, "summary": "요약 실패", "embedding_text": file.name}


# ---------------------------------------------------
# ⭐ 추가: 0차 EXPAND 병렬 처리[위 단계의 병렬화 버전]
# ---------------------------------------------------

def expand_documents_parallel(files, api_key):
    results = []
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(expand_document_with_gpt, f, api_key) for f in files]
        for future in as_completed(futures):
            results.append(future.result())
    return results


# ------------------------------------------
# ✨ 임베딩 [벡터화]
# ------------------------------------------

def embed_texts(texts, api_key):
    openai.api_key = api_key
    try:
        res = openai.Embedding.create(model="text-embedding-3-large", input=texts)
        return [d["embedding"] for d in res["data"]]
    except Exception as e:
        print("임베딩 실패:", e)
        return [[0.0]*1536 for _ in texts]


# ------------------------------------------
# 📦 클러스터링 [유사 문서 묶기]
# ------------------------------------------

def cluster_documents(embeddings):
    clusterer = HDBSCAN(min_cluster_size=2, min_samples=1)
    return clusterer.fit_predict(embeddings)


# ------------------------------------------
# 🔁 자동 재분해 [대형 클러스터를 다시 세분화]
# ------------------------------------------

def recursive_cluster(files, embeddings, depth=0, max_depth=2):
    if len(files) <= 25 or depth >= max_depth:
        return [files]
    labels = cluster_documents(embeddings)
    groups = {}
    for f, l in zip(files, labels):
        groups.setdefault(l, []).append(f)
    result = []
    for g in groups.values():
        if len(g) > 25:
            sub_embeddings = [embeddings[i] for i, f in enumerate(files) if f in g]
            result.extend(recursive_cluster(g, sub_embeddings, depth+1))
        else:
            result.append(g)
    return result


# ----------------------------------------------------
# ✨ GPT 폴더명 / README [각 그룹 이름 결정 + README 생성]
# ----------------------------------------------------

def generate_group_name(docs, api_key):
    openai.api_key = api_key
    titles = "\n".join([d["title"] for d in docs])
    prompt = f"""
    다음 글 제목 목록을 보고, 이 그룹의 공통 주제명을 1줄로 정리하세요.
    예시: "국내 뷰티업계 트렌드 변화", "정책 및 시장 이슈"
    출력: 공통 주제 한 줄만.
    """
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt + "\n\n" + titles}]
    )
    return sanitize_folder_name(response["choices"][0]["message"]["content"].strip())


def generate_readme(group_name, docs, api_key):
    openai.api_key = api_key
    doc_summaries = "\n".join([f"- {d['title']}: {d['summary']}" for d in docs])
    prompt = f"""
    '{group_name}' 폴더의 README를 작성하세요.
    이 폴더의 글들이 어떤 연관성과 시너지를 가지며, 공통 목표가 무엇인지 3~5문단으로 설명하세요.
    문서 목록:
    {doc_summaries}
    """
    response = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    return response["choices"][0]["message"]["content"]


# ------------------------------------------
# 🚀 메인 처리 [프로그램 진행]
# ------------------------------------------

def process_documents(readme_file, content_files, api_key):
    # 1️⃣ README 구조 파싱
    structure = parse_readme_structure(load_text(readme_file))
    base = Path("output_docs")
    if base.exists(): shutil.rmtree(base)
    base.mkdir(exist_ok=True)
    for cat, subs in structure.items():
        for sub in subs.keys():
            (base / sanitize_folder_name(cat) / sanitize_folder_name(sub)).mkdir(parents=True, exist_ok=True)

    # 2️⃣ 문서 의미 확장 + 임베딩
    expanded = expand_documents_parallel(content_files, api_key)
    embeddings = embed_texts([e["embedding_text"] for e in expanded], api_key)

    # 3️⃣ 클러스터링 및 분류
    labels = cluster_documents(embeddings)
    clusters = {}
    for f, l in zip(expanded, labels):
        clusters.setdefault(l, []).append(f)

    # 4️⃣ 폴더 생성 및 README 작성
    for cluster_id, docs in clusters.items():
        group_name = generate_group_name(docs, api_key)
        group_path = base / group_name
        group_path.mkdir(exist_ok=True)
        readme_text = generate_readme(group_name, docs, api_key)
        save_text(group_path / f"README_{group_name}.md", readme_text)

        for d in docs:
            save_text(group_path / f"{sanitize_folder_name(d['title'])}.txt", d['summary'])

    # 5️⃣ ZIP 파일로 묶기
    zip_path = Path("result.zip")
    with zipfile.ZipFile(zip_path, "w") as z:
        for root, _, files in os.walk(base):
            for f in files:
                path = Path(root) / f
                z.write(path, arcname=path.relative_to(base))
    return zip_path

# 기능 영역 ----------------------------------------------------------------------------------------------------------------------------------------------------

else:
    progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)
    log_box.markdown("<div class='log-box'>......</div>", unsafe_allow_html=True)
