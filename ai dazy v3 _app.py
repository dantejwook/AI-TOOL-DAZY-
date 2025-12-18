import streamlit as st
import zipfile
import os
from pathlib import Path
import openai
from hdbscan import HDBSCAN
import json
import hashlib
import re
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================
# 🔧 change log
# ============================
 대용량 처리 적용 버젼

# ============================
# 🔧 대용량 처리 설정 (1000개 기준)
# ============================
MAX_FILES_PER_CLUSTER = 25
MAX_RECURSION_DEPTH = 2
AUTO_SPLIT_NOTICE = "⚠️ 이 폴더는 파일 수 제한(25개)으로 인해 자동 분해되었습니다.\n\n"

BATCH_SIZE = 50
MAX_WORKERS = 5
BATCH_SLEEP = 0.2

# ----------------------------
# 🌈 기본 페이지 설정
# ----------------------------
st.set_page_config(
    page_title="AI dazy document sorter",
    page_icon="🗂️",
    layout="wide",
)

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
# 🎨 스타일
# ----------------------------
st.markdown(
    """
    <style>
    body { background-color: #f8f9fc; font-family: 'Pretendard', sans-serif; }
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

def h(t: str):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

# ----------------------------
# 📁 UI
# ----------------------------
uploaded_files = st.file_uploader(
    "문서를 업로드하세요 (.md, .pdf, .txt)",
    accept_multiple_files=True,
    type=["md", "pdf", "txt"],
)

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
def title_from_filename(file_name: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[_\-]+", " ", file_name.rsplit(".", 1)[0])).strip()

def chunked(lst, size):
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

# ----------------------------
# 🧠 0차 GPT EXPAND (단일)
# ----------------------------
def expand_document_with_gpt(file):
    key = h(file.name)
    if key in expand_cache:
        return expand_cache[key]

    title = title_from_filename(file.name)

    try:
        r = openai.ChatCompletion.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": "문서를 의미적으로 정규화하라. JSON만 출력."},
                {"role": "user", "content": f"문서 파일명:\n{file.name}"},
            ],
            temperature=0.2,
        )
        data = json.loads(r["choices"][0]["message"]["content"])
        if "embedding_text" not in data:
            raise ValueError
    except Exception:
        data = {
            "canonical_title": title,
            "keywords": title.split(),
            "domain": "기타",
            "embedding_text": f"제목: {title}",
        }

    expand_cache[key] = data
    save_cache(EXPAND_CACHE, expand_cache)
    return data

# ----------------------------
# 🚀 0차 EXPAND 병렬 + 배치
# ----------------------------
def expand_documents_batched(files):
    expanded = {}
    batches = list(chunked(files, BATCH_SIZE))
    total = len(files)
    done = 0

    for i, batch in enumerate(batches, start=1):
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(expand_document_with_gpt, f): f for f in batch}
            for future in as_completed(futures):
                f = futures[future]
                expanded[f] = future.result()
                done += 1

                pct = int(done / total * 100)
                progress_placeholder.progress(pct)
                progress_text.markdown(
                    f"<div class='status-bar'>🧠 0차 분석 중… "
                    f"[{pct}%] ({done} / {total})</div>",
                    unsafe_allow_html=True,
                )

        log(f"Batch {i}/{len(batches)} 완료")
        time.sleep(BATCH_SLEEP)

    return [expanded[f] for f in files]

# ----------------------------
# 📦 임베딩
# ----------------------------
def embed_texts(texts):
    missing = [t for t in texts if h(t) not in embedding_cache]
    for chunk in chunked(missing, 100):
        r = openai.Embedding.create(
            model="text-embedding-3-large",
            input=chunk,
        )
        for t, d in zip(chunk, r["data"]):
            embedding_cache[h(t)] = d["embedding"]
        save_cache(EMBED_CACHE, embedding_cache)

    return [embedding_cache[h(t)] for t in texts]

# ----------------------------
# 📦 클러스터링
# ----------------------------
def cluster_documents(files):
    expanded = expand_documents_batched(files)
    vectors = embed_texts([e["embedding_text"] for e in expanded])
    return HDBSCAN(min_cluster_size=3, min_samples=1).fit_predict(vectors)

# ----------------------------
# 🚀 실행
# ----------------------------
if uploaded_files:
    labels = cluster_documents(uploaded_files)
    progress_text.markdown(
        "<div class='status-bar'>✅ 0차 분석 완료</div>",
        unsafe_allow_html=True,
    )
