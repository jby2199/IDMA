# PRD — 제출물 관리대장 자동화 시스템 (IDMA)

## 1. 개요

### 1.1 배경
Hybrid 분류(Rule Engine 우선 + AI 보조) 구조와 Phase 기반 배치, 로컬 Python UI로 구성된 제출물 관리대장 자동화 시스템이다. `source_root`에 유입된 파일을 파일명 기반으로 단계(Phase)를 판단해 해당 Phase 폴더로 옮기고, 분류 실패 시 `project_root`에 안전하게 배치하며, 그 결과를 제출물 관리대장(xlsx)에 자동 기록한다.

### 1.2 목적
사용자가 매번 파일명을 보고 수작업으로 Phase를 판단해 폴더에 옮기고 관리대장에 기입하던 작업을, Rule 우선·AI 보조 분류로 자동화하여 수작업 부담과 오분류·누락 위험을 줄인다.

### 1.3 목표
- `source_root`에 유입된 파일을 탐색해 abbr/full_name 매칭 기반 Rule Engine으로 1차 분류한다.
- Rule 매칭 실패·모호 시 AI 보조 분류를 호출해 Phase를 판정한다.
- 분류 성공 파일은 해당 Phase 폴더로, 실패 파일은 `project_root`에 안전 배치(Fallback)한다.
- 분류 결과를 제출물 관리대장에 자동 기록한다.
- 운영 설정(경로·threshold 등)을 로컬 Python UI에서 수정할 수 있다.

---

## 2. 사용자 및 환경

| 항목 | 내용 |
|------|------|
| 대상 사용자 | 프로젝트 제출물 접수·관리 담당자(비개발자 실무자 포함) |
| 운영체제 | 로컬 PC(Windows). Python 실행 환경 필요 |
| 배포 형태 | 로컬 Python 애플리케이션(CLI 실행 + 로컬 Python GUI 설정 도구) |
| 데이터 계층 | Knowledge Layer(읽기 전용, `문서목록.json`) + Runtime Config Layer(UI 편집 가능, `ledger.config.yaml`) 분리 |
| 경로 해석 | 모든 상대경로는 `project_root` 기준으로 resolve. 실행 위치(CWD)와 무관하게 동일 결과를 보장한다. |

---

## 3. 사용자 스토리

[PRD-U001] 파일 자동 분류·배치
사용자는 `source_root`에 파일을 두면, 시스템이 파일명을 분석해 올바른 Phase 폴더로 자동 이동시켜주길 원한다.

[PRD-U002] 분류 실패 시 안전 폴백
사용자는 시스템이 분류에 실패한 파일을 잃어버리지 않고 `project_root`에 안전하게 남겨, 나중에 직접 확인할 수 있길 원한다.

[PRD-U003] 관리대장 자동 기록
사용자는 파일이 어떻게 분류·배치됐는지(방식·근거·경로·상태)를 매번 수기로 적지 않고, 관리대장에 자동으로 기록되길 원한다.

[PRD-U004] 운영 설정 UI 편집
사용자는 코드나 설정 파일을 직접 열어 고치지 않고, 로컬 Python UI에서 경로·임계값 등 운영 설정을 바꾸고 저장할 수 있길 원한다.

[PRD-U005] 지식 데이터와 설정의 분리
사용자는 `문서목록.json`(Phase·약어·정식명 목록)은 도구가 함부로 고치지 못하게 하고, 자신이 직접 관리하며 재실행 시 최신 내용이 반영되길 원한다.

[PRD-A001] 인수기준 — abbr 매치 시 AI 미사용
파일명에 약어(abbr)가 포함된 파일은 AI 호출 없이 Rule만으로 배치된다.

[PRD-A002] 인수기준 — full_name 매치 기준
정식명(full_name)의 50% 이상 단어가 파일명에 포함된 파일은 Rule로 처리된다(비율은 설정으로 조정 가능).

[PRD-A003] 인수기준 — 모호 케이스만 AI 호출
Rule로 판정할 수 없는(모호하거나 매칭 실패한) 케이스에서만 AI가 호출된다.

[PRD-A004] 인수기준 — 분류 실패 시 폴백 배치
분류에 실패한 파일은 `project_root`에 배치되고 상태·오류 사유가 기록된다.

[PRD-A005] 인수기준 — 파일명 불변
어떤 경로로 배치되든 원본 파일명은 변경되지 않는다(확장자 유지, 덮어쓰기 금지, 중복 시 suffix 증가).

