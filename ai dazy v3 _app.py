import streamlit as st
import zipfile
import os
from pathlib import Path
import openai
from hdbscan import HDBSCAN
import json
import hashlib
import re

# ============================
# 🔧 재분해 설정
# ============================
MAX_FILES_PER_CLUSTER = 25
MAX_RECURSION_DEPTH = 2
AUTO_SPLIT_NOTICE = "⚠️ 이 폴더는 파일 수 제한(25개)으로 인해 자동 분해되었습니다.\n\n"

# ----------------------------
# 🌈 기본 페이지 설정
# ----------------------------
st.set_page_config(page_title="AI dazy document sorter", page_icon="🗂️", layout="wide")

# ----------------------------
# 🔐 OpenAI API 키 설정
# ----------------------------
openai.api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
if not openai.api_key:
    st.sidebar.error("🚨 OpenAI API Key가 없습니다.")
    st.stop()
else:
    st.sidebar.success("✅ OpenAI Key 로드 완료")

# ----------------------------
# 🎨 스타일 (기존 유지)
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
        background-color: #595656; border-radius: 6px;
        padding: 0.5em; margin-top: 20px; font-size: 0.9em;
    }
    .log-box {
        background-color: #595656; border-radius: 6px;
        padding: 0.8em; margin-top: 10px;
        height: 120px; overflow-y: auto; font-size: 0.85em;
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
if st.sidebar.button("🔁 다시 시작"):
    st.markdown("<script>window.location.reload();</script>", unsafe_allow_html=True)

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

def unique_folder_name(base: str, existing: set) -> str:
    """같은 이름이 있으면 _1, _2 자동 부여"""
    if base not in existing:
        return base
    i = 1
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"

# ----------------------------
# ✨ OpenAI / 임베딩
# ----------------------------
def embed_titles(titles):
    missing = []
    for t in titles:
        if h(t) not in embedding_cache:
            missing.append(t)

    if missing:
        r = openai.Embedding.create(
            model="text-embedding-3-large",
            input=missing,
        )
        for t, d in zip(missing, r["data"]):
            embedding_cache[h(t)] = d["embedding"]
        save_cache(EMBED_CACHE, embedding_cache)

    return [embedding_cache[h(t)] for t in titles]

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
    k = h(("split" if auto_split else "nosplit") + "||" + topic + "||" + "||".join(sorted(files)))
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

    content = r["choices"][0]["message"]["content"].strip()
    final = notice + content
    readme_cache[k] = final
    save_cache(README_CACHE, readme_cache)
    return final

def cluster_documents(files):
    titles = [f"title: {f.name.split('.')[0]}" for f in files]
    vectors = embed_titles(titles)
    return HDBSCAN(min_cluster_size=5, min_samples=1).fit_predict(vectors)

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

    final = []
    for g in result:
        if len(g) > MAX_FILES_PER_CLUSTER:
            for i in range(0, len(g), MAX_FILES_PER_CLUSTER):
                final.append(g[i:i + MAX_FILES_PER_CLUSTER])
        else:
            final.append(g)

    return final

# ----------------------------
# 🚀 메인 처리
# ----------------------------
if uploaded_files:
    progress = progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)
    log("파일 업로드 완료")

    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    top_clusters = recursive_cluster(uploaded_files)
    total = len(top_clusters)
    done = 0

    for cluster_files in top_clusters:
        auto_split = len(cluster_files) > MAX_FILES_PER_CLUSTER
        main_group = generate_group_name([f.name.split(".")[0] for f in cluster_files])

        main_folder = output_dir / main_group
        main_folder.mkdir(parents=True, exist_ok=True)

        # 📄 대분류 README
        main_readme = generate_readme(
            main_group,
            [f.name for f in cluster_files],
            auto_split=auto_split,
        )
        (main_folder / "★README.md").write_text(main_readme, encoding="utf-8")

        # 🔹 중분류
        sub_clusters = recursive_cluster(cluster_files)
        used_names = set()

        for sub_files in sub_clusters:
            base_name = generate_group_name([f.name.split(".")[0] for f in sub_files])
            sub_group = unique_folder_name(base_name, used_names)
            used_names.add(sub_group)

            sub_folder = main_folder / sub_group
            sub_folder.mkdir(parents=True, exist_ok=True)

            for f in sub_files:
                (sub_folder / f.name).write_bytes(f.getvalue())

            sub_readme = generate_readme(
                f"{main_group} - {sub_group}",
                [f.name for f in sub_files],
                auto_split=len(sub_files) >= MAX_FILES_PER_CLUSTER,
            )
            (sub_folder / "★README.md").write_text(sub_readme, encoding="utf-8")

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
