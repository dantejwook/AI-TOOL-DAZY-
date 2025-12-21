# AI DAZY TEST MODE

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
    page_title="AI dazy document sorter",
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

#----------------------------------------------------------------------------------------------------------

# ============================
# ✨ 유틸
# ============================
def sanitize_folder_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^\w가-힣\s]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_") or "기타_문서"

def unique_folder_name(base: str, existing: set) -> str:
    if base not in existing:
        return base
    i = 1
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"

def title_from_filename(file_name: str) -> str:
    base = file_name.rsplit(".", 1)[0]
    base = re.sub(r"[_\-]+", " ", base)
    base = re.sub(r"\s+", " ", base).strip()
    return base

# ----------------------------
# 🧠 0차 GPT EXPAND
# ----------------------------
def expand_document_with_gpt(file):
    key = h(file.name)
    if key in expand_cache:
        return expand_cache[key]

    fallback_title = title_from_filename(file.name)

    prompt = f"""
너는 이미 존재하는
[블로그 카테고리 및 세부 주제가 정리된 README 파일]을
기준 분류 체계로 사용하는 역할이다.

아래 문서는 블로그 초안이다.
이 문서가 README에 정의된
카테고리 또는 세부 주제 중
어디에 속하는지 판단할 수 있도록
의미를 정규화하라.

❗중요 규칙
- 새로운 카테고리나 주제를 만들지 마라
- README에 존재하는 표현 기준으로만 해석하라
- 분류나 그룹핑은 하지 말고 의미 정보만 추출하라
- 요약문 작성 금지

출력은 반드시 JSON 하나만 출력한다.

형식:
{{
  "canonical_title": "카테고리 기준에서 해석한 제목",
  "keywords": ["카테고리_연관_키워드"],
  "domain": "README에 정의된 상위 카테고리명",
  "embedding_text": "카테고리/주제 기준으로 재서술한 문서 의미"
}}

문서 파일명:
{file.name}
"""

    try:
        r = openai.ChatCompletion.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "너는 블로그 카테고리 기준 의미 정규화 엔진이다."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        data = json.loads(r["choices"][0]["message"]["content"])
        if "embedding_text" not in data:
            raise ValueError

    except Exception:
        data = {
            "canonical_title": fallback_title,
            "keywords": fallback_title.split(),
            "domain": "기타",
            "embedding_text": f"제목: {fallback_title}",
        }

    expand_cache[key] = data
    save_cache(EXPAND_CACHE, expand_cache)
    return data

# ----------------------------
# ⭐ 추가: 0차 EXPAND 병렬 처리
# ----------------------------
def expand_documents_parallel(files, max_workers=5):
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(expand_document_with_gpt, f): f for f in files}
        for future in as_completed(futures):
            f = futures[future]
            try:
                results[f] = future.result()
            except Exception:
                fallback_title = title_from_filename(f.name)
                results[f] = {
                    "canonical_title": fallback_title,
                    "keywords": fallback_title.split(),
                    "domain": "기타",
                    "embedding_text": f"제목: {fallback_title}",
                }
    return [results[f] for f in files]

# ----------------------------
# ✨ 임베딩
# ----------------------------
def embed_texts(texts):
    missing = [t for t in texts if h(t) not in embedding_cache]

    if missing:
        r = openai.Embedding.create(
            model="text-embedding-3-large",
            input=missing,
        )
        for t, d in zip(missing, r["data"]):
            embedding_cache[h(t)] = d["embedding"]
        save_cache(EMBED_CACHE, embedding_cache)

    return [embedding_cache[h(t)] for t in texts]

# ----------------------------
# 📦 클러스터링
# ----------------------------
def cluster_documents(files):
    # ⭐ 변경: 0차 EXPAND 병렬 적용
    expanded = expand_documents_parallel(files, max_workers=5)
    vectors = embed_texts([e["embedding_text"] for e in expanded])
    return HDBSCAN(min_cluster_size=3, min_samples=1).fit_predict(vectors)

# ----------------------------
# 🔁 자동 재분해
# ----------------------------
def recursive_cluster(files, depth=0):
    if len(files) <= MAX_FILES_PER_CLUSTER or depth >= MAX_RECURSION_DEPTH:
        return [files]

    labels = cluster_documents(files)
    groups = {}
    for f, l in zip(files, labels):
        groups.setdefault(l, []).append(f)

    result = []
    for g in groups.values():
        if len(g) > MAX_FILES_PER_CLUSTER:
            result.extend(recursive_cluster(g, depth + 1))
        else:
            result.append(g)

    return result

# ----------------------------
# ✨ GPT 폴더명 / README
# ----------------------------
def generate_group_name(names):
    k = h("||".join(sorted(names)))
    if k in group_cache:
        return group_cache[k]

    prompt = f"""
다음 문서들은 이미 생성된 블로그 카테고리 폴더 중
하나에 반드시 속한다.

규칙:
- 새로운 이름을 만들지 마라
- 반드시 아래 폴더명 중 하나만 그대로 선택하라
- 가장 관련성이 높은 하나만 선택하라
- 출력은 폴더명 하나만

선택 가능한 폴더 목록:
{chr(10).join(os.listdir("output_docs"))}

문서 제목:
{chr(10).join(names)}
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 기존 폴더명 중 하나만 선택하는 분류기다."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.1,
    )

    name = sanitize_folder_name(r["choices"][0]["message"]["content"])
    group_cache[k] = name
    save_cache(GROUP_CACHE, group_cache)
    return name
# -
def generate_readme(topic, files, auto_split=False):
    k = h(("split" if auto_split else "nosplit") + topic + "||" + "||".join(sorted(files)))
    if k in readme_cache:
        return readme_cache[k]

    notice = AUTO_SPLIT_NOTICE if auto_split else ""

    prompt = f"""
