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
# 🔧 분류 / 재분해 / 시간 설정
# ============================
MAX_FILES_PER_CLUSTER = 25
MAX_RECURSION_DEPTH = 2
AUTO_SPLIT_NOTICE = "⚠️ 이 폴더는 파일 수 제한(25개)으로 인해 자동 분해되었습니다.\n\n"

# 정밀도별 HDBSCAN 파라미터
CLUSTER_PARAMS = {
    1: {"min_cluster_size": 8, "min_samples": 1},  # 느슨
    2: {"min_cluster_size": 5, "min_samples": 1},  # 기본
    3: {"min_cluster_size": 3, "min_samples": 2},  # 타이트
}

# 시간 예측용 평균값 (초)
AVG_EMBED_SEC_PER_FILE = 0.03
AVG_README_SEC_MIN = 1.2
AVG_README_SEC_MAX = 2.0

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
# 🧭 사이드바
# ----------------------------
st.sidebar.title("⚙️ 설정")

if st.sidebar.button("🔁 다시 시작"):
    st.markdown("<script>window.location.reload();</script>", unsafe_allow_html=True)

lang = st.sidebar.selectbox("🌐 언어 선택", ["한국어", "English"])

invalidate_cache = st.sidebar.checkbox(
    "♻️ 정밀도 변경 시 캐시 초기화",
    value=False,
    help="그룹명 / README 캐시만 초기화 (임베딩 유지)"
)

if "tightness" not in st.session_state:
    st.session_state.tightness = 2

tightness = st.sidebar.slider("📊 분류 정밀도", 1, 3, st.session_state.tightness)

if tightness != st.session_state.tightness:
    st.session_state.tightness = tightness
    if invalidate_cache:
        Path(".cache/group_names.json").unlink(missing_ok=True)
        Path(".cache/readmes.json").unlink(missing_ok=True)

if st.sidebar.button("🤖 자동 추천 정밀도"):
    file_count = len(st.session_state.get("uploaded_files", []))
    if file_count <= 30:
        st.session_state.tightness = 3
    elif file_count <= 80:
        st.session_state.tightness = 2
    else:
        st.session_state.tightness = 1
    st.rerun()

# ----------------------------
# 📁 메인 UI
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
    st.session_state.uploaded_files = uploaded_files
    if not uploaded_files:
        st.error("❗ 유효한 파일이 없습니다.")
        st.stop()

with right_col:
    st.subheader("📦 ZIP 다운로드")
    zip_placeholder = st.empty()

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

def h(t): return hashlib.sha256(t.encode("utf-8")).hexdigest()

# ----------------------------
# ✨ 유틸
# ----------------------------
def sanitize_folder_name(name):
    name = re.sub(r"[^\w가-힣\s]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_") or "기타_문서"

def unique_folder_name(base, used):
    if base not in used:
        return base
    i = 1
    while f"{base}_{i}" in used:
        i += 1
    return f"{base}_{i}"

# ----------------------------
# ✨ 임베딩 / 클러스터
# ----------------------------
def embed_titles(titles):
    missing = [t for t in titles if h(t) not in embedding_cache]
    if missing:
        r = openai.Embedding.create(
            model="text-embedding-3-large",
            input=missing,
        )
        for t, d in zip(missing, r["data"]):
            embedding_cache[h(t)] = d["embedding"]
        save_cache(EMBED_CACHE, embedding_cache)
    return [embedding_cache[h(t)] for t in titles]

def cluster_documents(files):
    titles = [f"title: {f.name.split('.')[0]}" for f in files]
    vectors = embed_titles(titles)
    params = CLUSTER_PARAMS[st.session_state.tightness]
    return HDBSCAN(
        min_cluster_size=params["min_cluster_size"],
        min_samples=params["min_samples"],
    ).fit_predict(vectors)

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
# 📊 예상 결과 & 시간 미리보기
# ----------------------------
if uploaded_files:
    st.sidebar.markdown("### 🔍 예상 분류 결과")
    titles = [f"title: {f.name.split('.')[0]}" for f in uploaded_files]
    vectors = embed_titles(titles)
    file_count = len(uploaded_files)
    embed_time = file_count * AVG_EMBED_SEC_PER_FILE

    for lvl, label in [(1, "느슨"), (2, "기본"), (3, "타이트")]:
        p = CLUSTER_PARAMS[lvl]
        labels = HDBSCAN(
            min_cluster_size=p["min_cluster_size"],
            min_samples=p["min_samples"],
        ).fit_predict(vectors)
        folder_count = len(set(labels)) - (1 if -1 in labels else 0)
        folder_count = max(folder_count, 1)

        readme_count = folder_count * 2
        min_t = embed_time + readme_count * AVG_README_SEC_MIN
        max_t = embed_time + readme_count * AVG_README_SEC_MAX

        st.sidebar.write(
            f"{label}: 약 {folder_count}개 / {int(min_t)}~{int(max_t)}초"
        )

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
        main_group = sanitize_folder_name(
            cluster_files[0].name.split(".")[0]
        )
        main_group = generate_group = None

        main_group = sanitize_folder_name(
            generate_group_name([f.name.split(".")[0] for f in cluster_files])
        )

        main_folder = output_dir / main_group
        main_folder.mkdir(parents=True, exist_ok=True)

        readme = AUTO_SPLIT_NOTICE if auto_split else ""
        readme += generate_readme(main_group, [f.name for f in cluster_files])
        (main_folder / "README.md").write_text(readme, encoding="utf-8")

        sub_clusters = recursive_cluster(cluster_files)
        used = set()

        for sub_files in sub_clusters:
            base = sanitize_folder_name(
                generate_group_name([f.name.split(".")[0] for f in sub_files])
            )
            sub_group = unique_folder_name(base, used)
            used.add(sub_group)

            sub_folder = main_folder / sub_group
            sub_folder.mkdir(parents=True, exist_ok=True)

            for f in sub_files:
                (sub_folder / f.name).write_bytes(f.getvalue())

            sub_readme = AUTO_SPLIT_NOTICE if len(sub_files) >= MAX_FILES_PER_CLUSTER else ""
            sub_readme += generate_readme(
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
