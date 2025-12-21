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
import numpy as np


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

# ============================
# 📊 상태바 업데이트 헬퍼
# ============================
def update_progress(pct: int, msg: str):
    """상태바 + 로그 동시에 업데이트"""
    try:
        pct = max(0, min(100, int(pct)))  # 0~100 사이로 제한
        progress_placeholder.progress(pct)
        progress_text.markdown(
            f"<div class='status-bar'>| {msg} | [ {pct}% ]</div>",
            unsafe_allow_html=True
        )
        log(msg)
    except Exception as e:
        st.warning(f"⚠️ 상태 업데이트 오류: {e}")


# 기본 영역 ----------------------------------------------------------------------------------------------------------------------------------------------------

# 기능 영역 ----------------------------------------------------------------------------------------------------------------------------------------------------

# ============================
# ✨ 유틸 (파일/캐시 함수)
# ============================
def sanitize_folder_name(name: str) -> str:
    """폴더/파일 이름에서 특수문자 제거하고 안전한 이름으로 변환"""
    name = (name or "").strip()
    name = re.sub(r"[^\w가-힣\s]", "", name)
    name = re.sub(r"\s+", "_", name)
    return name.strip("_") or "기타_문서"
    
def title_from_filename(file_name: str) -> str:
    """파일 이름에서 확장자를 제거하고, 밑줄/하이픈 등을 공백으로 바꾼 제목 문자열 반환"""
    base = file_name.rsplit(".", 1)[0]
    base = re.sub(r"[_\\-]+", " ", base)
    base = re.sub(r"\\s+", " ", base).strip()
    return base

def embed_texts(texts, batch_size=50):
    """입력 텍스트 리스트를 OpenAI 임베딩 API로 변환 (대용량 안전)"""
    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        missing = [t for t in batch if h(t) not in embedding_cache]

        if missing:
            try:
                r = openai.Embedding.create(
                    model="text-embedding-3-large",
                    input=missing,
                )
                for t, d in zip(missing, r["data"]):
                    embedding_cache[h(t)] = d["embedding"]
                save_cache(EMBED_CACHE, embedding_cache)
            except Exception as e:
                st.error(f"❌ 임베딩 생성 중 오류 발생 (batch {i//batch_size+1}): {e}")
                continue

        results.extend([embedding_cache[h(t)] for t in batch])

    return results

def load_category_structure(readme_file):
    text = readme_file.getvalue().decode("utf-8")
    prompt = f"""
다음은 블로그 카테고리 및 세부 주제 정리 문서입니다.
이 문서를 JSON 트리 구조로 변환하세요.

출력 예시:
[
  {{"category": "시장 이해 & 트렌드", "subtopics": ["뷰티업계 산업 트렌드", "국내 뷰티업계 트렌드 변화"]}},
  {{"category": "국내외 뷰티업계 핫이슈", "subtopics": ["정책·규제·시장 이슈"]}}
]
"""

    r = openai.ChatCompletion.create(
        model="gpt-4.1-mini",
        messages=[
            {"role": "system", "content": "너는 문서를 JSON 구조로 파싱하는 전문가다."},
            {"role": "user", "content": prompt + "\n" + text}
        ],
        temperature=0
    )

    try:
        return json.loads(r["choices"][0]["message"]["content"])
    except Exception:
        st.error("카테고리 구조를 파싱하는 중 오류가 발생했습니다.")
        return []

# ============================
# 📘 README 기반 폴더 생성 (선택)
# ============================

def create_category_folders(base_dir, category_structure):
    folder_map = {}
    for cat in category_structure:
        cat_folder = base_dir / f"{sanitize_folder_name(cat['category'])}"
        cat_folder.mkdir(exist_ok=True)
        sub_map = {}
        for sub in cat.get("subtopics", []):
            sub_folder = cat_folder / sanitize_folder_name(sub)
            sub_folder.mkdir(exist_ok=True)
            sub_map[sub] = sub_folder
        folder_map[cat['category']] = sub_map
    return folder_map

# ============================
# 🧠 문서 확장 + 임베딩 통합
# ============================

