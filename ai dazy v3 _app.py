#last, rollbacK 용

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

# ⭐ 추가: 병렬 처리용
from concurrent.futures import ThreadPoolExecutor, as_completed

# ============================
# 🔧change log
# ============================

# 1.캐시 초기화 적용 버젼
# 2.다시시작 버튼 제거
# 3.대용량 처리 가능
# 4.사이드바에 사용법 추가가

# ============================

# ============================
# 🔧 재분해 설정
# ============================
MAX_FILES_PER_CLUSTER = 25
MAX_RECURSION_DEPTH = 2
AUTO_SPLIT_NOTICE = "⚠️ 이 폴더는 파일 수 제한(25개)으로 인해 자동 분해되었습니다.\n\n"

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
st.sidebar.tittle("✂️ F5 : 초기화")
st.sidebar.markdown(
    """
- ⚙️ 다시 시작하시려면 
-  ㄴ캐시 초기화 > 다운로드 초기화 > F5 순서대로 눌러주세요.
-     ㄴ warning : 중복 다운로드 우려가 있습니다.
"""
)

# ▶ 사이드바 버튼 (분리)
if st.sidebar.button("🧹 캐시 초기화"):
    reset_cache()
    st.sidebar.success("✅ 캐시가 초기화되었습니다.")
    st.rerun()

if st.sidebar.button("🗑️ 결과 폴더 초기화"):
    reset_output()
    st.sidebar.success("✅ 결과 폴더가 초기화되었습니다.")
    st.rerun()

def h(t: str):
    return hashlib.sha256(t.encode("utf-8")).hexdigest()

st.sidebar.title("💡 사용 팁")
st.sidebar.markdown(
    """
- ⏳ 업로드 하면 자동으로 시작됩니다.
- 📂 **여러 문서를 한 번에 업로드**할 수 있습니다.
- 🧠 문서는 **AI가 자동으로 주제별 분류**합니다.
- 📁 폴더 수가 많으면 **자동으로 하위 폴더로 분해**됩니다.
- ⏳ 문서 수가 많을수록 처리 시간이 늘어납니다.
- 📦 완료 후 **ZIP 파일로 한 번에 다운로드**할 수 있습니다.
"""
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
        "📥 정리된 ZIP 파일 다운로드",
        open(zip_path, "rb"),
        file_name=zip_path.name,
        mime="application/zip",
    )

    progress.progress(100)
    progress_text.markdown("<div class='status-bar'>[100% complete]</div>", unsafe_allow_html=True)
    log("모든 문서 정리 완료")

else:
    progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[대기 중]</div>", unsafe_allow_html=True)
    log_box.markdown("<div class='log-box'>대기 중...</div>", unsafe_allow_html=True)
