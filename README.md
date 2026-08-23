# Korea Horse Racing Data

한국 경마 공개데이터를 재현 가능하게 수집·검증·보존하기 위한 비공식 연구 프로젝트입니다.

## 현재 상태

**2016-2025년 10개년 KRA 공개 API 수집·통합·corrected canonical Dropbox 보존은 완료 상태입니다.**

- 총 8,123개 논리 수집 단위 기술 감사 완료, 오류 0
- 2020·2021 기존 수집 artifact 재사용 및 의미 감사 완료
- normalized/staged 계층 역할·중복·schema 감사 완료
- 통합 연구용 race universe: 24,436경주
- canonical entries/results: 각 **261,354행**
- API26_2 source duplicate 38행은 raw/normalized에 보존하고 research에서 natural key 기준으로 정리
- 통합 odds: 29,192,211행
- `race_id` 중복: 0
- corrected canonical Dropbox 연구 bundle 보존 완료
- 원천 API가 제공하지 않는 값은 0으로 대체하지 않고 coverage gap으로 유지
- 후속 HTML 대조와 경주 적격성 감사 완료: 기본 배당 분석 대상 **20,682경주**

최종 수치, GitHub Actions run, artifact, Dropbox 보존 증거는
**[docs/CURRENT_STATUS_2016_2025.md](docs/CURRENT_STATUS_2016_2025.md)** 한 문서에 통합되어 있습니다.

## 먼저 읽기: 이미 확인한 예외

아래 사례는 2016–2025 전체 자료에서 원인을 확인했다. 입력 bundle이나 판정 규칙이
바뀌지 않았다면 같은 사례를 다시 “이상 경주”로 처음부터 조사하지 않는다. 상세 근거와
분석 규칙은 **[docs/KNOWN_DATA_EXCEPTIONS.md](docs/KNOWN_DATA_EXCEPTIONS.md)**에 기록한다.

| 사례 | 전수 확인 결과 | 처리 |
| --- | --- | --- |
| 배당 `= 9999.9` | 정상 경주의 등록 마번 조합에서는 표시상한이다 | 삭제하지 않고 우측 검열값으로 보존 |
| 배당 `> 9999.9` | **2018-07-01 하루만 존재**: 15경주, 18개 승식판, 3,555조합, 최대 235,070.0 | 상한값이 아니라 그날 실제 게시된 점값으로 보존 |
| 2023-03-17 부경 8경주 | API28_1 단·연승에 출전표 밖 마번을 참조한 `9999.9` 72행 | 해당 72행만 제외; KRA 신고 완료 |
| 2019-05-18 제주 6경주 | API26_2 `dusu=9`, 등록·실제 출전은 10두 | `dusu`를 단독 정본으로 사용하지 않음; KRA 신고 완료 |
| 결과 없는 경주 | 전체 145경주. 2020–2021 50경주, 그 밖의 기간 95경주 | 원자료에는 보존하고 기본 분석에서 제외 |
| 2019-11-29 부경 1–11경주 | 당일 11경주 전부 취소. 결과·HTML 링크가 없고 API 배당은 전부 `9999.9` | 배당 이상이 아니라 취소·무결과 경주로 처리 |
| 2025-10-17 제주·부경 16경주 | API28_1·API29_1의 5개 승식이 빠졌지만 HTML에는 존재 | HTML 3,866행으로 보완하고 출처 표시 |
| HTML에 없고 API에 있는 경주 | 기존 HTML 수집은 지역별 전형 요일을 기준으로 한 부분집합 | HTML 부재만으로 API 경주를 이상으로 판정하지 않음 |

판정 순서는 다음과 같다.

1. 유효 순위가 하나도 없으면 먼저 취소·무결과 경주로 분리한다.
2. 배당 조합의 모든 마번이 출전표 안에 있는지 확인한다.
3. 승식 전체가 비었는지와 일부 조합만 비었는지를 구분한다.
4. `9999.9`와 `9999.9 초과`를 구분한다. 초과값은 현재까지 2018-07-01에만 있다.
5. API–HTML 공통 키의 값이 실제로 다른 경우에만 값 오류 후보로 올린다. 현재 공통
   24,263,109키의 숫자 불일치는 0건이다.

## 수집 범위

2016-2025년, 서울·제주·부경의 다음 8개 공개 API를 보존합니다.

`API28_1`, `API29_1`, `API30_1`, `API179_1`, `API26_2`, `API227`, `API4_3`, `API5`

- JSON이 가능한 서비스는 JSON으로 보존하고 `API227`, `API4_3`은 XML을 사용합니다.
- raw 응답은 페이지별 원본 바이트를 보존합니다.
- `API227`은 `API4_3`에서 발견한 실제 경주일만 호출합니다.
- 비경주·예비·취소·시험성 기록은 raw에는 보존하되 연구용 race universe에서는 제외합니다.
- normalized/staged는 source item을 JSONL로 구조화하는 계층이며 의미·자료형 통일은 research에서 수행합니다.
- API5는 API29 복승의 validation evidence로 raw/normalized에 유지하고 research odds에는 중복 포함하지 않습니다.

## Dropbox

canonical Dropbox는 GitHub Actions repository secrets의
`DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`이 가리키는 기존 Dropbox 앱 계정입니다.
기본 경로는 `/앱/kra-data/`이고 통합 연구용 데이터는 `/앱/kra-data/research/2016-2025/`에 보존합니다.

## 문서

- **[docs/CURRENT_STATUS_2016_2025.md](docs/CURRENT_STATUS_2016_2025.md)** — 최종 수집·통합·corrected Dropbox 보존 상태
- **[docs/NORMALIZED_LAYER_AUDIT.md](docs/NORMALIZED_LAYER_AUDIT.md)** — normalized/staged 계층의 역할, 실제 artifact 감사, 중복·schema 판정
- **[docs/API_FINDINGS.md](docs/API_FINDINGS.md)** — KRA 공개 API 조사 결과
- **[docs/COLLECTION_FORMATS.md](docs/COLLECTION_FORMATS.md)** — API 형식·호출량·저장 규칙
- **[docs/COLLECTION_WORKFLOW.md](docs/COLLECTION_WORKFLOW.md)** — 재수집·증분수집 시 운영 규칙
- **[docs/SEMANTIC_AUDIT_2020_2021.md](docs/SEMANTIC_AUDIT_2020_2021.md)** — 2020·2021 의미 완전성 감사
- **[docs/COVERAGE_GAP_AUDIT_2016_2025.md](docs/COVERAGE_GAP_AUDIT_2016_2025.md)** — coverage gap의 원인과 처리
- **[docs/KNOWN_DATA_EXCEPTIONS.md](docs/KNOWN_DATA_EXCEPTIONS.md)** — 이미 확인한 이상·예외와 재조사 중단 기준
- `docs/backfill-audit-2016-2025.json`, `docs/pilot-audit-2020-2021.json` — 기계적 보존 감사 증거

## 개발·검증

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m kra_data.preflight \
  --start-year 2020 --end-year 2021 --meets 1,2,3
PYTHONPATH=src python -m kra_data.normalized_audit <collection-artifact.zip>
```

운영 workflow는 `collect.yml`, `probe.yml`, `ci.yml`만 유지합니다.
