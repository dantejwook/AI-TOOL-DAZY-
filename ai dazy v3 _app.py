import streamlit as st
import zipfile
import os
from pathlib import Path
from openai import OpenAI
from hdbscan import HDBSCAN
import re
import json
import hashlib

# ----------------------------
# 🌈 기본 페이지 설정
# ----------------------------
st.set_page_config(page_title="AI dazy document sorter", page_icon="🗂️", layout="wide")

# ----------------------------
# 🔐 OpenAI API 키 설정
# ----------------------------
api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

if not api_key:
    st.sidebar.error("🚨 OpenAI API Key가 없습니다. secrets.toml 또는 환경변수를 확인하세요.")
    st.stop()
else:
    st.sidebar.success("✅ OpenAI Key 로드 완료")

client = OpenAI(api_key=api_key)

# ----------------------------
# 🎨 스타일 커스터마이징
# ----------------------------
st.markdown(
    """
    <style>
    body {
        background-color: #f8f9fc;
        font-family: 'Pretendard', sans-serif;
    }
    .stButton>button {
        border-radius: 10px;
        background-color: #4a6cf7;
        color: white;
        border: none;
        padding: 0.6em 1.2em;
        font-weight: 600;
        transition: 0.2s;
    }
    .stButton>button:hover {
        background-color: #3451c1;
    }
    .status-bar {
        background-color: #595656;
        border-radius: 6px;
        padding: 0.5em;
        margin-top: 20px;
        font-size: 0.9em;
    }
    .log-box {
        background-color: #595656;
        border-radius: 6px;
        padding: 0.8em;
        margin-top: 10px;
        height: 120px;
        overflow-y: auto;
        font-size: 0.85em;
        border: 1px solid #dee2e6;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------
# 🧭 사이드바 설정
# ----------------------------
st.sidebar.title("⚙️ 설정")
if st.sidebar.button("🔁 다시 시작"):
    st.session_state.clear()
    st.rerun()

lang = st.sidebar.selectbox("🌐 언어 선택", ["한국어", "English"])

# ----------------------------
# 📁 메인 UI 구성
# ----------------------------
left_col, right_col = st.columns([1, 1])

with left_col:
    st.subheader("📤 파일 업로드")
    uploaded_files = st.file_uploader(
        "문서를 업로드하세요 (.md, .pdf, .txt)",
        accept_multiple_files=True,
        type=["md", "pdf", "txt"],
    )

if uploaded_files:
    uploaded_files = [f for f in uploaded_files if f and hasattr(f, "name") and f.name.strip()]
    if not uploaded_files:
        st.error("❗ 유효한 파일이 없습니다.")
        st.stop()

with right_col:
    st.subheader("📦 ZIP 다운로드")
    zip_placeholder = st.empty()

# ----------------------------
# ⚙️ 상태 표시 / 로그
# ----------------------------
status_placeholder = st.empty()
log_box = st.empty()
log_messages = []

def log(msg):
    log_messages.append(msg)
    log_html = "<div class='log-box'>" + "<br>".join(log_messages[-10:]) + "</div>"
    log_box.markdown(log_html, unsafe_allow_html=True)

# ----------------------------
# 🧠 캐시 시스템
# ----------------------------
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

EMBED_CACHE = CACHE_DIR / "embeddings.json"
GROUP_CACHE = CACHE_DIR / "group_names.json"
README_CACHE = CACHE_DIR / "readmes.json"

def load_cache(path):
    return json.loads(path.read_text()) if path.exists() else {}

def save_cache(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2))

embedding_cache = load_cache(EMBED_CACHE)
group_cache = load_cache(GROUP_CACHE)
readme_cache = load_cache(README_CACHE)

def hash_key(text):
    return hashlib.sha256(text.encode()).hexdigest()

# ----------------------------
# ✨ OpenAI + 캐시 적용 함수
# ----------------------------
def embed_titles(titles):
    vectors = []
    to_request = []

    for t in titles:
        key = hash_key(t)
        if key in embedding_cache:
            vectors.append(embedding_cache[key])
        else:
            to_request.append((t, key))

    if to_request:
        response = client.embeddings.create(
            model="text-embedding-3-large",
            input=[t for t, _ in to_request]
        )
        for emb, (_, key) in zip(response.data, to_request):
            embedding_cache[key] = emb.embedding
            vectors.append(emb.embedding)
        save_cache(EMBED_CACHE, embedding_cache)

    return vectors

def generate_group_name(file_names):
    key = hash_key("||".join(sorted(file_names)))
    if key in group_cache:
        return group_cache[key]

    prompt = f"""
    다음 문서 제목들을 보고 공통 주제를 대표하는
    짧고 명확한 한글 폴더명을 하나 생성하세요.

    규칙:
    - 뱀_상자
    - 2~4 단어
    - 설명 없이 이름만 출력

    문서 제목:
    {chr(10).join(file_names)}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You generate concise folder names."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=20,
        temperature=0.2,
    )

    name = re.sub(r"[^a-z0-9_]", "", response.choices[0].message.content.strip())
    group_cache[key] = name or "misc_documents"
    save_cache(GROUP_CACHE, group_cache)
    return group_cache[key]

