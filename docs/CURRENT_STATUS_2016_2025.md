# 2016-2025 최종 데이터셋 상태

*최종 정리: 2026-08-27*

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

## 2. normalized/staged 계층 감사

`normalized`는 코드 내부 `staged/`와 같은 논리 계층이며 source item을 JSONL 행으로 구조화한 archival staging이다. 의미·자료형 통일은 `research`에서 수행한다.

- 2020-2021 artifact `9396629882`: staged 2,913개, 총 4,656,969행, 파일 내부 완전 중복 0
- legacy API227 달력 전수 방식 때문에 빈 staged 파일 1,797개가 존재하나 현재 운영 planner에서는 발생하지 않음
- production 연도 2016-2019·2022-2025의 normalized 파일 유형은 11종으로 고정
- API29 QNL과 API5 복승 교차검증은 **2016-2025 전 기간에서 키 누락 0, 배당 불일치 0**
- API5는 validation evidence로 raw/normalized에 유지하되 canonical `research/odds`에는 포함하지 않음

재현 가능한 감사 코드와 전체 판정은 `docs/NORMALIZED_LAYER_AUDIT.md` 및 `src/kra_data/normalized_audit.py`에 유지한다.

## 3. 통합 연구용 데이터셋

공통 키는 `race_id = YYYYMMDD-meet-rcNo`이다. `race_record`를 연구용 race universe로 사용한다.

| 테이블/항목 | 행·경주 수 |
| --- | ---: |
| races | 24,436 |
| race_record rows | 261,354 |
| entries | **261,354** |
| results | **261,354** |
| sales | 163,844 |
| odds | **29,196,005** |
| non-race odds excluded | 526,192 |
| coverage | 24,436 |

산출 파일은 `races.jsonl.gz`, `entries.jsonl.gz`, `results.jsonl.gz`, `sales.jsonl.gz`, `odds.jsonl.gz`, `coverage.jsonl.gz`, `manifest.json`, `SHA256SUMS`이다.
통합 빌더는 `src/kra_data/research.py`에 있고, 검증된 공급기관 정정을 canonical에
이관하는 fail-closed 빌더는 `src/kra_data/canonical_update.py`에 있다.

검증 결과:

- 2016-2025 10개 연도 모두 존재
- `race_id` 24,436개 unique, 중복 0
- `races`와 `coverage` 행 수 일치
- `entries` canonical key `(race_id, chulNo, hrNo)` 261,354개 unique, 중복 0
- `entries` key와 `results` 출전마 key가 261,354개로 완전히 일치
- 비경주·예비·취소·시험성 odds 526,192행은 raw에는 보존하되 연구 universe에서는 제외

### entries 38행 초과 문제 — 해결 완료

기존 research bundle의 `entries` 261,392행이 `race_record/results` 261,354행보다 38행 많았던 원인을 API26_2 source까지 추적했다.

| 연도 | source duplicate 초과행 |
| --- | ---: |
| 2016 | 5 |
| 2017 | 18 |
| 2018 | 11 |
| 2019 | 4 |
| 2020-2025 | 0 |
| 합계 | **38** |

38행은 모두 동일 natural key `(rcDate, meet, rcNo, chulNo, hrNo)`가 두 번 나타난 API26_2 source duplicate이며, 확인된 차이는 마주명 표기·대소문자 변형이다. 서로 다른 출전마가 추가된 것이 아니다.

정책은 다음과 같이 확정했다.

- raw/normalized에는 source row를 원형대로 모두 보존
- research에서만 `(race_id, chulNo, hrNo)` 기준으로 1행 유지
- 경로와 source 순서를 결정적으로 정렬한 뒤 첫 source row 유지
- 제거 수와 서로 내용이 다른 duplicate key 수를 manifest에 기록

최종 corrected manifest는 `entries_source_duplicate_rows_removed = 38`, `entries_source_conflicting_duplicate_keys = 38`을 기록한다.

### coverage 감사 — 해결 완료

