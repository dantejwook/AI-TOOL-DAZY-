import streamlit as st
import zipfile
import os
from pathlib import Path
from sklearn.cluster import HDBSCAN
from openai import OpenAI

# ----------------------------
# 🌈 기본 페이지 설정
# ----------------------------
st.set_page_config(
    page_title="AI dazy document sorter",
    page_icon="🗂️",
    layout="wide"
)

# ----------------------------
# 🔐 OpenAI API 키 설정
# ----------------------------
OPENAI_API_KEY = (
    st.secrets.get("OPENAI_API_KEY")
    if hasattr(st, "secrets")
    else None
) or os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    st.sidebar.error("🚨 OpenAI API Key가 없습니다.")
    st.stop()

st.sidebar.success("✅ OpenAI Key 로드 완료")

# ✅ 최신 SDK 공식 클라이언트 (단일 인스턴스)
client = OpenAI(api_key=OPENAI_API_KEY)

# ----------------------------
# 🎨 스타일
# ----------------------------
st.markdown(
    """
    <style>
    body { background-color: #f8f9fc; }
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
    st.session_state.clear()
    st.rerun()

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

if uploaded_files:
    uploaded_files = [f for f in uploaded_files if f and hasattr(f, "name")]

with right_col:
    st.subheader("📦 ZIP 다운로드")
    zip_placeholder = st.empty()

# ----------------------------
# 로그 UI
# ----------------------------
status_placeholder = st.empty()
log_box = st.empty()
log_messages = []

def log(msg: str):
    log_messages.append(msg)
    log_box.markdown(
        "<div class='log-box'>" + "<br>".join(log_messages[-10:]) + "</div>",
        unsafe_allow_html=True,
    )

# ----------------------------
# ✨ AI 기능 (최신 SDK)
# ----------------------------
def embed_titles(titles: list[str]) -> list[list[float]]:
    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=titles,
    )
    return [item.embedding for item in response.data]

def cluster_documents(files):
    titles = [f"title: {f.name.split('.')[0]}" for f in files]
    vectors = embed_titles(titles)
    clusterer = HDBSCAN(min_cluster_size=2)
    return clusterer.fit_predict(vectors)

def generate_readme(topic: str, file_names: list[str]) -> str:
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
    return response.choices[0].message.content.strip()

# ----------------------------
# 🚀 메인 처리
# ----------------------------
if uploaded_files:
    log("파일 업로드 완료 ✅")

    output_dir = Path("output_docs")
    output_dir.mkdir(exist_ok=True, parents=True)

    try:
        labels = cluster_documents(uploaded_files)
    except Exception as e:
        st.error(f"문서 클러스터링 실패: {e}")
        st.stop()

    groups = {}
    for file, label in zip(uploaded_files, labels):
        group_name = f"Group_{label if label >= 0 else 'Unclassified'}"
        groups.setdefault(group_name, []).append(file)

    for i, (group, files) in enumerate(groups.items(), start=1):
        folder = output_dir / group
        folder.mkdir(exist_ok=True)

        for f in files:
            with open(folder / f.name, "wb") as out:
                out.write(f.read())

        readme = generate_readme(group, [f.name for f in files])
        with open(folder / "README.md", "w", encoding="utf-8") as r:
            r.write(readme)

        progress = int((i / len(groups)) * 100)
        status_placeholder.markdown(
            f"<div class='status-bar'>[{progress}% processing]</div>",
            unsafe_allow_html=True,
        )
        log(f"{group} 처리 완료")

    zip_name = "result_documents.zip"
    with zipfile.ZipFile(zip_name, "w") as zipf:
        for folder, _, files in os.walk(output_dir):
            for file in files:
                p = os.path.join(folder, file)
                zipf.write(p, arcname=os.path.relpath(p, output_dir))

    with open(zip_name, "rb") as f:
        zip_placeholder.download_button(
            "📥 정리된 ZIP 파일 다운로드",
            f,
            zip_name,
            "application/zip",
        )

    log("✅ 모든 문서 정리 완료")

else:
    status_placeholder.markdown(
        "<div class='status-bar'>[대기 중]</div>",
        unsafe_allow_html=True,
    )