def embed_texts(texts, batch_size=40):
    """입력 텍스트 리스트를 OpenAI 임베딩 API로 변환 (대용량/토큰 제한 안전 버전)"""
    results = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        missing = [t for t in batch if h(t) not in embedding_cache]

        if missing:
            try:
                # 각 batch별 임베딩 요청
                r = openai.Embedding.create(
                    model="text-embedding-3-large",
                    input=missing,
                )
                for t, d in zip(missing, r["data"]):
                    embedding_cache[h(t)] = d["embedding"]

                # ✅ 캐시 저장
                save_cache(EMBED_CACHE, embedding_cache)
                log(f"🧩 임베딩 batch {i//batch_size + 1} 완료 ({len(batch)}개)")
            except Exception as e:
                st.error(f"❌ 임베딩 batch {i//batch_size + 1} 오류: {e}")
                continue

        # 캐시된 벡터를 순서대로 append
        results.extend([embedding_cache[h(t)] for t in batch])

    return results


def prepare_blog_embeddings(files):
    """블로그 초안 임베딩 생성 (방어 버전)"""
    texts, file_objs = [], []

    for f in files:
        try:
            text = f.getvalue().decode("utf-8", errors="ignore")
        except Exception:
            st.warning(f"⚠️ {f.name} 파일 읽기 실패 — 건너뜀")
            continue

        title = title_from_filename(f.name)
        clean_text = re.sub(r"\s+", " ", text.strip())[:4000]  # 4000자 제한
        texts.append(f"제목: {title}\n내용: {clean_text}")
        file_objs.append(f)

    if not texts:
        st.error("❌ 업로드된 블로그 초안에서 읽을 수 있는 문서가 없습니다.")
        return {}

    vectors = embed_texts(texts)

    if not vectors or len(vectors) != len(file_objs):
        st.error(f"❌ 임베딩 생성 실패: {len(vectors)} / 기대값 {len(file_objs)}")
        return {}

    st.write(f"✅ 임베딩 완료: {len(vectors)}개 문서 변환됨.")
    return dict(zip(file_objs, vectors))


# ============================
# 📦 클러스터링 + 자동 재분해 (조건부)
# ============================

def match_documents_to_categories(embeddings, category_structure):
    """문서와 카테고리 매칭 (방어 + 디버그 버전)"""

    # ✅ 1단계: 임베딩 유효성 검사
    if not embeddings or not isinstance(embeddings, dict):
        st.error("❌ 임베딩 데이터가 비어 있거나 잘못되었습니다.")
        st.write(f"⚙️ embeddings 타입: {type(embeddings)} / 길이: {len(embeddings) if embeddings else 0}")
        return {}

    try:
        sample_names = [f.name for f in list(embeddings.keys())[:3]]
        st.write(f"📊 임베딩 샘플: {sample_names}")
    except Exception:
        st.warning("⚠️ 임베딩 키 샘플 표시 중 오류 (무시 가능)")

    all_topics = []
    for c in category_structure:
        for sub in c.get("subtopics", []):
            all_topics.append((c["category"], sub))

    if not all_topics:
        st.error("❌ 카테고리 구조에 subtopics가 없습니다. README 파일 확인 필요.")
        return {}

    topic_texts = [f"{cat} - {sub}" for cat, sub in all_topics]
    topic_embeddings = embed_texts(topic_texts)

    if not topic_embeddings or len(topic_embeddings) != len(all_topics):
        st.error("❌ 카테고리 주제 임베딩 실패.")
        return {}

    # ✅ 안전하게 numpy 배열 생성
    try:
        doc_vecs = np.array(list(embeddings.values()), dtype=float)
    except Exception as e:
        st.error(f"❌ 문서 임베딩 배열 변환 중 오류: {e}")
        return {}

    sim = cosine_similarity(doc_vecs, np.array(topic_embeddings))
    match_results = {cat: {sub: [] for sub in [s for _, s in all_topics if _ == cat]} for cat, _ in all_topics}

    for i, (file_obj, _) in enumerate(embeddings.items()):
        best_idx = int(np.argmax(sim[i]))
        cat, sub = all_topics[best_idx]
        match_results[cat][sub].append(file_obj)

    st.success("✅ 문서-카테고리 매핑 완료.")
    return match_results

# ============================
# ✨ GPT 폴더명 / README 생성
# ============================

