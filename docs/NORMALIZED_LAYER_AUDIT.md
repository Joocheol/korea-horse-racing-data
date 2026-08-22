# Normalized 계층 감사 및 최종 규칙

*감사일: 2026-08-23*

## 결론

이 프로젝트의 `normalized`는 **연구용 의미 통합 데이터가 아니라, API 응답을 행 단위 JSONL로 구조화한 중간 보존 계층**으로 확정한다.

코드 내부 명칭은 `staged/`이며 Dropbox 보존 경로는 `/앱/kra-data/normalized/`이다. 두 이름은 같은 논리 계층을 가리킨다.

최종 경계는 다음과 같다.

| 계층 | 역할 | 허용되는 변환 | 금지되는 변환 |
| --- | --- | --- | --- |
| `raw` | 원천 증거 | 없음 | 파싱, 값 변경, 결측 대체 |
| `normalized` (`staged`) | 원천 레코드를 공통 JSONL 행으로 구조화 | JSON/XML item을 1행 JSON으로 변환, API227의 완전히 동일한 중복행 제거 | cross-API 조인, `race_id` 추가, 승식 코드 통일, 자료형 강제 통일, 결측 0 대체, 연구 표본 필터 |
| `research` | 실제 연구용 canonical 데이터 | `race_id`, `meet`, `pool_code` 표준화, API별 파일 통합, 자연키 중복 정리, 연구 race universe 적용, coverage 생성 | 원천에 없는 값을 임의 생성하거나 결측을 0으로 대체 |

따라서 `normalized`라는 이름의 의미는 **structural normalization**이며 semantic normalization은 `research`에서 수행한다.

## 실제 artifact 전수 감사

### production 방식: 2016-2019, 2022-2025

GitHub Actions run `32544887677`의 연도별 `kra-backfill-YYYY` artifact를 전수 확인했다.

| 연도 | staged JSONL | 총 행 | 빈 파일 | results 파일 | 비고 |
| --- | ---: | ---: | ---: | ---: | --- |
| 2016 | 653 | 2,703,042 | 12 | 293 | 빈 파일 12개는 모두 `triple-tri` |
| 2017 | 648 | 3,742,259 | 0 | 288 | 정상 |
| 2018 | 648 | 3,767,623 | 0 | 288 | 정상 |
| 2019 | 648 | 3,886,005 | 0 | 288 | 정상 |
| 2022 | 648 | 3,385,413 | 0 | 288 | 정상 |
| 2023 | 657 | 3,364,878 | 0 | 297 | 정상 |
| 2024 | 654 | 3,156,359 | 0 | 294 | 정상 |
| 2025 | 654 | 3,280,645 | 0 | 294 | 정상 |

2016의 `triple-tri` 빈 파일은 해당 월/경마장에서 source가 반환한 행이 없는 구조적 공백이며, raw/normalized 보존 원칙상 그대로 유지한다. 빈 파일 자체를 수집 실패로 판정하지 않는다.

모든 production 연도에서 normalized 파일 유형은 다음 11종으로 고정된다.

- `single-all.jsonl`
- `double-qnl.jsonl`
- `double-exa.jsonl`
- `double-qpl.jsonl`
- `triple-tla.jsonl`
- `triple-tri.jsonl`
- `sales-all.jsonl`
- `entries-all.jsonl`
- `race_record-all.jsonl`
- `results-all/date-YYYYMMDD.jsonl`
- `quinella_crosscheck-all.jsonl`

### 2020-2021 legacy pilot artifact

대상: GitHub Actions artifact `kra-collection-state`, ID `9396629882`.

- staged JSONL 파일: 2,913개
- 총 행: 4,656,969
- 파일 내부 완전 중복행: 0
- 빈 staged 파일: 1,797개
- 빈 파일은 과거 pilot planner가 API227을 달력 날짜 전체에 호출했던 흔적이며 데이터 손실이 아니다.
- 현재 운영 planner는 API4_3에서 발견한 실제 경주일만 API227 대상으로 사용하므로 이 legacy empty-file 패턴을 새 수집에는 만들지 않는다.

주요 행 수:

| 데이터 | 행 |
| --- | ---: |
| entries | 41,749 |
| race_record | 41,749 |
| results | 41,749 |
| sales | 20,267 |
| single | 83,973 |
| double-qnl | 222,490 |
| double-exa | 301,788 |
| double-qpl | 150,803 |
| triple-tla | 504,273 |
| triple-tri | 3,025,638 |
| quinella_crosscheck | 222,490 |

## entries 38행 초과 문제: 원인 확정 및 research 처리

최종 research bundle에서 `entries`가 `race_record/results`보다 38행 많았던 원인을 natural key
`(rcDate, meet, rcNo, chulNo, hrNo)`로 추적했다.

| 연도 | entries 행 | race_record 행 | 초과 행 | natural-key 초과 |
| --- | ---: | ---: | ---: | ---: |
| 2016 | 29,346 | 29,341 | 5 | 5 |
| 2017 | 28,914 | 28,896 | 18 | 18 |
| 2018 | 28,507 | 28,496 | 11 | 11 |
| 2019 | 29,196 | 29,192 | 4 | 4 |
| 2022-2025 | 동일 | 동일 | 0 | 0 |
| 합계 | - | - | **38** | **38** |

