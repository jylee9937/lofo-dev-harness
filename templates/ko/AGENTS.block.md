# 작업 하네스 (Claude Code + Codex 공용)

Claude의 진입점은 `CLAUDE.md → @AGENTS.md`이고, Codex도 이 파일을 같은 규칙으로 읽는다. 이 블록은 프로젝트의 다른 가이드보다 먼저 적용되며, 상세 정본은 `{{dev_harness_path}}`다.

- 스택: {{framework_name}} · {{db_name}} · {{hosting_name}} · {{pm}}
- 운영 모드: {{mode_name}}

## 시작
- 새 작업은 `main` 최신화 → 작업 브랜치 생성 → 하네스 읽기 순서로 시작한다. Claude Code에서는 `/lofo-dev-harness:start-task <작업 설명>`이 이 절차를 수행한다.
- 작업 전에 `git status --short`, 현재 브랜치, 핸드오프 파일(`{{handoff_path}}`, 있으면)을 확인한다.
- 작업 브랜치에 커밋되지 않은 작업이 남아 있으면 브랜치를 바꾸거나 stash하지 않고 그대로 이어서 한다.
- `main` pull과 새 브랜치 생성은 사용자가 새 작업 시작을 명시했을 때만 한다.

## 읽는 순서
1. `{{dev_harness_path}}`: 역할 분담, 프로세스, 백엔드 협업, 검사, 기록 규칙
2. `.harness/config.json`: 모델, 검사 명령, QA 포트 (모델명은 이 파일에만 있다)
3. `{{handoff_path}}`: 지난 세션이 남긴 시작점 (있으면)
4. `{{flows_dir}}/*.flow.json`: 확정된 화면과 흐름 (화면 작업일 때)

## 역할
{{#codex}}
- **Codex**: 1차 구현, 코드 리뷰, 버그 진단을 먼저 맡는다. 모델과 effort는 `.harness/config.json`의 `models.codex` 값을 매번 명시해서 넘긴다.
- **Claude**: 작업을 나누고, 판단하고, Codex 결과를 검수·통합하고, 설명하고, 기록한다.
- Codex를 쓸 수 없거나 한도에 걸리면 멈추지 않고 Claude가 이어서 한다. 순서: {{fallback_chain}}.
{{/codex}}
{{^codex}}
- 이 프로젝트는 Codex를 쓰지 않는다. Claude가 구현까지 맡는다. 모델 순서: {{fallback_chain}} (어려운 판단은 앞쪽, 기계적인 작업과 문서는 뒤쪽).
{{/codex}}

## 규칙
{{#collab}}
- 커밋·푸시·PR·병합은 사용자가 요청할 때만 한다.
{{/collab}}
{{#autonomous}}
- 자율 모드는 아직 이 버전의 lofo-dev-harness에 없다. 추가되기 전까지는 커밋·푸시·PR·병합을 사용자가 요청할 때만 한다.
{{/autonomous}}
- `main`에 바로 커밋하지 않는다. 항상 브랜치를 먼저 만든다.
- 외부 쓰기, 배포, 호스팅 DB 변경은 사용자 확인 없이 하지 않는다.
- 비밀값과 토큰은 출력하지 않고, 파일이나 커밋에 넣지 않는다.
- 백엔드(권한 규칙, 마이그레이션, 관리자 키, 서버 경계)는 개념과 선택지를 먼저 설명하고 사용자와 함께 정한 뒤 구현한다.
- 보안 관문 대상 변경(인증, 권한, 돈, 비밀값, 개인정보, 업로드, webhook, 권한 마이그레이션)은 `/lofo-dev-harness:security-gate`에서 GO를 받기 전에 병합·배포하지 않는다.
- 결정이 필요하면 추천을 맨 앞에 둔 선택지로 한 번에 하나씩 묻는다.

## 완료 기준
- 검사를 모두 통과한다: `{{gates_chain}}`
- e2e: {{e2e_line}}
- 검증하지 못한 것은 이유와 다음에 돌릴 명령을 남긴다.
- 완료 보고 끝에 사용자가 직접 확인할 방법을 적는다: `{{dev_cmd}}` → 확인할 URL.
