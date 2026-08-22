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

GitHub Actions run `32595439823`에서 동일 빌드를 재현했고 전체 job이 `success`로 완료되었다.

- 연구 bundle artifact: `kra-research-2016-2025`
- artifact ID: `9481498381`
- artifact size: `320,932,784` bytes
- Dropbox upload evidence artifact: `kra-research-dropbox-evidence`
- evidence artifact ID: `9481506837`

canonical Dropbox는 repository secrets의 `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`,
`DROPBOX_REFRESH_TOKEN`이 가리키는 기존 Dropbox 앱 계정이다. 이 계정의
`/앱/kra-data/research/2016-2025/`에 다음 8개 파일이 Dropbox API 성공 응답과 함께 보존되었다.

| 파일 | Dropbox 응답 크기 |
| --- | ---: |
| `SHA256SUMS` | 572 |
| `coverage.jsonl.gz` | 125,355 |
| `entries.jsonl.gz` | 32,692,664 |
| `manifest.json` | 411 |
| `odds.jsonl.gz` | 261,365,204 |
| `races.jsonl.gz` | 492,943 |
| `results.jsonl.gz` | 22,847,349 |
| `sales.jsonl.gz` | 3,407,302 |

외부 Dropbox 커넥터가 다른 사용자 컨텍스트를 가리킬 수 있으므로, 이 프로젝트의
Dropbox 보존 성공 여부는 **canonical 앱 계정에 대한 GitHub Actions Dropbox API 응답과 evidence artifact**를 기준으로 판정한다.