[PRD-A006] 인수기준 — 설정 영속화
설정은 UI에서 변경 후 파일(`ledger.config.yaml`)에 저장된다.

[PRD-A007] 인수기준 — 지식 데이터 재로드
`문서목록.json` 수정 시 별도 반영 절차 없이 재실행만으로 최신 내용이 반영된다.

[PRD-A008] 인수기준 — 실행 위치 독립성
실행 위치(현재 작업 디렉토리)와 무관하게 동일한 결과가 나온다.

---

## 4. 기능 요구사항

### 4.1 데이터 계층

[PRD-F001] Knowledge Layer 분리
시스템은 `문서목록.json`을 읽기 전용 Knowledge Layer로 취급한다. Phase 목록, `artifact.abbr`(약어), `artifact.full_name`(정식명)을 포함하며, 도구는 이 파일을 편집하는 기능을 제공하지 않는다. 사용자가 직접 수정하고, 시스템은 실행 시점에 이 파일을 로드한다.

[PRD-F002] Runtime Config Layer 분리
시스템은 `ledger.config.yaml`을 UI로 편집 가능한 Runtime Config Layer로 취급한다. 포함 항목: `project_root`, `workbook.path`, `roots.source_root`, `roots.phase_folders`, `rule.full_name_min_ratio`, `ai.confidence_threshold`, `fallback.enabled`, `duplicate.suffix_start`. 최초 실행 시 파일에서 로드하고, UI에서 수정 후 저장 시 유효성 검증을 거쳐 파일에 반영한다.

[PRD-F003] 경로 해석 규칙
모든 상대경로는 `project_root` 기준으로 resolve한다. 현재 작업 디렉토리(CWD) 기준 해석은 금지하며, 실행 위치와 무관하게 동일한 동작을 보장한다.

### 4.2 분류 (Hybrid: Rule + AI)

[PRD-F004] 전체 분류 흐름
시스템은 파일 탐색 → Rule Engine 분류 → (실패 시) AI 분류 → (실패 시) Fallback 배치 순서로 처리한다.

[PRD-F005] Rule Engine — abbr 매칭
시스템은 `문서목록.json`의 `abbr` 값과 파일명을 정확 매치(대소문자 무시, 토큰 단위 비교)로 비교한다. 매치 시 confidence는 1.0이며 우선순위 1로 처리한다.

[PRD-F006] Rule Engine — full_name 매칭
시스템은 `문서목록.json`의 `full_name`을 공백 기준으로 단어 분리하고, 파일명에 포함된 단어 수를 계산한다. 전체 단어의 `rule.full_name_min_ratio`(기본 50%) 이상 매치 시 성공으로 판정한다. confidence는 매치 비율 70% 이상이면 0.8, 50~69%이면 0.6, 50% 미만이면 실패로 처리한다.

[PRD-F007] Rule Engine — 충돌 처리
복수 후보가 매치되면 가장 높은 매치 비율의 후보를 선택한다. 매치 비율이 동일한 후보가 여럿이면 AI를 호출한다.

[PRD-F008] AI 분류 호출 조건
시스템은 다음 중 하나에 해당하면 AI 분류를 호출한다: Rule 매칭 실패, 다중 후보 간 모호(ambiguous) 상태, confidence가 `ai.confidence_threshold` 미만.

[PRD-F009] AI 분류 입출력
AI 분류 입력은 파일명과 `문서목록.json` 내용이다. AI 분류 출력은 `artifact_abbr`, `phase`, `ai_confidence`다.

### 4.3 파일 배치

[PRD-F010] 정상 분류 배치 경로
분류에 성공한 파일의 배치 경로는 `project_root / phase_folders[phase] / 원본파일명`이다.

[PRD-F011] 분류 실패 시 Fallback 배치 경로
분류에 실패한 파일의 배치 경로는 `project_root / 원본파일명`이며, 상태는 `Filed`로, 오류 사유는 `error_message`에 기록한다.

[PRD-F012] 파일명 보존 정책
파일 배치 시 원본 파일명과 확장자(`.pdf`/`.zip` 등)를 그대로 유지한다. 기존 파일 덮어쓰기는 금지하며, 동일 파일명 충돌 시 suffix(`_1`, `_2`, ...)를 증가시켜 저장한다.

### 4.4 상태 모델

[PRD-F013] 파일 상태 전이
파일 상태는 다음 세 경로 중 하나로 전이한다: (1) `Ready` → `Rule-Classified` → `Filed`, (2) `Ready` → `AI-Classified` → `Filed`, (3) `Ready` → `Fallback` → `Filed`. `Error` 상태는 시스템 오류가 발생했을 때만 진입한다.