coverage gap 전수 감사 결과는 `docs/COVERAGE_GAP_AUDIT_2016_2025.md`에 정리했고,
이미 확인한 예외와 최종 판정 순서는 `docs/KNOWN_DATA_EXCEPTIONS.md`에 정리한다.

핵심 판정:

- `sales_missing_all=True`인 **145경주**는 유효 순위가 없는 145경주와 정확히 일치한다. odds 격자가 남아 있어도 시행 경주로 판정하지 않는다.
- 145경주 중 2020–2021은 50경주, 그 밖의 기간은 95경주이며 기본 분석에서 제외한다.
- 2019-11-29 부경 11경주는 당일 전 경주 취소 사례다. 결과·HTML 링크가 없고 API 배당은 전부 `9999.9`다.
- 2025-10-17 제주 8경주 + 부경 8경주, 총 **16경주**는 sales와 TLA/TRI odds는 있으나 WIN/PLC/QNL/EXA/QPL odds가 없다. 2025 source artifact에서도 해당 날짜 `single-all` 및 `double-*` normalized 행이 0임을 확인해 source endpoint gap으로 확정.
- TRI의 2016-06-10 도입 전 **1,210경주** 공백은 구조적 pre-introduction gap.
- 2020-06-19~2021-09-05 사이 **1,276경주**에서 EXA/QPL/TLA/TRI가 모두 없고 WIN/PLC/QNL만 존재하는 패턴은 당시 무고객 경마의 단승·연승·복승 제한 발매와 일치하는 구조적 COVID regime.

따라서 현재 확인된 coverage gap 중 **재수집으로 해결해야 할 race-level collection failure는 발견되지 않았다.**
source anomaly는 결측으로 유지하며 0으로 대체하지 않는다.

### 공급기관 정정 재검산 — 2026-08-27

KRA 회신 후 11개 표적 API 요청을 다시 실행해 원문 응답·SHA-256·요약을 Actions
run `33028591323`, artifact `9629358212`에 보존했다.

| 사례 | 재조회 결과 | 판정 |
| --- | --- | --- |
| 2025-10-17 제주·부경 배당 공백 | 제주 1,562행 + 부경 2,304행 = 3,866행, 16경주·5승식 복구 | 정정 확인 |
| 2019-05-18 제주 6경주 `dusu` | 10행, 출전번호 1–10, `dusu=10` | 정정 확인 |
| 2023-03-17 부경 자리표시자 | 실제 1–8경주 출전표 밖 72행 + 비경주 9–12경주 128행 | 미정정 |

Dropbox에 보존된 기존 HTML backfill 3,866행과 새 API 3,866행을 자연키
`(race_id, pool_code, h1, h2, h3)`와 배당값으로 전수 대조했다. 공통 키 3,866개,
양쪽 고유 키 0개, 배당값 불일치 0건이었다. 이에 따라 HTML backfill을 동일한 API
source로 교체했다. 2019년은 분석용 출전두수를 이미 행 단위로 재계산하므로 분석
결과 변경이 없다. 2023년 72행 제외와 비경주 universe 제외 규칙도 계속 유지한다.

### 배당 상한 예외 — 해결 완료

- `odds == 9999.9`는 정상 유효 조합에서 표시상한으로 보존한다.
- `odds > 9999.9`는 2018-07-01 하루, 15경주·18개 승식판·3,555행에서만 존재한다.
- 초과값 범위는 10,000.3–235,070.0이며 실제 게시된 점값으로 보존한다.
- 이후 bundle에서 다른 날짜의 초과값이 나오면 새 이상으로 경고한다.

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

credentials 자체는 GitHub Secrets에만 보관한다.

## 5. API-only 최종 연구 bundle 보존 증거

최종 권위(authoritative) rebuild·publish는 GitHub Actions run **`33032964636`**이며
`build-validate-publish` job 전체가 `success`였다. 이전 run `32603481704`의 API-only
bundle은 이 run으로 대체됐다.

