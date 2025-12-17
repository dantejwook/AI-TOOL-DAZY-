import streamlit as st
import zipfile
import os
from pathlib import Path
import openai
from hdbscan import HDBSCAN
import json
import hashlib
import re

# ----------------------------
# 🌈 기본 페이지 설정
# ----------------------------
st.set_page_config(page_title="AI dazy document sorter", page_icon="🗂️", layout="wide")

# ----------------------------
# 🔐 OpenAI API 키 설정 (legacy 방식)
# ----------------------------
openai.api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    st.sidebar.error("🚨 OpenAI API Key가 없습니다. secrets.toml 또는 환경변수를 확인하세요.")
    st.stop()
else:
    st.sidebar.success("✅ OpenAI Key 로드 완료")

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
    uploaded_files = [f for f in uploaded_files if f and f.name.strip()]
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
    log_box.markdown(
        "<div class='log-box'>" + "<br>".join(log_messages[-10:]) + "</div>",
        unsafe_allow_html=True,
    )

# ----------------------------
# 🧠 캐시
# ----------------------------
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

EMBED_CACHE = CACHE_DIR / "embeddings.json"
GROUP_CACHE = CACHE_DIR / "group_names.json"
README_CACHE = CACHE_DIR / "readmes.json"

def load_cache(p):
    return json.loads(p.read_text()) if p.exists() else {}

def save_cache(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2))

embedding_cache = load_cache(EMBED_CACHE)
group_cache = load_cache(GROUP_CACHE)
readme_cache = load_cache(README_CACHE)

def h(text):
    return hashlib.sha256(text.encode()).hexdigest()

# ----------------------------
# ✨ OpenAI 함수 (legacy + 캐시)
# ----------------------------
def embed_titles(titles):
    vectors = []
    to_call = []

    for t in titles:
        k = h(t)
        if k in embedding_cache:
            vectors.append(embedding_cache[k])
        else:
            to_call.append((t, k))

    if to_call:
        resp = openai.Embedding.create(
            model="text-embedding-3-large",
            input=[t for t, _ in to_call],
        )
        for d, (_, k) in zip(resp["data"], to_call):
            embedding_cache[k] = d["embedding"]
            vectors.append(d["embedding"])
        save_cache(EMBED_CACHE, embedding_cache)

    return vectors

def generate_group_name(names):
    k = h("||".join(sorted(names)))
    if k in group_cache:
        return group_cache[k]

    prompt = """
다음 문서 제목들의 공통 주제를 대표하는
짧고 명확한 영문 폴더명 하나만 출력하세요.

규칙:
- 소문자
- snake_case
- 2~4 단어
- 설명 금지
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You generate folder names."},
            {"role": "user", "content": "\n".join(names)},
        ],
        temperature=0.2,
        max_tokens=20,
    )

    name = re.sub(r"[^a-z0-9_]", "", r["choices"][0]["message"]["content"])
    group_cache[k] = name or "misc_documents"
    save_cache(GROUP_CACHE, group_cache)
    return group_cache[k]

def generate_readme(topic, files):
    k = h(topic + "||".join(sorted(files)))
    if k in readme_cache:
        return readme_cache[k]

    prompt = f"""
다음 문서들은 '{topic}' 그룹으로 분류되었습니다.
각 문서 간의 시너지와 활용 목적을 설명하는 README.md를 작성하세요.

문서 목록:
{chr(10).join(files)}
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
    )

    readme_cache[k] = r["choices"][0]["message"]["content"]
    save_cache(README_CACHE, readme_cache)
    return readme_cache[k]

def cluster_documents(files):
    titles = [f"title: {f.name.split('.')[0]}" for f in files]
    vectors = embed_titles(titles)
    return HDBSCAN(min_cluster_size=2).fit_predict(vectors)

# ----------------------------
# 🚀 메인 처리
# ----------------------------
if uploaded_files:
    log("파일 업로드 완료 ✅")
    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    labels = cluster_documents(uploaded_files)

    groups = {}
    for f, l in zip(uploaded_files, labels):
        groups.setdefault(l, []).append(f)

    for i, (label, files) in enumerate(groups.items(), 1):
        names = [f.name.split(".")[0] for f in files]
        group = "unclassified_documents" if label == -1 else generate_group_name(names)

        folder = output_dir / group
        folder.mkdir(exist_ok=True)

        for f in files:
            (folder / f.name).write_bytes(f.getvalue())

        readme = generate_readme(group, [f.name for f in files])
        (folder / "README.md").write_text(readme, encoding="utf-8")

        status_placeholder.markdown(
            f"<div class='status-bar'>[{int(i/len(groups)*100)}% processing]</div>",
            unsafe_allow_html=True,
        )
        log(f"문서 그룹 '{group}' 처리 완료 ✅")

    with zipfile.ZipFile("result_documents.zip", "w") as z:
        for root, _, files in os.walk(output_dir):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, arcname=os.path.relpath(p, output_dir))

    zip_placeholder.download_button(
        "📥 정리된 ZIP 파일 다운로드",
        open("result_documents.zip", "rb"),
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
