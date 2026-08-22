# 수집·검증 워크플로우

*정리 2026-08-23*

이 문서는 KRA 공개 API를 다시 수집하거나 기간을 확장할 때 적용할 운영 규칙이다.
API 사실관계는 `API_FINDINGS.md`, API별 형식·호출량·저장 규칙은 `COLLECTION_FORMATS.md`,
완료된 2016-2025 데이터셋 상태는 `CURRENT_STATUS_2016_2025.md`를 따른다.

## 1. 기본 원칙

1. 장시간 수집은 `workflow_dispatch`로만 시작한다.
2. 원응답 raw를 불변으로 보존한다.
3. 완료한 요청 단위는 재실행 때 건너뛴다.
4. 실행 전에 통과 기준과 호출 예산을 고정한다.
5. 원천 API가 제공하지 않는 값은 0으로 대체하지 않는다.
6. 채팅이나 일시적 로그가 아니라 manifest, ledger, checksum, audit 파일을 증거로 남긴다.

## 2. 수집 순서

### 월 단위 API

`API227`을 제외한 API를 `경마장 × 월 × API × pool` 단위로 계획한다.
서비스별 일일 한도와 재시도 여유를 preflight에서 검사한다.

### API227

`API227`은 모든 달력 날짜를 순회하지 않는다.

1. 요청 기간의 `API4_3` meet-month를 먼저 모두 수집한다.
2. 해당 ledger가 모두 `complete`인지 확인한다.
3. staged `API4_3`에서 `unique(meet, rcDate)`를 만든다.
4. 발견된 실제 경주일에 대해서만 `API227`을 호출한다.
5. `rc_no`는 생략해 해당 경마일 전체를 한 번에 받는다.
6. 실제 요청 수에 안전여유를 적용해 API227 일일 한도를 다시 검사한다.

`API4_3`이 일부만 완료된 상태에서는 API227 날짜를 추정하지 않고 `deferred`로 둔다.

## 3. 저장 계층

| 계층 | 내용 | 규칙 |
| --- | --- | --- |
| `raw` | 페이지별 API 원응답 | 불변, 덮어쓰기 금지 |
| `staged` | 형 변환·표준 열·중복 표시 | raw에서 재생성 가능 |
| research/curated | 검증을 통과한 연구용 자료 | staged에서 재생성 가능 |

canonical Dropbox는 GitHub Actions repository secrets가 가리키는 기존 Dropbox 앱 계정이고,
기본 사용자 표시 경로는 `/앱/kra-data/`이다.

## 4. Ledger와 재개

각 요청 단위에는 최소한 다음을 기록한다.

- 요청 파라미터와 페이지 범위
- API `totalCount`
- raw 수신 행 수와 unique 행 수
- 중복 수
- 오류·재시도 횟수
- raw checksum
- collector SHA와 schema version
- 시작·완료 시각과 상태

상태는 `pending / running / validating / complete / failed`로 제한한다.
검증이 끝나기 전에 `complete`로 바꾸지 않는다.
재실행은 `complete`를 건너뛰고 실패·미완료 요청만 처리한다.

## 5. 재시도와 실패 처리

| 오류 | 처리 |
| --- | --- |
| HTTP 429, 5xx, 일시적 네트워크 오류 | 제한된 지수 backoff + jitter |
| 인증·필수 파라미터 오류 | 즉시 중단 |
| 예상하지 않은 schema 변화 | 즉시 중단 |
| 빈 응답 | 보조 API로 정상 빈 기간인지 확인 |
| 일부 페이지 실패 | 요청 단위 전체를 미완료로 유지 |
| 설명되지 않은 중복 | 실패 처리 |

무제한 반복하지 않는다. 후속 실행은 실패 목록만 재개한다.

## 6. 기술적 완료 기준

- 계획 ledger 완료율 100%
- 비정상 HTTP/API 오류 0
- 설명되지 않은 기본키·페이지 경계 중복 0
- `totalCount = raw 수신 행 수 = 페이지별 행 수 합계`
- API 특성상 중복이 없으면 `totalCount = unique 행 수`
- 필수 열의 예상치 못한 결측 0
- 동일 raw와 동일 코드/schema로 staged 재생성 가능

`totalCount` 일치 하나만으로 완전성을 단정하지 않고 기본키와 unique 수를 별도로 검사한다.

## 7. 의미 검증

가능한 경우 다음을 함께 사용한다.

- `race_record`, entries, results의 race universe 비교
- 출주두수 기반 승식 조합 수 비교
- API5와 API29_1 복승 셀 교차검증
- 매출액·배당과 환급률 정합성
- 실제 개최일과 시험·취소성 기록 분리
- source-level coverage gap의 명시적 flag

2020·2021의 구체적인 예외와 검증 결과는 `SEMANTIC_AUDIT_2020_2021.md`에 보존한다.

## 8. 종료 조건

다음을 모두 만족하면 수집을 완료로 판정한다.

- 대상 ledger 100% complete
- 실패 요청 0
- 기술 감사 통과
- 의미 감사에서 설명되지 않은 중대 불일치 0
- raw → staged → research 재생성 가능
- audit와 checksum 증거 보존

2016-2025 범위는 이미 이 조건을 충족했으며, 그 최종 상태는 `CURRENT_STATUS_2016_2025.md`가 정본이다.
