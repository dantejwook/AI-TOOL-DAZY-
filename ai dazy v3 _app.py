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
# 🔄 Restore API Session from Token
# ============================
if token and token in TOKEN_STORE:
    record = TOKEN_STORE[token]
    if datetime.utcnow() < record["expires_at"]:
        openai.api_key = record["api_key"]
        st.session_state.api_key = record["api_key"]
    else:
        TOKEN_STORE.pop(token, None)
        st.experimental_set_query_params()
        st.warning("⏰ API 세션이 만료되었습니다. 다시 로그인하세요.")
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
# ✅ API Session Active
# ============================
openai.api_key = st.session_state.api_key

st.success("✅ API 인증성공 ")

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
# 🧭 사이드바
# ----------------------------

# ============================
# 🔒 Logout Button
# ============================
st.sidebar.title("⚙️ Setting")
col1, col2 = st.sidebar.columns([1, 1], gap="small")

with col1:
    if st.button("🔑 API Key 변경", use_container_width=True):
        st.session_state.pop("api_key", None)
        st.rerun()

with col2:
    if st.button("🔒 로그아웃", use_container_width=True):
    # 인증 상태 제거
        st.session_state.pop("authenticated", None)
        st.session_state.pop("api_key", None)

    # URL 토큰 제거
        st.experimental_set_query_params()

    # 전체 리셋
        st.rerun()


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
    output_dir = Path("output_docs")
    zip_path = Path("result_documents.zip")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    if zip_path.exists():
        zip_path.unlink()

st.sidebar.markdown(
    """

- ⚙️ 다시 시작하시려면 
-     "Cache Reset > Download Reset > F5 순서대로 눌러주세요."
"""
)

# ▶ 사이드바 버튼 (캐시, 다운로드 초기화)

col1, col2 = st.sidebar.columns([1, 1], gap="small")

with col1:
    if st.button("🧹 Cache Reset", use_container_width=True):
        reset_cache()
        st.toast("✅ Cache Reset is complete.")
        st.rerun()

with col2:
    if st.button("🗑️ Download Reset", use_container_width=True):
        reset_output()
        st.toast("✅ Download Reset is complete.")
        st.rerun()

def h(t: str):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


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

# ----------------------------
# 📁 메인 UI
# ----------------------------
left_col, right_col = st.columns([1, 1])

st.subheader("AI auto file analyzer")
st.caption("문서를 분석하고 자동으로 구조화합니다")

with left_col:
    st.subheader("File upload")
    uploaded_files = st.file_uploader(
        "📁문서를 업로드하세요 (.md, .pdf, .txt)",
        accept_multiple_files=True,
        type=["md", "pdf", "txt"],
    )

with right_col:
    st.subheader("ZIP Download")
    st.caption("📁 문서 정리 후 다운로드 버튼이 활성화 됩니다.")

    st.markdown(
        '<div class="download-box">',
        unsafe_allow_html=True,
    )

    zip_placeholder = st.empty()

    st.markdown(
        '</div>',
        unsafe_allow_html=True,
    )

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
다음 문서를 분류하기 쉽게 의미적으로 정규화하라.
분류나 그룹핑은 하지 말고, 의미만 추출하라.

출력은 반드시 JSON 하나만 출력한다.

형식:
{{
  "canonical_title": "...",
  "keywords": ["...", "..."],
  "domain": "...",
  "embedding_text": "..."
}}

문서 파일명:
{file.name}
"""

    try:
        r = openai.ChatCompletion.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "너는 문서를 분류하기 쉽게 정규화하는 역할이다."},
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

    prompt = """
다음 문서 제목들의 공통 주제를 대표하는
짧고 명확한 한글 폴더명 하나만 출력하세요.

규칙:
- 2~4 단어
- 조사 사용 금지
- 숫자/번호 금지
- 설명 금지
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 한글 폴더명만 생성한다."},
            {"role": "user", "content": prompt + "\n" + "\n".join(names)},
        ],
        temperature=0.3,
    )

    name = sanitize_folder_name(r["choices"][0]["message"]["content"])
    group_cache[k] = name
    save_cache(GROUP_CACHE, group_cache)
    return name

def generate_readme(topic, files, auto_split=False):
    k = h(("split" if auto_split else "nosplit") + topic + "||" + "||".join(sorted(files)))
    if k in readme_cache:
        return readme_cache[k]

    notice = AUTO_SPLIT_NOTICE if auto_split else ""

    prompt = f"""
{notice}다음 문서들은 '{topic}' 주제로 분류된 자료입니다.
각 문서의 관계와 활용 목적을 설명하는 README.md를 작성하세요.
반드시 한국어로 작성하세요.

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
    log("파일 업로드 완료")

    top_clusters = recursive_cluster(uploaded_files)
    total = len(top_clusters)
    done = 0

    for cluster_files in top_clusters:
        main_group = generate_group_name([f.name.rsplit(".", 1)[0] for f in cluster_files])
        main_folder = output_dir / main_group
        main_folder.mkdir(parents=True, exist_ok=True)

        (main_folder / "★README.md").write_text(
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

            for f in sub_files:
                (sub_folder / f.name).write_bytes(f.getvalue())

            (sub_folder / "★README.md").write_text(
                generate_readme(f"{main_group} - {sub_group}", [f.name for f in sub_files]),
                encoding="utf-8",
            )

        done += 1
        pct = int(done / total * 100)
        progress.progress(pct)
        progress_text.markdown(
            f"<div class='status-bar'>정리 중… [{pct}%] ({done} / {total} 파일)</div>",
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

else:
    progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[대기 중]</div>", unsafe_allow_html=True)
    log_box.markdown("<div class='log-box'>대기 중...</div>", unsafe_allow_html=True)