run 내부 검증에서 다음을 직접 확인했다.

- races: 24,436
- race_record rows: 261,354
- entries: **261,354**
- entries source duplicates removed: **38**
- entries conflicting duplicate keys: **38**
- results: 261,354
- sales: 163,844
- base odds: 29,192,211
- 출전표 밖 API odds 제거: 72
- 2025-10-17 정정 API odds 추가: 3,866
- 최종 API-only odds: **29,196,005**
- HTML source rows: **0**
- non-race odds excluded: 526,192
- coverage: 24,436
- 2025-10-17 coverage 갱신: 16경주
- canonical entry key 261,354개 unique, 중복 0

Actions 보존물:

- final canonical artifact: `kra-canonical-api-only-2016-2025`, ID **`9631057131`**,
  digest `sha256:19094bbba127d417e5c464561f46c76f7c98ef0422e940400f047710fd76df5f`
- migration evidence: `kra-canonical-api-migration-evidence`, ID **`9631057426`**,
  digest `sha256:7364b7a4b9cd31dd7d75ec0e46746941cbd9559891a08f50a9be010337c15f10`
- Dropbox evidence: `kra-api-canonical-dropbox-evidence`, ID **`9631069376`**,
  digest `sha256:1a4c4fc1b2b59f842db88abd86ade048df6c4e76deb24af28b9d0e1bd149711f`

Dropbox publish는 파일별 직접 덮어쓰기가 아니라 다음 순서로 수행했다.

1. `/앱/kra-data/research/.staging-2016-2025-33032964636/`에 전체 bundle 업로드
2. staging의 8개 파일 이름·크기·Dropbox content hash를 로컬 산출물과 대조
3. 기존 canonical 폴더를 backup으로 이동
4. staging 폴더를 `/앱/kra-data/research/2016-2025/`로 승격
5. 승격 성공 후 backup 삭제

보존 evidence의 최종 상태는 다음과 같다.

- `old_moved = true`
- `new_promoted = true`
- `canonical_verified = true`
- `rollback = null`
- `backup_cleanup = success`

승격 후 canonical 폴더를 다시 조회해 8개 파일의 크기와 Dropbox content hash가
staging 및 로컬 산출물과 동일함을 확인했다. 최종 파일 크기는 다음과 같다.

| 파일 | bytes |
| --- | ---: |
| `SHA256SUMS` | 572 |
| `coverage.jsonl.gz` | 89,015 |
| `entries.jsonl.gz` | **32,690,587** |
| `manifest.json` | **1,237** |
| `odds.jsonl.gz` | **177,663,413** |
| `races.jsonl.gz` | 492,943 |
| `results.jsonl.gz` | 22,854,988 |
| `sales.jsonl.gz` | 3,406,155 |

Dropbox 앱에는 content-read scope가 없으므로 사후 검증은 파일 본문 재다운로드가
아니라 **성공한 rebuild의 내부 내용 검증 + staging 크기·content-hash 검증 + 원자적
승격 + 승격 후 canonical 크기·content-hash 재검증**을 결합해 판정한다.

## 6. 최종 판정과 남은 품질 점검

**2016-2025 KRA 공개 API 수집·normalized 감사·coverage 감사·API-only canonical
재빌드·Dropbox 보존은 완료 상태다.**

`entries` 38행 초과 문제, 2023년 출전표 밖 72행, 2025년 endpoint 공백은 모두
canonical에서 해결됐다. 2023년 공급기관 raw 응답 자체의 미정정 문제는 원자료
예외로 남지만 현재 canonical 무결성에는 영향을 주지 않는다.

후속 HTML 대조도 완료했다. HTML–API 공통 19,301경주에서 유효 배당
24,263,109키의 숫자 불일치는 0건이다. 알려진 예외는
`docs/KNOWN_DATA_EXCEPTIONS.md`에 고정하며, 입력 bundle이나 판정 규칙이 바뀌지 않는
한 같은 사례를 다시 미해결 품질 문제로 열지 않는다.
