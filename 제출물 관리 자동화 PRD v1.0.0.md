---
aliases:
PROJ:
  - "[[제출물 관리 자동화]]"
AREA:
DATE: 2026-02-15
ORG:
RELATE:
---


---

# 📘 최종 PRD (Baseline 1.0)

## 제출물 관리대장 자동화 시스템

### Hybrid 분류 + Phase 기반 배치 + Local Python UI

---

# 1. 목적

본 시스템은 다음을 자동화한다:

1. `source_root`에 유입된 파일 탐색
    
2. 파일명을 기반으로 단계(Phase) 자동 판단
    
    - 1차: Rule Engine
        
    - 2차: AI 보조
        
3. 해당 단계 폴더로 파일 복사
    
4. 분류 실패 시 `project_root`에 안전 배치
    
5. 제출물 관리대장 자동 업데이트
    
6. 운영 설정은 로컬 Python UI에서 수정 가능
    

---

# 2. 시스템 구조

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

---

# 3. 데이터 계층 분리

## 3.1 Knowledge Layer (읽기 전용)

파일:

- `문서목록.json`
    

포함 내용:

- phase 목록
    
- artifact.abbr
    
- artifact.full_name
    

특징:

- 도구 내 편집 기능 없음
    
- 사용자 직접 수정
    
- 실행 시 로드
    

---

## 3.2 Runtime Config Layer (UI 편집 가능)

파일:

- `ledger.config.yaml`
    

포함 내용:

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

특징:

- 최초 실행 시 파일에서 로드
    
- 로컬 Python UI에서 수정 가능
    
- 저장 시 파일 반영
    
- 유효성 검증 후 저장
    

---

# 4. 경로 해석 규칙

- 모든 상대경로는 `project_root` 기준으로 resolve
    
- CWD 기준 해석 금지
    
- 실행 위치와 무관한 동일 동작 보장
    

---

# 5. 분류 구조 (Hybrid)

## 5.1 전체 흐름

```
파일 탐색
    ↓
Rule Engine
    ↓ 성공 → Phase 배치
    ↓ 실패
AI 분류
    ↓ 성공 → Phase 배치
    ↓ 실패
Fallback → project_root 배치
```

---

# 6. Rule Engine 상세 규칙

## 6.1 기준 데이터

`문서목록.json`의:

- abbr
    
- full_name
    

---

## 6.2 abbr 규칙

- 정확 매치
    
- 대소문자 무시
    
- 토큰 단위 비교
    
- 우선순위 1
    

confidence = 1.0

---

## 6.3 full_name 규칙

- 공백 기준 단어 분리
    
- 파일명에 포함된 단어 수 계산
    
- 전체 단어의 50% 이상 매치 시 성공  
    (비율은 UI에서 조정 가능)
    

confidence:

- ≥70% → 0.8
    
- 50~69% → 0.6
    
- <50% → 실패
    

---

## 6.4 충돌 처리

- 가장 높은 매치 비율 선택
    
- 동일 비율 발생 시 AI 호출
    

---

# 7. AI 분류

호출 조건:

- Rule 매칭 실패
    
- 다중 ambiguous
    
- confidence < threshold
    

AI 입력:

- 파일명
    
- 문서목록.json
    

AI 출력:

- artifact_abbr
    
- phase
    
- ai_confidence
    

---

# 8. 파일 배치 규칙

## 8.1 정상 분류

```
target_path =
project_root /
phase_folders[phase] /
original_filename
```

## 8.2 분류 실패 (Fallback)

```
target_path =
project_root /
original_filename
```

- status = Filed
    
- error_message 기록
    

---

## 8.3 파일명 정책

- 원본 파일명 유지
    
- 확장자 유지 (.pdf / .zip)
    
- 덮어쓰기 금지
    
- 중복 시 suffix 증가 (_1, _2 ...)
    

---

# 9. 상태 모델

```
Ready
   ↓
Rule-Classified
   ↓
Filed

Ready
   ↓
AI-Classified
   ↓
Filed

Ready
   ↓
Fallback
   ↓
Filed

Error (시스템 오류 시에만)
```

---

# 10. 관리대장 컬럼

|컬럼|설명|
|---|---|
|original_filename|원본 파일명|
|phase|최종 단계|
|artifact_abbr|최종 판단|
|classification_method|Rule-ABBR / Rule-FULL / AI / Fallback|
|ai_confidence|AI 사용 시|
|result_path|최종 저장 경로|
|status|Ready / Filed / Error|
|error_message|오류 사유|

---

# 11. UI 요구사항 (Local Python GUI)

## 11.1 제공 기능

- project_root 설정
    
- source_root 설정
    
- phase_folders 설정
    
- full_name 매치 비율 설정
    
- AI threshold 설정
    
- Fallback 사용 여부 설정
    
- 중복 정책 설정
    
- 설정 저장 기능
    

## 11.2 제공하지 않는 기능

- 문서목록.json 편집 ❌
    
- Knowledge 데이터 수정 ❌
    

---

# 12. 실행 전 검증

실행 전 다음을 확인:

- config 파싱 성공
    
- Knowledge 파싱 성공
    
- phase_folders 키 = 문서목록 phase 일치
    
- 경로 존재 및 접근 가능
    
- threshold 값 범위 유효
    

실패 시 실행 차단.

---

# 13. 로그 정책

로그에 기록:

- 실행 시각
    
- config 버전/경로
    
- Knowledge 파일 경로
    
- 분류 방식
    
- 매칭 근거
    
- 최종 경로
    
- fallback 여부
    

---

# 14. Acceptance Criteria

1. abbr 포함 파일은 AI 없이 배치된다.
    
2. full_name 50% 이상 포함 파일은 Rule 처리된다.
    
3. ambiguous 케이스만 AI 호출된다.
    
4. 분류 실패 시 project_root 배치된다.
    
5. 파일명은 변경되지 않는다.
    
6. 설정은 UI에서 변경 후 파일에 저장된다.
    
7. Knowledge 파일 수정 시 재실행으로 반영된다.
    
8. 실행 위치와 무관하게 동일 결과가 나온다.
    

---

# 15. 설계 특성 요약

|항목|상태|
|---|---|
|구조 안정성|확보|
|설정 확장성|높음|
|AI 의존도|보조적|
|운영 안정성|Fallback 보장|
|감사 추적성|classification 기록|
|유지보수성|외부 파일 기반|

---

# 최종 결론

본 시스템은:

- Deterministic Rule 기반
    
- AI 보조 구조
    
- 외부 지식/설정 분리
    
- 로컬 Python UI 제공
    
- 안전한 폴백 보장
    
- 하드코딩 배제
    

의 구조를 가진다.
