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
| `research` | 실제 연구용 canonical 데이터 | `race_id`, `meet`, `pool_code` 표준화, API별 파일 통합, 연구 race universe 적용, coverage 생성 | 원천에 없는 값을 임의 생성하거나 결측을 0으로 대체 |

따라서 `normalized`라는 이름의 의미는 **structural normalization**이며 semantic normalization은 `research`에서 수행한다.

## 실제 artifact 감사

### 2020-2021 완전수집 artifact

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

### 2025 production artifact

대상: GitHub Actions artifact `kra-backfill-2025`, ID `9468442238`.

- staged JSONL 파일: 654개
- 총 행: 3,280,645
- 빈 staged 파일: 0
- 파일 내부 완전 중복행: 0
- entries schema presence variants: 4
- race_record schema presence variants: 3
- results schema presence variants: 2

schema variant는 오류로 판정하지 않는다. 원천 API에서 선택적으로 빠지는 필드와 JSON/XML의 source-native 표현 차이를 normalized 계층이 그대로 보존하기 때문이다.

## API5 복승 교차검증 자료

`API5` (`quinella_crosscheck`)는 `API29_1`의 복승(`double-qnl`)과 내용이 중복되지만 삭제하지 않는다. 역할이 **독립 endpoint에 의한 검증 증거**이기 때문이다.

감사 결과:

| 표본 | double-qnl 행 | API5 행 | 키 누락 | 배당 불일치 |
| --- | ---: | ---: | ---: | ---: |
| 2020-2021 | 222,490 | 222,490 | 0 | 0 |
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
- API29 QNL과 API5의 natural-key coverage 및 odds 일치 여부

완전 중복행이 있거나 QNL 교차검증이 불일치하면 감사 명령은 실패 코드로 종료한다. 빈 파일과 source-field presence variant는 경고/기술 통계이지 자동 실패 사유가 아니다.

## 최종 판정

현재 계층을 새로 뜯어고칠 필요는 없다. 다만 명칭과 역할을 다음처럼 이해해야 한다.

```text
KRA API
  -> raw        : 원본 바이트
  -> normalized : source item을 JSONL로 구조화한 archival staging
  -> research   : cross-API 의미 통합 및 연구용 canonical tables
  -> derived    : 개별 논문의 계산·추정 변수
```

기존 raw/normalized archive는 불변 provenance로 유지하고, 앞으로의 분석과 Parquet/DuckDB 변환은 `research`에서 시작한다.