38개 모두 동일 natural key가 API26_2 응답 안에서 두 번 나타난 source duplicate다. 서로 다른 출전마가 추가된 것이 아니다. 중복 두 행의 차이는 확인된 전 사례에서 마주명(`owName`, `owNameEn`) 표기 변형뿐이었다.

대표 예:

- `요시다 가츠미` ↔ `요시다가츠미`
- `YOSHIDA Katsumi` ↔ `Yoshida Katsumi`
- `(주)링크폴로` ↔ `링크폴로`
- `Linkpolo` ↔ `LINKPOLO`

정책은 다음과 같이 확정한다.

- raw/normalized에는 source duplicate를 그대로 보존한다.
- normalized audit는 이를 natural-key source anomaly로 집계하되 실패로 처리하지 않는다.
- research의 `entries`는 `(race_id, chulNo, hrNo)`를 canonical key로 사용해 1행만 유지한다.
- 파일 경로와 source 순서를 결정적으로 정렬한 후 처음 나온 source row를 유지한다.
- 제거된 중복 수와 서로 내용이 다른 duplicate key 수를 `manifest.json`에 기록한다.

이 수정 후 예상 canonical `entries` 행 수는 **261,354행**으로 `results`와 일치한다.

## API5 복승 교차검증 자료

`API5` (`quinella_crosscheck`)는 `API29_1`의 복승(`double-qnl`)과 내용이 중복되지만 삭제하지 않는다. 역할이 **독립 endpoint에 의한 검증 증거**이기 때문이다.

전수 감사 결과:

| 표본 | double-qnl 행 | API5 행 | 키 누락 | 배당 불일치 |
| --- | ---: | ---: | ---: | ---: |
| 2016 | 142,087 | 142,087 | 0 | 0 |
| 2017 | 138,401 | 138,401 | 0 | 0 |
| 2018 | 137,909 | 137,909 | 0 | 0 |
| 2019 | 142,544 | 142,544 | 0 | 0 |
| 2020-2021 | 222,490 | 222,490 | 0 | 0 |
| 2022 | 123,629 | 123,629 | 0 | 0 |
| 2023 | 126,478 | 126,478 | 0 | 0 |
| 2024 | 120,230 | 120,230 | 0 | 0 |
| 2025 | 123,078 | 123,078 | 0 | 0 |

따라서 다음 정책을 확정한다.

- raw/normalized에는 API5를 유지한다.
- `research/odds`에는 API29_1의 QNL만 사용한다.
- API5는 연구변수가 아니라 validation evidence로 취급한다.

## Dropbox의 normalized 보존 형식

Dropbox의 과거 pilot normalized 폴더를 확인하면 JSONL을 직접 나열하는 대신 `staged.tar.gz`를 base64 chunk로 분할한 `staged.tar.gz.NNN.b64part` 파일들이 보존되어 있다.

이는 **Dropbox 전송/보존 형식**일 뿐 normalized의 논리 스키마가 아니다. 실제 normalized 데이터는 복원된 tar 안의 `staged/**/*.jsonl`이다.

따라서 기존 archive는 provenance 보존을 위해 이동·삭제하지 않는다. 앞으로 분석자는 Dropbox normalized archive를 직접 분석하지 않고 `research` bundle을 사용한다.

## 자료형 정책

normalized는 source-native 값을 보존한다. 예를 들어 XML 기반 API4_3/API227에서는 숫자처럼 보이는 값도 문자열일 수 있고, JSON API에서는 숫자로 파싱될 수 있다. 이를 normalized에서 강제로 맞추지 않는다.

이유는 두 가지다.

1. raw와 normalized 사이의 변환을 최대한 단순하고 검증 가능하게 유지한다.
2. 의미가 같은지 확인하기 전에 자료형을 강제 변환해 원천 의미를 손상시키는 것을 막는다.

자료형·경마장 코드·승식 코드 등의 의미 통일은 `research` 빌더가 담당한다.

## 재현 가능한 감사 명령

`src/kra_data/normalized_audit.py`는 GitHub Actions artifact ZIP 또는 압축을 푼 collection 디렉터리를 감사한다.

```bash
PYTHONPATH=src python -m kra_data.normalized_audit kra-backfill-2025.zip \
  --output normalized-audit-2025.json
```

감사 항목은 다음과 같다.

- staged JSONL 파일 수
- dataset별 행 수
- 빈 파일 수
- source-field presence 기준 schema variant 수
- 파일 내부 완전 중복행
- entries natural-key duplicate 및 conflicting duplicate 수
- API29 QNL과 API5의 natural-key coverage 및 odds 일치 여부

완전 중복행이 있거나 QNL 교차검증이 불일치하면 감사 명령은 실패 코드로 종료한다. 빈 파일, source-field presence variant, entries natural-key source duplicate는 경고/기술 통계이며 자동 실패 사유가 아니다.

## 최종 판정

현재 계층을 새로 뜯어고칠 필요는 없다. 다만 명칭과 역할을 다음처럼 이해한다.

```text
KRA API
  -> raw        : 원본 바이트
  -> normalized : source item을 JSONL로 구조화한 archival staging
  -> research   : cross-API 의미 통합 및 연구용 canonical tables
  -> derived    : 개별 논문의 계산·추정 변수
```

기존 raw/normalized archive는 불변 provenance로 유지하고, 앞으로의 분석과 Parquet/DuckDB 변환은 `research`에서 시작한다.
