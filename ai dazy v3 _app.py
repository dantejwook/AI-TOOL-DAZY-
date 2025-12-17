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
# 🔐 OpenAI API 키 설정 (legacy)
# ----------------------------
openai.api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

if not openai.api_key:
    st.sidebar.error("🚨 OpenAI API Key가 없습니다. secrets.toml 또는 환경변수를 확인하세요.")
    st.stop()
else:
    st.sidebar.success("✅ OpenAI Key 로드 완료")

# ----------------------------
# 🎨 스타일 커스터마이징 (기존 유지)
# ----------------------------
st.markdown(
    """
    <style>
    body { background-color: #f8f9fc; font-family: 'Pretendard', sans-serif; }
    .stButton>button {
        border-radius: 10px;
        background-color: #4a6cf7;
        color: white;
        border: none;
        padding: 0.6em 1.2em;
        font-weight: 600;
        transition: 0.2s;
    }
    .stButton>button:hover { background-color: #3451c1; }
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
# 🧭 사이드바 (기존 유지)
# ----------------------------
st.sidebar.title("⚙️ 설정")

lang = st.sidebar.selectbox("🌐 언어 선택", ["한국어", "English"])

# ----------------------------
# 📁 메인 UI (기존 유지)
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
# ⚙️ 상태 / 로그 (기존 유지)
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
# 🧠 캐시
# ----------------------------
CACHE_DIR = Path(".cache")
CACHE_DIR.mkdir(exist_ok=True)

def load_cache(p):
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:
        return {}

def save_cache(p, d):
    p.write_text(json.dumps(d, ensure_ascii=False, indent=2))

EMBED_CACHE = CACHE_DIR / "embeddings.json"
GROUP_CACHE = CACHE_DIR / "group_names.json"
README_CACHE = CACHE_DIR / "readmes.json"

embedding_cache = load_cache(EMBED_CACHE)
group_cache = load_cache(GROUP_CACHE)
readme_cache = load_cache(README_CACHE)

def h(t): 
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

# ----------------------------
# ✨ 유틸
# ----------------------------
def sanitize_folder_name(name: str) -> str:
    name = (name or "").strip()
    name = re.sub(r"[^\w가-힣\s]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_") or "기타_문서"

# ----------------------------
# ✨ OpenAI 함수
# ----------------------------
def embed_titles(titles):
    vectors = []
    missing = []

    for t in titles:
        k = h(t)
        if k in embedding_cache:
            vectors.append(embedding_cache[k])
        else:
            missing.append(t)

    if missing:
        r = openai.Embedding.create(
            model="text-embedding-3-large",
            input=missing,
        )
        for t, d in zip(missing, r["data"]):
            embedding_cache[h(t)] = d["embedding"]
        save_cache(EMBED_CACHE, embedding_cache)

        vectors = [embedding_cache[h(t)] for t in titles]

    return vectors

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

def generate_readme(topic, files):
    k = h("ko||" + topic + "||" + "||".join(sorted(files)))
    if k in readme_cache:
        return readme_cache[k]

    prompt = f"""
다음 문서들은 '{topic}' 주제로 분류된 자료입니다.
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

    content = r["choices"][0]["message"]["content"].strip()
    readme_cache[k] = content
    save_cache(README_CACHE, readme_cache)
    return content

def cluster_documents(files):
    titles = [f"title: {f.name.split('.')[0]}" for f in files]
    return HDBSCAN(min_cluster_size=2).fit_predict(embed_titles(titles))

# ----------------------------
# 🚀 메인 로직 (중복 제거 완료)
# ----------------------------
if uploaded_files:
    progress = progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)
    log("파일 업로드 완료")

    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    labels = cluster_documents(uploaded_files)
    groups = {}
    for f, l in zip(uploaded_files, labels):
        groups.setdefault(l, []).append(f)

    total = len(groups)
    done = 0

    for label, files in groups.items():
        main_group = (
            "미분류_문서"
            if label == -1
            else generate_group_name([f.name.split(".")[0] for f in files])
        )

        main_folder = output_dir / main_group
        main_folder.mkdir(parents=True, exist_ok=True)

        # 📄 대분류 README만 생성 (❌ 파일 저장 안 함)
        main_readme = generate_readme(main_group, [f.name for f in files])
        (main_folder / "README.md").write_text(main_readme, encoding="utf-8")

        # 🔹 중분류
        sub_labels = cluster_documents(files)
        sub_groups = {}
        for f, sl in zip(files, sub_labels):
            sub_groups.setdefault(sl, []).append(f)

        for sl, sub_files in sub_groups.items():
            sub_group = (
                "기타"
                if sl == -1
                else generate_group_name([f.name.split(".")[0] for f in sub_files])
            )

            sub_folder = main_folder / sub_group
            sub_folder.mkdir(parents=True, exist_ok=True)

            # ✅ 파일 저장은 여기서만!
            for f in sub_files:
                (sub_folder / f.name).write_bytes(f.getvalue())

            # 📄 중분류 README
            sub_readme = generate_readme(
                f"{main_group} - {sub_group}",
                [f.name for f in sub_files],
            )
            (sub_folder / "README.md").write_text(sub_readme, encoding="utf-8")

        done += 1
        pct = int(done / total * 100)
        progress.progress(pct)
        progress_text.markdown(
            f"<div class='status-bar'>[{pct}% ({done}/{total})]</div>",
            unsafe_allow_html=True,
        )
        log(f"{main_group} 처리 완료")

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

    progress.progress(100)
    progress_text.markdown(
        "<div class='status-bar'>[100% complete]</div>",
        unsafe_allow_html=True,
    )
    log("모든 문서 정리 완료")

else:
    progress_placeholder.progress(0)
    progress_text.markdown(
        "<div class='status-bar'>[대기 중]</div>",
        unsafe_allow_html=True,
    )
    log_box.markdown("<div class='log-box'>대기 중...</div>", unsafe_allow_html=True)
