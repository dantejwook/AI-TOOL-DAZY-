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
    .status-bar { background:#595656; border-radius:6px; padding:0.5em; margin-top:10px; }
    .log-box { background:#595656; border-radius:6px; padding:0.8em; height:120px; overflow-y:auto; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ----------------------------
# 🧭 사이드바
# ----------------------------
st.sidebar.title("⚙️ 설정")
if st.sidebar.button("🔁 다시 시작"):
    st.session_state.clear()
    st.rerun()

lang = st.sidebar.selectbox("🌐 언어 선택", ["한국어", "English"])

# ----------------------------
# 📁 UI
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
# 📊 상태 / 로그
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
CACHE = Path(".cache")
CACHE.mkdir(exist_ok=True)

def h(t): return hashlib.sha256(t.encode()).hexdigest()

def load(p): return json.loads(p.read_text()) if p.exists() else {}
def save(p, d): p.write_text(json.dumps(d, ensure_ascii=False, indent=2))

emb_cache = load(CACHE / "emb.json")
grp_cache = load(CACHE / "grp.json")
sub_cache = load(CACHE / "sub.json")
readme_cache = load(CACHE / "readme.json")

# ----------------------------
# 🔧 유틸
# ----------------------------
def sanitize(name):
    name = re.sub(r"[^a-z0-9]+", "_", name.lower())
    name = re.sub(r"_+", "_", name).strip("_")
    return name if re.search(r"[a-z]", name) else "misc_documents"

# ----------------------------
# 🤖 OpenAI 함수
# ----------------------------
def embed_titles(titles):
    vectors = []
    missing = []

    for t in titles:
        k = h(t)
        if k in emb_cache:
            vectors.append(emb_cache[k])
        else:
            missing.append(t)

    if missing:
        r = openai.Embedding.create(
            model="text-embedding-3-large",
            input=missing,
        )
        for t, d in zip(missing, r["data"]):
            emb_cache[h(t)] = d["embedding"]
        save(CACHE / "emb.json", emb_cache)

        vectors = [emb_cache[h(t)] for t in titles]

    return vectors

def generate_group_name(names):
    k = h("||".join(sorted(names)))
    if k in grp_cache:
        return grp_cache[k]

    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "\n".join(names)}],
        temperature=0.2,
    )
    name = sanitize(r["choices"][0]["message"]["content"])
    grp_cache[k] = name
    save(CACHE / "grp.json", grp_cache)
    return name

def generate_subgroups(names):
    k = h("SUB||" + "||".join(sorted(names)))
    if k in sub_cache:
        return sub_cache[k]

    prompt = f"""
다음 문서 제목들을 2~4개의 하위 주제로 분류하세요.
결과는 JSON으로, key는 snake_case 영문 폴더명입니다.

문서 제목:
{chr(10).join(names)}
"""
    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    data = json.loads(r["choices"][0]["message"]["content"])
    sub_cache[k] = data
    save(CACHE / "sub.json", sub_cache)
    return data

def generate_readme(title, files):
    k = h(lang + title + "||".join(files))
    if k in readme_cache:
        return readme_cache[k]

    lang_rule = "반드시 한국어로 작성하세요." if lang == "한국어" else "Write in English."

    prompt = f"""
'{title}' 폴더에 대한 README.md를 작성하세요.
{lang_rule}

파일:
{chr(10).join(files)}
"""
    r = openai.ChatCompletion.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "Folder names are English for system use, "
                    "but README language must follow the instruction."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    text = r["choices"][0]["message"]["content"]
    readme_cache[k] = text
    save(CACHE / "readme.json", readme_cache)
    return text

# ----------------------------
# 🚀 메인
# ----------------------------
if uploaded_files:
    uploaded_files = [f for f in uploaded_files if f.name.strip()]
    progress = progress_placeholder.progress(0)

    titles = [f"title: {f.name.split('.')[0]}" for f in uploaded_files]
    labels = HDBSCAN(min_cluster_size=2).fit_predict(embed_titles(titles))

    groups = {}
    for f, l in zip(uploaded_files, labels):
        groups.setdefault(l, []).append(f)

    out = Path("output_docs")
    out.mkdir(exist_ok=True)

    total = len(groups)
    done = 0

    for label, files in groups.items():
        if label == -1:
            group = "미분류_문서" if lang == "한국어" else "unclassified_documents"
        else:
            group = generate_group_name([f.name.split(".")[0] for f in files])

        gdir = out / group
        gdir.mkdir(exist_ok=True)

        subgroups = generate_subgroups([f.name.split(".")[0] for f in files])

        for sub, names in subgroups.items():
            sdir = gdir / sub
            sdir.mkdir(exist_ok=True)

            sub_files = []
            for f in files:
                if f.name.split(".")[0] in names:
                    (sdir / f.name).write_bytes(f.getvalue())
                    sub_files.append(f.name)

            (sdir / "README.md").write_text(
                generate_readme(sub, sub_files),
                encoding="utf-8",
            )

        (gdir / "README.md").write_text(
            generate_readme(group, [f.name for f in files]),
            encoding="utf-8",
        )

        done += 1
        progress.progress(int(done / total * 100))
        progress_text.markdown(
            f"<div class='status-bar'>[{done}/{total} 처리 완료]</div>",
            unsafe_allow_html=True,
        )
        log(f"{group} 완료")

    with zipfile.ZipFile("result_documents.zip", "w") as z:
        for root, _, fs in os.walk(out):
            for f in fs:
                p = os.path.join(root, f)
                z.write(p, arcname=os.path.relpath(p, out))

    zip_placeholder.download_button(
        "📥 정리된 ZIP 파일 다운로드",
        open("result_documents.zip", "rb"),
        file_name="result_documents.zip",
        mime="application/zip",
    )

    progress.progress(100)
    progress_text.markdown(
        "<div class='status-bar'>[100% 완료]</div>",
        unsafe_allow_html=True,
    )

else:
    progress_placeholder.progress(0)
    progress_text.markdown(
        "<div class='status-bar'>[대기 중]</div>",
        unsafe_allow_html=True,
    )
