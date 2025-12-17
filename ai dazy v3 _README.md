# 🗂️ AI 문서 정리기 (AI Document Organizer)

이 프로젝트는 **Streamlit 기반 웹앱**으로, 여러 형식의 문서 파일(`.md`, `.pdf`, `.txt`)을 업로드하면 자동으로 문서 내용을 분석하고 **주제별로 분류한 뒤 README를 생성**, 최종적으로 ZIP 파일 형태로 정리된 결과를 다운로드할 수 있습니다.

---

## 🚀 주요 기능

### 1️⃣ 문서 임베딩 및 자동 분류
- OpenAI의 `text-embedding-3-large` 모델을 사용하여 문서 제목 임베딩 수행
- `HDBSCAN` 알고리즘을 사용하여 의미 기반 자동 클러스터링

### 2️⃣ 태그 기반 주제 보정
- 각 문서의 키워드(tags)를 임베딩하여 **cosine similarity**로 주제 보정 수행
- 의미가 애매한 태그에 대해서는 `gpt-5-nano`로 주제명 자동 제안

### 3️⃣ 시너지 분석 및 README 자동 생성
- 각 그룹의 문서 요약(`description`)을 기반으로 GPT-4o-mini가 **시너지 효과 설명**을 포함한 `README.md` 생성

### 4️⃣ ZIP 결과 다운로드
- 정리된 폴더 구조를 `.zip`으로 묶어 즉시 다운로드 가능

---

## 🧠 사용 모델 요약
| 단계 | 모델 / 알고리즘 | 역할 |
|------|------------------|------|
| 1 | text-embedding-3-large | 문서 의미 임베딩 |
| 2 | HDBSCAN | 의미 기반 문서 분류 |
| 3 | cosine similarity + gpt-5-nano | 태그 기반 주제 보정 |
| 4 | gpt-4o-mini | README.md 자동 생성 |

---

## 🧩 설치 및 실행

### 🔹 1. 저장소 클론
```bash
git clone https://github.com/yourusername/ai-document-organizer.git
cd ai-document-organizer
```

### 🔹 2. 패키지 설치
```bash
pip install -r requirements.txt
```

### 🔹 3. 환경 변수 설정
프로젝트 루트 디렉터리에 `.streamlit/secrets.toml` 파일을 만들고 아래 내용 추가:
```toml
OPENAI_API_KEY = "your-openai-api-key"
```

### 🔹 4. 실행
```bash
streamlit run app.py
```

---

## 💻 UI 구성

| 사이드바 | 메인 화면 | 하단 |
|-----------|-------------|-------|
| 🔁 다시시작 버튼<br>🌐 언어 선택 드롭다운 | 📤 파일 업로드<br>📦 ZIP 다운로드 버튼 | 🔄 STATUS BAR + LOG 영역 |

---

## 📦 예시 폴더 구조
```
/AI_기초/
   ├── 문서1.md
   ├── 문서2.pdf
   └── README.md
/AI_응용/
   ├── 문서3.txt
   └── README.md
```

---

## 🎨 디자인 특징
- 미니멀 & 트렌디한 **모던 UI (파란 포인트 컬러)**
- 실시간 진행률 표시 바
- 로그 기록 박스 (최근 10개 이벤트 표시)

---

## 🧾 License
MIT License © 2025 [dante J.wook]

---
