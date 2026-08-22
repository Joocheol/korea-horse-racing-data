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

최종 수치, GitHub Actions run, artifact, Dropbox 보존 증거는
**[docs/CURRENT_STATUS_2016_2025.md](docs/CURRENT_STATUS_2016_2025.md)** 한 문서에 통합되어 있습니다.

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
- `docs/backfill-audit-2016-2025.json`, `docs/pilot-audit-2020-2021.json` — 기계적 보존 감사 증거

## 개발·검증

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m kra_data.preflight \
  --start-year 2020 --end-year 2021 --meets 1,2,3
PYTHONPATH=src python -m kra_data.normalized_audit <collection-artifact.zip>
```

운영 workflow는 `collect.yml`, `probe.yml`, `ci.yml`만 유지합니다.
