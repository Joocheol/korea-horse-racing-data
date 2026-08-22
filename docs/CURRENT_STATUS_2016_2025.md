# 2016-2025 최종 데이터셋 상태

*최종 정리: 2026-08-23*

이 문서는 2016-2025년 KRA 공개 API 수집, 검증, 통합 연구용 데이터셋, Dropbox 보존 상태를 한 곳에 정리한 **단일 최종 상태 문서**다.

## 1. 수집 범위와 완료 판정

대상 API는 `API28_1`, `API29_1`, `API30_1`, `API179_1`, `API26_2`, `API227`, `API4_3`, `API5`이다.
서울·제주·부경, 2016-2025년 10개년을 대상으로 총 8,123개 논리 수집 단위를 감사했다.

| 구간 | 논리 단위 | 상태 |
| --- | ---: | --- |
| 2016-2019, 2022-2025 | 5,210 | complete, 오류 0 |
| 2020-2021 | 2,913 | complete, 오류 0 |
| 전체 | 8,123 | complete, 오류 0 |

2016-2019·2022-2025는 source run `32544887677`, archive run `32553067249`에서 검증했고,
2020-2021은 source run `32340684155`, artifact `9396629882`, archive run `32559614706`을 사용했다.
세부 보존 증거는 `backfill-audit-2016-2025.json`, `pilot-audit-2020-2021.json`에 남아 있다.

## 2. 2020-2021 의미 감사

세부 근거는 `SEMANTIC_AUDIT_2020_2021.md`에 유지한다.

- `race_record`, `entries`, `results`: 각 41,749 rows
- unique race IDs: 3,659
- 핵심 3개 테이블 간 누락 race ID: 0
- triple이 기준 경주보다 1,276경주 적은 것은 수집 실패가 아니라 해당 경주의 삼복·삼쌍 미판매와 대응
- sales가 없는 50경주는 ledger 완전성 검사를 통과했으므로 source-level coverage gap으로 분류
- 원천 API가 제공하지 않은 값은 0으로 대체하지 않고 결측으로 유지

### normalized/staged 계층 감사

`normalized`는 코드 내부 `staged/`와 같은 논리 계층이며 source item을 JSONL 행으로 구조화한 archival staging으로 확정했다. 의미·자료형 통일은 `research`에서 수행한다.

실제 artifact 감사 결과:

- 2020-2021 artifact `9396629882`: staged 2,913개, 총 4,656,969행, 파일 내부 완전 중복 0
- legacy API227 달력 전수 방식 때문에 빈 staged 파일 1,797개가 존재하나 현재 운영 planner에서는 발생하지 않음
- 2025 artifact `9468442238`: staged 654개, 총 3,280,645행, 빈 파일 0, 파일 내부 완전 중복 0
- API29 QNL과 API5 복승 교차검증: 2020-2021 222,490행 및 2025 123,078행 모두 키 누락 0, 배당 불일치 0
- API5는 validation evidence로 raw/normalized에 유지하되 canonical `research/odds`에는 포함하지 않음

재현 가능한 감사 코드와 전체 판정은 `docs/NORMALIZED_LAYER_AUDIT.md` 및 `src/kra_data/normalized_audit.py`에 유지한다.

## 3. 통합 연구용 데이터셋

공통 키는 `race_id = YYYYMMDD-meet-rcNo`이다. `race_record`를 연구용 race universe로 사용한다.

| 테이블/항목 | 행·경주 수 |
| --- | ---: |
| races | 24,436 |
| race_record rows | 261,354 |
| entries | 261,392 |
| results | 261,354 |
| sales | 163,844 |
| odds | 29,192,211 |
| non-race odds excluded | 526,192 |
| coverage | 24,436 |

산출 파일은 `races.jsonl.gz`, `entries.jsonl.gz`, `results.jsonl.gz`, `sales.jsonl.gz`, `odds.jsonl.gz`, `coverage.jsonl.gz`, `manifest.json`, `SHA256SUMS`이다.
통합 빌더는 `src/kra_data/research.py`에 있다.

검증 결과:

- 2016-2025 10개 연도 모두 존재
- `race_id` 24,436개 unique, 중복 0
- `races`와 `coverage` 행 수 일치
- 비경주·예비·취소·시험성 odds 526,192행은 raw에는 보존하되 연구 universe에서는 제외

### coverage 요약

| 항목 | 경주 수 |
| --- | ---: |
| sales 전체 미제공 | 145 |
| 삼복·삼쌍 매출 모두 미제공 | 1,394 |
| sales WIN / PLC / QNL | 각 24,291 |
| sales EXA / QPL / TLA | 각 23,042 |
| sales TRI | 21,845 |
| odds WIN / QNL | 각 24,420 |
| odds PLC | 24,403 |
| odds EXA / QPL | 각 23,144 |
| odds TLA | 23,160 |
| odds TRI | 21,950 |

## 4. canonical Dropbox

이 프로젝트의 Dropbox 정본은 **GitHub Actions repository secrets**의
`DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`이 가리키는 기존 Dropbox 앱 계정이다.
다른 Dropbox 연결이나 외부 커넥터 계정은 보존 완료 판정에 사용하지 않는다.

canonical 사용자 표시 경로는 `/앱/kra-data/`이며 다음 구조를 사용한다.

- `/앱/kra-data/raw/`
- `/앱/kra-data/normalized/`
- `/앱/kra-data/manifests/`
- `/앱/kra-data/quarantine/`
- `/앱/kra-data/docs/`
- `/앱/kra-data/research/2016-2025/`

Dropbox 보존 성공 여부는 canonical 앱 계정에 대한 **GitHub Actions Dropbox API 성공 응답과 evidence**로 판정한다.
credentials 자체는 GitHub Secrets에만 보관한다.

## 5. 최종 연구 bundle 보존 증거

GitHub Actions run `32595439823`의 `build-and-archive` job은 전체 `success`였다.

- research artifact: `kra-research-2016-2025`, ID `9481498381`, 320,932,784 bytes
- Dropbox evidence artifact: `kra-research-dropbox-evidence`, ID `9481506837`
- Dropbox destination: `/앱/kra-data/research/2016-2025/`

Dropbox API 성공 응답 기준 파일:

| 파일 | bytes |
| --- | ---: |
| `SHA256SUMS` | 572 |
| `coverage.jsonl.gz` | 125,355 |
| `entries.jsonl.gz` | 32,692,664 |
| `manifest.json` | 411 |
| `odds.jsonl.gz` | 261,365,204 |
| `races.jsonl.gz` | 492,943 |
| `results.jsonl.gz` | 22,847,349 |
| `sales.jsonl.gz` | 3,407,302 |

## 6. 최종 판정과 남은 품질 점검

**2016-2025 KRA 공개 API 수집·통합·Dropbox 보존은 완료 상태다.**
재수집이나 과거 일회성 archive workflow를 운영 단계에서 반복할 필요는 없다.

남은 데이터 품질 점검은 연구 단계에서 수행한다.

1. `entries`가 `race_record/results`보다 38행 많은 원인 확인
2. sales/odds coverage 이상치 목록 확정
3. 기존 HTML 기반 데이터와 새 API 데이터의 경주 universe 및 연구결과 비교
