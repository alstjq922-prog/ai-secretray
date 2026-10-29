# AI 비서실 — 설치 안내

하루 3번(06:30 · 12:00 · 17:30) 비서 6명이 보고서를 만들고, 내가 필요할 때 웹페이지로 확인합니다.
보고서는 비밀번호로 암호화되어 저장되므로 주소가 알려져도 내용은 보이지 않습니다.

| 비서 | 하는 일 | 데이터 |
|---|---|---|
| 일정 | 오늘·이번 주 일정, 준비사항 | 구글 캘린더 |
| SNS | 정치인 SNS 발언 중 쟁점만 | 네이버 뉴스(SNS 인용 기사) + 네이버 블로그 |
| 언론 | 전국 지자체 '최초'·우수 정책 | 네이버 뉴스 |
| 정책 | 화성시 적용 정책안 (주 1회) | 언론 비서 결과 |
| 국회·의회 | 상임위 통과 이상 법안 + 도·시의회 | 열린국회정보 + 네이버 뉴스 |
| 여론·민원 | 진영별 커뮤니티 여론 + 화성 맘카페 민원 | 커뮤니티 인기글 + 네이버 카페 |

---

## 1. 키 발급 (Claude만 유료)

### ① 네이버 검색 API — 무료
1. https://developers.naver.com 로그인 → 상단 **Application > 애플리케이션 등록**
2. 이름: 아무거나 / 사용 API: **검색** / 환경: **WEB 설정**, URL: `http://localhost`
3. 등록 후 나오는 **Client ID**, **Client Secret** 복사

### ② 열린국회정보 API — 무료
1. https://open.assembly.go.kr 회원가입 → 로그인
2. **마이페이지 > 인증키 발급** → 용도 간단히 적고 발급 → 인증키 복사

### ③ Claude API — 유료(소액)
1. https://console.anthropic.com 가입 → **Billing**에서 카드 등록 후 소액 충전(예: $5)
2. **API Keys > Create Key** → 키 복사 (한 번만 보이니 바로 저장)
3. 과금 폭주 방지: **Limits**에서 월 사용 한도 설정 권장

### ④ 구글 캘린더 — 무료
1. 갤럭시 **설정 > 계정 및 백업 > 계정 관리**에 구글 계정 추가 → 삼성 캘린더에서 일정 저장 위치를 **구글 캘린더**로 선택
   (기존 일정은 삼성 캘린더 앱에서 구글 계정으로 이동)
2. PC에서 https://calendar.google.com → 톱니바퀴 **설정** → 왼쪽에서 내 캘린더 선택
3. **캘린더 통합 > iCal 형식의 비밀 주소** 복사 (이 주소는 남에게 알려주면 안 됩니다)
   - 캘린더가 여러 개면 주소를 쉼표(,)로 이어 붙이면 됩니다.

---

## 2. GitHub에 올리기 — 무료

1. https://github.com 가입 → 오른쪽 위 **+ > New repository**
   - 이름: `ai-secretary` / **Public** 선택(무료로 웹페이지를 열려면 공개 저장소 필요, 보고서는 암호화됨) → Create
2. 생성된 화면의 **uploading an existing file** 클릭 → `ai-secretary` 폴더 **안의 내용 전부**를 끌어다 놓기 → Commit
   - `.github` 폴더가 빠지기 쉽습니다. 업로드 후 저장소에 `.github/workflows/run.yml`이 없으면
     **Add file > Create new file**에서 파일 이름에 `.github/workflows/run.yml`을 입력하고 내용을 붙여 넣으세요.

## 3. 비밀값 등록

저장소 **Settings > Secrets and variables > Actions > New repository secret**에서 아래 6개를 등록합니다.

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | ③ Claude 키 |
| `NAVER_CLIENT_ID` | ① Client ID |
| `NAVER_CLIENT_SECRET` | ① Client Secret |
| `ASSEMBLY_API_KEY` | ② 국회 인증키 |
| `CALENDAR_ICS_URLS` | ④ iCal 비밀 주소 |
| `DASHBOARD_PASSWORD` | 보고서 비밀번호 (직접 정하기, 길게) |

## 4. 웹페이지 켜기

1. **Settings > Pages** → Source: **Deploy from a branch** → Branch: `main`, 폴더: `/docs` → Save
2. **Actions** 탭 → (처음이면 활성화 버튼 클릭) → **AI 비서실 보고** → **Run workflow**
3. 2~5분 뒤 `https://<내 GitHub 아이디>.github.io/ai-secretary/` 접속 → 비밀번호 입력
4. 휴대폰에서 열고 **홈 화면에 추가**하면 앱처럼 쓸 수 있습니다.

---

## 운영

- **감시 대상·키워드 수정**: 저장소에서 `config.yaml` 열기 → 연필 아이콘으로 수정 → Commit
  - 2026 지방선거 이후 바뀐 인물(경기도지사, 화성시장, 장관 등)은 이름을 직접 채워 주세요.
- **지금 바로 갱신**: Actions > AI 비서실 보고 > Run workflow (특정 비서만: `sns press`처럼 입력)
- **실패 확인**: 대시보드에 빨간 안내가 뜨면 Actions 탭에서 해당 실행 기록을 열어 보세요.
- **비용 조절**: `config.yaml`의 `claude.model`
  - `claude-opus-5-5`: 품질 최상, 월 약 3~5만 원 예상
  - `claude-haiku-5-5`: 월 약 1~2천 원 예상, 판단력은 다소 낮음
  - (하루 3회 실행 기준 대략치. 실제 사용량은 console.anthropic.com에서 확인)

## 한계

- 페이스북·인스타그램은 외부 수집이 막혀 있어, **언론이 인용한 SNS 발언**과 네이버 블로그로 대신합니다.
- 커뮤니티 사이트가 해외 서버(GitHub) 접속을 막으면 그 사이트만 건너뜁니다.
- 국회 법안 요약은 법안명 기준이라, 세부 내용은 링크(의안정보시스템)에서 확인하세요.