다음 문서들은
[블로그 카테고리 및 세부 주제가 정리된 README]에 정의된
'{topic}' 주제로 분류된 글들이다.

아래 내용을 반드시 포함하여 README.md를 작성하라.

1. 이 카테고리(주제)의 핵심 목적
2. 각 문서가 주제와 어떤 연관성을 가지는지
3. 함께 묶였을 때의 콘텐츠 시너지
4. 이 묶음이 독자에게 제공하는 공통된 목표와 방향성

규칙:
- README 제목은 반드시 '{topic}'
- 설명형 문단 위주
- 반드시 한국어로 작성


문서 목록:
{chr(10).join(files)}
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 한국어로만 README를 작성한다."},
            {"role": "user", "content": prompt},
        ],
    )

    content = notice + r["choices"][0]["message"]["content"].strip()
    readme_cache[k] = content
    save_cache(README_CACHE, readme_cache)
    return content

# ----------------------------
# 🚀 메인 처리
# ----------------------------
if uploaded_files:
    uploaded_files = [f for f in uploaded_files if f and f.name.strip()]
    if not uploaded_files:
        st.stop()

    # ▶ 실행 시 결과 폴더 자동 초기화
    reset_output()

    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    progress = progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)
    log("[파일 업로드 완료]")

    # ==================================================
    # 📘 카테고리 README 기반 폴더 생성
    # ==================================================

    # 1. 업로드된 파일 중 카테고리 README 선택
    category_readme = next(
        f for f in uploaded_files
        if "README" in f.name
    )

    # 2. README 내용 읽기
    content = category_readme.getvalue().decode("utf-8")
    lines = content.splitlines()

    current_main = None

    for line in lines:
        line = line.strip()

        # 메인 카테고리 (#)
        if line.startswith("# "):
            current_main = sanitize_folder_name(
                line[2:].split("[")[0]
            )
            (output_dir / current_main).mkdir(exist_ok=True)

        # 하위 카테고리 (##)
        elif line.startswith("## ") and current_main:
            sub = sanitize_folder_name(line[3:])
            (output_dir / current_main / sub).mkdir(
                parents=True,
                exist_ok=True
            )

    log("[카테고리 폴더생성 완료]")


    top_clusters = recursive_cluster(uploaded_files)
    total = len(top_clusters)
    done = 0

    for cluster_files in top_clusters:
        main_group = generate_group_name(
        [f.name.rsplit(".", 1)[0] for f in cluster_files]
    )
    main_folder = output_dir / main_group

    # 🚫 README 기반 선생성 구조에서는 mkdir 하면 안 됨
    if not main_folder.exists():
         raise RuntimeError(
            f"[구조 오류] README에 정의되지 않은 폴더: {main_group}"
        )

    readme_filename = f"★README_{main_group}.md"

        (main_folder / readme_filename).write_text(
            generate_readme(main_group, [f.name for f in cluster_files]),
            encoding="utf-8",
        )

        used_names = set()
        for sub_files in recursive_cluster(cluster_files):
            base = generate_group_name([f.name.rsplit(".", 1)[0] for f in sub_files])
            sub_group = unique_folder_name(base, used_names)
            used_names.add(sub_group)

            sub_folder = main_folder / sub_group
            sub_folder.mkdir(parents=True, exist_ok=True)

            # 🔒 README 기반 선생성 폴더 보호
            if main_folder.exists() and not main_folder.is_dir():
               raise RuntimeError(f"[폴더 충돌] {main_folder} 는 파일입니다")

            main_folder.mkdir(parents=True, exist_ok=True)
            
            readme_filename = f"★README_{main_group}.md"

            (sub_folder / readme_filename).write_text(
                generate_readme(f"{main_group} - {sub_group}", [f.name for f in sub_files]),
                encoding="utf-8",
            )

        done += 1
        pct = int(done / total * 100)
        progress.progress(pct)
        progress_text.markdown(
            f"<div class='status-bar'>| 카테고리 정리 중… | [ {pct}%  ({done} / {total} file) ]</div>",
            unsafe_allow_html=True
        )
        log(f"{main_group} 처리 완료")

    zip_path = Path("result_documents.zip")
    with zipfile.ZipFile(zip_path, "w") as z:
        for root, _, files in os.walk(output_dir):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, arcname=os.path.relpath(p, output_dir))
 
    zip_placeholder.download_button(
        "[ Download ]",
        open("result_documents.zip", "rb"),
        file_name="result_documents.zip",
        mime="application/zip",
        use_container_width=True,
        key="zip_download",
    )

    progress.progress(100)
    progress_text.markdown("<div class='status-bar'>[100% complete]</div>", unsafe_allow_html=True)
    log("모든 문서 정리 완료")

#----------------------------------------------------------------------------------------------------------

else:
    progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)
    log_box.markdown("<div class='log-box'>......</div>", unsafe_allow_html=True)
