# AI 비서실 — 설치 안내

15분마다 비서들이 새 소식을 확인하고, 내가 원할 때 웹페이지에서 봅니다.
보고서와 인간관계 명단은 비밀번호로 암호화되므로 주소가 알려져도 내용은 보이지 않습니다.

| 비서 | 하는 일 | 데이터 | 확인 주기 |
|---|---|---|---|
| SNS | 정치인 SNS 발언 중 쟁점만 | 네이버 뉴스(SNS 인용 기사) + 네이버 블로그 | 15분 |
| 정보 | 텔레그램 단체방의 중요한 글, 반응 좋은 글 | 텔레그램 | 30분 |
| 언론 | 전국 지자체 '최초'·우수 정책 | 네이버 뉴스 | 15분 |
| 정책 | 화성시 적용 정책안 | 언론 비서 결과 | 주 1회 |
| 국회·의회 | 상임위 통과 이상 법안 + 도·시의회 | 열린국회정보 + 네이버 뉴스 | 6시간 |
| 여론·민원 | 진영별 커뮤니티 여론 + 화성 맘카페 민원 | 커뮤니티 인기글 + 네이버 카페 | 1시간 |
| 인간관계 | 상 1주 · 중 1달 · 하 3개월 연락 알림 | 내가 입력한 명단 | 화면에서 바로 계산 |

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

---

## 2. GitHub에 올리기 — 무료

1. https://github.com 가입 → 오른쪽 위 **+ > New repository**
   - 이름: `ai-secretary` / **Public** 선택 → Create
2. **uploading an existing file** 클릭 → `ai-secretary` 폴더 **안의 내용 전부**를 끌어다 놓기 → Commit
   - `.github` 폴더가 빠지기 쉽습니다. 저장소에 `.github/workflows/run.yml`이 없으면
     **+ > Create new file**에서 파일 이름에 `.github/workflows/run.yml`을 입력하고 내용을 붙여 넣으세요.

## 3. 비밀값 등록

저장소 **Settings > Secrets and variables > Actions > New repository secret**

| 이름 | 값 |
|---|---|
| `ANTHROPIC_API_KEY` | ③ Claude 키 |
| `NAVER_CLIENT_ID` | ① Client ID |
| `NAVER_CLIENT_SECRET` | ① Client Secret |
| `ASSEMBLY_API_KEY` | ② 국회 인증키 |
| `DASHBOARD_PASSWORD` | 보고서 비밀번호 (직접 정하기, 길게) |

## 4. 웹페이지 켜기

1. **Settings > Pages** → Source: **GitHub Actions** 선택
2. 맨 위 **Actions** 탭 → **AI 비서실 보고** → **Run workflow**
3. 완료 후 `https://<내 GitHub 아이디>.github.io/ai-secretary/` 접속 → 비밀번호 입력
4. 휴대폰에서 열고 **홈 화면에 추가**하면 앱처럼 쓸 수 있습니다.

---

## 5. 정보 비서 연결 (텔레그램)

단체방에 봇을 넣지 않고 **내 계정으로 읽기만** 합니다. 다른 사람에게 보이지 않고, 반응 수도 읽을 수 있습니다.

1. https://my.telegram.org 로그인 → **API development tools** → 앱 생성 → `api_id`, `api_hash` 복사
2. PC에 Python 설치(https://www.python.org, 설치 시 **Add python.exe to PATH** 체크)
3. 이 프로그램 폴더에서 터미널을 열고 아래 실행 → 전화번호와 인증코드 입력

   ```bash
   pip install telethon
   ```

   ```bash
   python tools/telegram_login.py
   ```

4. 화면에 나온 값을 비밀값으로 등록

| 이름 | 값 |
|---|---|
| `TELEGRAM_API_ID` | api_id |
| `TELEGRAM_API_HASH` | api_hash |
| `TELEGRAM_SESSION` | 출력된 긴 문자열 |
| `TELEGRAM_CHATS` | 방 이름을 쉼표로 연결 (예: `방이름1,방이름2`) |

**주의**
- `TELEGRAM_SESSION`은 내 계정 로그인과 같습니다. 비밀값 외에는 어디에도 저장·공유하지 마세요.
  유출이 의심되면 텔레그램 **설정 > 기기**에서 해당 세션을 종료하세요.
- 텔레그램이 해외 서버 접속을 이상하게 보면 세션을 끊을 수 있습니다. 그 경우 3번부터 다시 하면 됩니다.
- 단체방 메시지는 요약을 위해 Claude API로 전달됩니다. 대화 내용이 민감한 방은 넣지 마세요.

## 6. 인간관계 비서

대시보드 **인간관계** 탭에서 이름과 등급을 입력합니다. 첫 연락일은 한꺼번에 몰리지 않게 자동으로 나눕니다. 연락 후 **연락함**을 누르세요.

휴대폰과 PC의 명단을 같게 하려면 토큰이 필요합니다. 한 기기만 쓰면 건너뛰어도 됩니다.
1. GitHub **Settings > Developer settings > Personal access tokens > Fine-grained tokens > Generate new token**
2. Repository access: **Only select repositories** → `ai-secretary`
3. Permissions: **Contents** → **Read and write** → 생성 후 토큰 복사
4. 각 기기의 인간관계 탭 **기기 간 동기화**에 붙여 넣고 저장

---

## 운영

- **감시 대상 수정**: 저장소에서 `config.yaml` 열기 → 연필 아이콘으로 수정 → Commit
- **주기 변경**: `config.yaml`의 `intervals`
- **지금 바로 갱신**: Actions > AI 비서실 보고 > Run workflow (특정 비서만: `sns press`처럼 입력)
- **실패 확인**: 대시보드에 빨간 안내가 뜨면 Actions 탭의 해당 실행 기록 확인
- **비용**: 새 글이 있을 때만 Claude를 호출합니다. 실제 사용량은 console.anthropic.com에서 확인하세요.

## 한계

- **완전한 실시간은 아닙니다.** 15분 간격이 목표이고, GitHub 사정으로 더 밀릴 수 있습니다.
- GitHub는 저장소에 60일간 활동이 없으면 자동 실행을 멈춥니다. 멈추면 Actions 탭에서 다시 켜거나 `config.yaml`을 한 번 수정하세요.
- 페이스북·인스타그램은 외부 수집이 막혀 있어, **언론이 인용한 SNS 발언**과 네이버 블로그로 대신합니다.
- 커뮤니티 사이트가 해외 서버(GitHub) 접속을 막으면 그 사이트만 건너뜁니다.
- 국회 법안 요약은 법안명 기준이라, 세부 내용은 링크(의안정보시스템)에서 확인하세요.