def generate_summary_readme(category, subtopic, files):
    file_titles = [title_from_filename(f.name) for f in files]
    file_titles_text = "\n".join(f"- {t}" for t in file_titles)

    prompt = f"""
'{category}' 카테고리의 '{subtopic}' 주제와 관련된 블로그 초안들입니다.
이 글들의 공통된 방향성과 시너지, 주제적 연결성을 분석하고
README 요약 파일을 작성하세요.

형식:
# README_{subtopic}

## 📘 주제 개요
(이 주제가 다루는 핵심 내용)

## 🤝 시너지 & 연관성
(파일들이 어떤 방향으로 연결되어 있는지)

## 🎯 공통 목표
(이 주제에서 일관된 핵심 목표는 무엇인지)

### 포함된 문서 목록
{file_titles_text}
"""

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "너는 블로그 카테고리 기반 요약문서를 생성하는 전문가다."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.5,
    )

    return r["choices"][0]["message"]["content"].strip()

# ============================
# 🚀 메인 파이프라인 실행 (상태바 포함)
# ============================

if uploaded_files:
    # 초기 상태 0%
    update_progress(0, "대기 중…")

    readme_file = None
    blog_files = []
    for f in uploaded_files:
        if "readme" in f.name.lower():
            readme_file = f
        else:
            blog_files.append(f)

    if not readme_file:
        st.error("카테고리 구조가 담긴 README 파일이 필요합니다.")
        st.stop()

    reset_output()
    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True)

    # 단계별 가중치 (총 100%)
    # 파싱 10, 임베딩 25, 매핑 25, README 생성 35, ZIP 5
    update_progress(5, "환경 초기화…")

    # 1) 카테고리 파싱 (10%)
    update_progress(10, "📘 카테고리 구조 분석 중…")
    category_structure = load_category_structure(readme_file)

    # 폴더 뼈대 생성 (UI 변화 없음)
    folder_map = create_category_folders(output_dir, category_structure)
    update_progress(15, "📂 폴더 구조 준비 완료")

    # 2) 임베딩 (25%)
    update_progress(20, "🧠 블로그 문서 임베딩 생성 중…")
    embeddings = prepare_blog_embeddings(blog_files)
    update_progress(35, "🧠 임베딩 완료")

    # 3) 매핑 (25%)
    update_progress(40, "📦 문서를 카테고리별로 매핑 중…")
    mapping = match_documents_to_categories(embeddings, category_structure)
    update_progress(65, "📦 매핑 완료")

    # 4) README 생성 (35%) — 하위 단위별로 세밀 진행률
    # 전체 README 생성 개수 계산
    total_subtopics = sum(len(v.get("subtopics", [])) for v in category_structure)
    # 실제 문서가 매핑된 subtopic만 집계
    total_work_units = max(
        1,
        sum(len(files) > 0 for _, subtopics in mapping.items() for _, files in subtopics.items())
    )

    unit_weight = 35 / total_work_units  # 각각의 주제 완료 시 진행률 반영
    cur_pct = 65
    update_progress(cur_pct, "📝 README 요약 생성 시작…")

    for category, subtopics in mapping.items():
        cat_folder = output_dir / sanitize_folder_name(category)
        cat_folder.mkdir(exist_ok=True)

        for sub, files in subtopics.items():
            if not files:
                continue

            sub_folder = cat_folder / sanitize_folder_name(sub)
            sub_folder.mkdir(exist_ok=True)

            # 파일 저장
            for f in files:
                (sub_folder / f.name).write_bytes(f.getvalue())

            # README 생성
            summary = generate_summary_readme(category, sub, files)
            (sub_folder / f"README_{sanitize_folder_name(sub)}.md").write_text(
                summary, encoding="utf-8"
            )

            # 진행률 갱신
            cur_pct = min(100, int(cur_pct + unit_weight))
            update_progress(cur_pct, f"📝 README 생성 중… ({category} > {sub})")

    # 5) ZIP (5%)
    update_progress(95, "📦 ZIP 파일 생성 중…")
    zip_path = Path("result_documents.zip")
    with zipfile.ZipFile(zip_path, "w") as z:
        for root, _, files in os.walk(output_dir):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, arcname=os.path.relpath(p, output_dir))

    zip_placeholder.download_button(
        "[ Download Result ]",
        open("result_documents.zip", "rb"),
        file_name="categorized_blogs.zip",
        mime="application/zip",
        use_container_width=True,
    )

    update_progress(100, "✅ 모든 카테고리 분류 및 README 요약 완료!")

# 기능 영역 ----------------------------------------------------------------------------------------------------------------------------------------------------

else:
    progress_placeholder.progress(0)
    progress_text.markdown("<div class='status-bar'>[0%]</div>", unsafe_allow_html=True)
    log_box.markdown("<div class='log-box'>......</div>", unsafe_allow_html=True)