### 4.5 관리대장 갱신

[PRD-F014] 관리대장 컬럼 구성
시스템은 제출물 관리대장에 다음 컬럼을 기록한다: `original_filename`(원본 파일명), `phase`(최종 단계), `artifact_abbr`(최종 판단 약어), `classification_method`(Rule-ABBR/Rule-FULL/AI/Fallback), `ai_confidence`(AI 사용 시), `result_path`(최종 저장 경로), `status`(Ready/Filed/Error), `error_message`(오류 사유).

### 4.6 로컬 Python UI

[PRD-F015] UI 제공 기능
로컬 Python UI는 다음 설정을 제공한다: `project_root` 설정, `source_root` 설정, `phase_folders` 설정, full_name 매치 비율 설정, AI threshold 설정, Fallback 사용 여부 설정, 중복 정책 설정, 설정 저장.

[PRD-F016] UI 비제공 기능
로컬 Python UI는 `문서목록.json` 편집 기능과 Knowledge 데이터 수정 기능을 제공하지 않는다.

### 4.7 실행 전 검증

[PRD-F017] 실행 전 사전 검증
시스템은 실행 전 다음을 확인한다: config 파싱 성공, Knowledge(`문서목록.json`) 파싱 성공, `phase_folders` 키와 `문서목록.json`의 phase 값 일치, 관련 경로의 존재 및 접근 가능 여부, threshold 값의 범위 유효성. 하나라도 실패하면 실행을 차단한다.

### 4.8 로그

[PRD-F018] 로그 기록 항목
시스템은 실행마다 다음을 로그에 기록한다: 실행 시각, config 버전/경로, Knowledge 파일 경로, 분류 방식, 매칭 근거, 최종 경로, fallback 여부.

---

## 5. 비기능 요구사항

[PRD-N001] 구조 안정성
경로 해석·데이터 계층 분리 규칙을 통해 구조 안정성을 확보한다(4.1절, 4.3절).

[PRD-N002] 설정 확장성
Runtime Config Layer(`ledger.config.yaml`)를 통해 운영 설정을 코드 변경 없이 확장·조정할 수 있어야 한다.

[PRD-N003] AI 의존도 최소화
AI는 Rule Engine이 판정하지 못하는 경우에만 보조적으로 호출되며, 분류의 주된 판단 수단이 아니다.

[PRD-N004] 운영 안정성 (Fallback 보장)
어떤 분류 실패 상황에서도 파일은 유실되지 않고 `project_root`에 안전하게 배치되어야 한다.

[PRD-N005] 감사 추적성
모든 분류 결과는 classification_method와 매칭 근거를 포함해 관리대장·로그에 기록되어야 한다(4.5절, 4.8절).

[PRD-N006] 유지보수성 (외부 파일 기반)
분류 기준(Knowledge)과 운영 설정(Config)은 코드에 하드코딩하지 않고 외부 파일로 분리해 유지보수한다.

---

## 6. 범위 외

- `문서목록.json`(Knowledge Layer) 편집 기능 — 사용자가 직접 관리하며 도구는 읽기 전용으로만 사용한다(4.6절 UI 비제공 기능).
- CWD(현재 작업 디렉토리) 기준 경로 해석 — 모든 경로는 `project_root` 기준으로만 해석한다(4.1절).
- 이미지/도형·시각 요소 기반 분류 — 파일명 기반 분류만 지원한다.
- 분류 실패 파일의 자동 재시도·자동 재분류 — 실패 시 Fallback 배치 후 사용자 확인을 전제로 한다.

---

## 7. 부록 — 원본 설계 스케치

아래는 초안 작성 시점의 시스템 구조·설정 스키마 스케치이며, 4장 기능 요구사항의 근거 자료다.

### 7.1 시스템 흐름
```
ledger.config.yaml      ← Runtime Config (UI 편집 가능)
문서목록.json           ← Knowledge (읽기 전용)
제출물관리대장.xlsx
        ↓
Rule Engine
        ↓
AI Classifier (보조)
        ↓
Phase Resolver
        ↓
File Mover
        ↓
Excel Updater + Logger
```

### 7.2 Runtime Config 스키마
```yaml
project_root:
workbook.path:
roots.source_root:
roots.phase_folders:

rule.full_name_min_ratio:
ai.confidence_threshold:
fallback.enabled:
duplicate.suffix_start:
```
