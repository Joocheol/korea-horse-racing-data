# 2016-2025 통합 연구용 데이터셋

*생성·검증일: 2026-08-22*

2016-2025년 KRA 공개 API 수집물을 공통 `race_id` 기준의 연구용 relational bundle로 통합했다.

## 스키마

공통 경주 키는 `YYYYMMDD-meet-rcNo` 형식이다. 결과는 다음 파일로 분리한다.

- `races.jsonl.gz`: 경주 universe
- `entries.jsonl.gz`: 출전마
- `results.jsonl.gz`: 경주 상세결과
- `sales.jsonl.gz`: 승식별 매출·확정배당
- `odds.jsonl.gz`: 승식별 전체 배당판
- `coverage.jsonl.gz`: 경주별 승식 제공/매출 존재 flag
- `manifest.json`: 생성·검증 요약

결측값은 0으로 대체하지 않는다. 원천 API가 제공하지 않는 값은 source-level coverage gap으로 남긴다.

## 최종 행 수

| 계층 | 행/경주 수 |
| --- | ---: |
| races | 24,436 |
| race_record rows | 261,354 |
| entries | 261,392 |
| results | 261,354 |
| sales | 163,844 |
| odds | 29,192,211 |
| non-race odds excluded | 526,192 |
| coverage | 24,436 |

## coverage 요약

| 항목 | 경주 수 |
| --- | ---: |
| sales 전체 미제공 | 145 |
| 삼복·삼쌍 매출 모두 미제공 | 1,394 |
| sales WIN | 24,291 |
| sales PLC | 24,291 |
| sales QNL | 24,291 |
| sales EXA | 23,042 |
| sales QPL | 23,042 |
| sales TLA | 23,042 |
| sales TRI | 21,845 |
| odds WIN | 24,420 |
| odds PLC | 24,403 |
| odds QNL | 24,420 |
| odds EXA | 23,144 |
| odds QPL | 23,144 |
| odds TLA | 23,160 |
| odds TRI | 21,950 |

## 최종 검증

- 2016-2025 10개 연도 모두 존재
- `race_id` 24,436개 전부 unique
- 중복 `race_id`: 0
- `races`와 `coverage` 행 수 일치
- 원천 배당 API에만 있는 비경주/예비·취소·시험성 조합 526,192행은 연구용 race universe에서 제외
- 2020·2021은 기존 수집 artifact를 재사용했으며 재수집하지 않음

통합 빌더는 `src/kra_data/research.py`에 구현되어 있다. 대용량 odds 출력을 위해 gzip compression level 1을 사용하되 JSONL 내용과 검증 규칙은 변하지 않는다.

## 보존 상태

로컬 실행 환경에서 통합 bundle 생성과 검증은 완료했다. GitHub Actions에서 동일 빌드를 재현하고 Dropbox `/앱/kra-data/research/2016-2025`에 보존하는 일회성 workflow를 추가했다. Dropbox 업로드는 실제 목록 조회로 파일이 확인된 뒤 성공으로 확정한다.
