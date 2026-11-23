# lofo-dev-harness

**Claude Code를 오케스트레이터로**, **Codex를 구현·리뷰 워커로** 두고 소프트웨어를 만들 때 쓰는 공용 개발 하네스입니다.

실제로 운영한 사이드 프로젝트 세 개의 하네스를 합쳤습니다. 프로젝트마다 복사하던 규칙·훅·스킬·스크립트가 서로 갈라지는 문제를 없애는 것이 가장 큰 목표입니다.

> **상태: 뼈대 단계.** 플러그인 설치는 되지만 아직 스킬과 훅이 없습니다. 현재 설계는 [`docs/design.ko.md`](docs/design.ko.md)에 있습니다. [English README](README.md)

## 설치

Claude Code 2.1.275 이상:

```
/plugin install lofo-dev-harness --marketplace jylee9937/lofo-dev-harness
```

이전 버전:

```
/plugin marketplace add jylee9937/lofo-dev-harness
/plugin install lofo-dev-harness@lofo-dev-harness
```

스킬은 `/lofo-dev-harness:<스킬>` 형태로 부릅니다. 예: `/lofo-dev-harness:init`

## 계획

- **Claude Code 플러그인 마켓플레이스.** 스킬·훅·에이전트를 한 곳에서 관리하므로 업데이트가 모든 프로젝트에 반영됩니다.
- **`init` 스킬.** 문서 언어, 운영 모드, 프레임워크, DB, 배포 방식, 통과 검사 명령, 함께 쓸 도구, Codex 모델을 하나씩 묻습니다. 그런 다음 프로젝트에 `AGENTS.md`, `CLAUDE.md`, `docs/`, `.harness/config.json`을 만듭니다. Codex도 같은 `AGENTS.md`를 읽습니다.
- **공통 core 위의 두 모드.**
  - *협업 모드*: 커밋·PR은 요청할 때만 합니다.
  - *자율 모드*: 정해진 시간에 혼자 작업하고, 오너에게 물을 결정을 모아 두고, Codex 보안 관문을 통과한 뒤에만 병합합니다.
- **스택 중립 core + 프리셋.** 첫 프리셋은 Next.js + Supabase + Vercel이고, Firebase·GCP·AWS를 추가할 예정입니다.

## 설정

프로젝트마다 커밋하는 설정 파일 `.harness/config.json` 하나를 모든 스킬·훅·스크립트가 읽습니다. 모델명, 통과 검사 명령, QA 포트, 백엔드 경로 패턴이 여기에 있어서 모델을 바꿀 때는 한 줄만 고치면 됩니다.

- 스키마: [`schemas/harness-config.schema.json`](schemas/harness-config.schema.json)
- 예시: [협업 모드, Next.js + Supabase + Vercel](examples/nextjs-supabase-vercel.config.json), [자율 모드](examples/autonomous.config.json)

로컬 경로처럼 내 컴퓨터에만 해당하는 값은 이 파일에 넣지 않습니다. git에서 제외되는 `.harness/config.local.json`에 둡니다.

## 라이선스

[MIT](LICENSE)