def generate_readme(topic, file_names):
    key = hash_key(topic + "||".join(sorted(file_names)))
    if key in readme_cache:
        return readme_cache[key]

    prompt = f"""
    다음 문서들은 '{topic}' 그룹으로 분류된 자료입니다.
    각 문서의 시너지 효과를 설명하는 README.md를 작성해 주세요.

    문서 목록:
    {chr(10).join(file_names)}
    """

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    readme_cache[key] = response.choices[0].message.content.strip()
    save_cache(README_CACHE, readme_cache)
    return readme_cache[key]

def cluster_documents(files):
    titles = [f"title: {f.name.split('.')[0]}" for f in files]
    vectors = embed_titles(titles)
    clusterer = HDBSCAN(min_cluster_size=2, metric="euclidean")
    return clusterer.fit_predict(vectors)

# ----------------------------
# 🚀 메인 처리 로직
# ----------------------------
if uploaded_files:
    log("파일 업로드 완료 ✅")
    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True, parents=True)

    labels = cluster_documents(uploaded_files)

    raw_groups = {}
    for file, label in zip(uploaded_files, labels):
        raw_groups.setdefault(label, []).append(file)

    for i, (label, files) in enumerate(raw_groups.items(), start=1):
        names = [f.name.split(".")[0] for f in files]
        group = "unclassified_documents" if label == -1 else generate_group_name(names)

        folder = output_dir / group
        folder.mkdir(exist_ok=True, parents=True)

        for f in files:
            with open(folder / f.name, "wb") as out:
                out.write(f.read())

        readme = generate_readme(group, [f.name for f in files])
        (folder / "README.md").write_text(readme, encoding="utf-8")

        progress = int((i / len(raw_groups)) * 100)
        status_placeholder.markdown(
            f"<div class='status-bar'>[{progress}% processing]</div>",
            unsafe_allow_html=True,
        )
        log(f"문서 그룹 '{group}' 처리 완료 ✅")

    with zipfile.ZipFile("result_documents.zip", "w") as zipf:
        for folder, _, files in os.walk(output_dir):
            for f in files:
                p = os.path.join(folder, f)
                zipf.write(p, arcname=os.path.relpath(p, output_dir))

    with open("result_documents.zip", "rb") as f:
        zip_placeholder.download_button(
            "📥 정리된 ZIP 파일 다운로드",
            f,
            file_name="result_documents.zip",
            mime="application/zip",
        )

    status_placeholder.markdown(
        "<div class='status-bar'>[100% complete – 모든 문서 정리 완료]</div>",
        unsafe_allow_html=True,
    )

else:
    status_placeholder.markdown(
        "<div class='status-bar'>[0% processing (0/0 complete)]</div>",
        unsafe_allow_html=True,
    )
    log_box.markdown("<div class='log-box'>대기 중...</div>", unsafe_allow_html=True)
