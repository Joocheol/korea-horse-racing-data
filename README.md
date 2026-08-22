# Korea Horse Racing Data

한국 경마 공개데이터를 재현 가능하게 수집·검증·배포하기 위한 비공식 연구 프로젝트입니다.

## 현재 상태

**2016-2025년 10개년 KRA 공개 API 수집·보존 작업은 완료 상태입니다.**

- 총 8,123개 논리 수집 단위 기술 감사 완료, 오류 0
- 2020·2021은 기존 수집 완료 artifact를 재사용했으며 재수집하지 않음
- 2020·2021 경주 universe 의미 감사 완료
- raw / normalized / manifests / quarantine / docs 계층 Dropbox 보존 감사 완료
- 2016-2025 통합 연구용 bundle 생성·검증·Dropbox 보존 완료
- 원천 API가 제공하지 않는 값은 source-level coverage gap으로 별도 표시

최종 판정과 검증 근거는
**[docs/CURRENT_STATUS_2016_2025.md](docs/CURRENT_STATUS_2016_2025.md)**에 기록합니다.
2020·2021의 승식별 coverage 차이 검증은
**[docs/SEMANTIC_AUDIT_2020_2021.md](docs/SEMANTIC_AUDIT_2020_2021.md)**를 참고하십시오.

## Dropbox 보존 원칙

이 저장소의 **canonical Dropbox는 GitHub Actions repository secrets의
`DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`이 가리키는 Dropbox 앱 계정**이다.
다른 Dropbox 연결이나 외부 커넥터의 계정은 보존 완료 여부 판정에 사용하지 않는다.

- canonical 사용자 표시 경로: `/앱/kra-data/`
- 원자료 계층: `raw`, `normalized`, `manifests`, `quarantine`, `docs`
- 통합 연구용 데이터: `/앱/kra-data/research/2016-2025/`
- Dropbox 보존 성공 판정: GitHub Actions에서 Dropbox API가 반환한 성공 응답 + 업로드 evidence artifact

세부 원칙과 최종 연구 bundle의 보존 증거는
**[docs/DROPBOX_STORAGE.md](docs/DROPBOX_STORAGE.md)**에 기록합니다.

## 수집 범위

2016-2025년, 서울·제주·부경의 다음 8개 공개 API를 보존합니다.

`API28_1`, `API29_1`, `API30_1`, `API179_1`, `API26_2`, `API227`, `API4_3`, `API5`

- 원본 형식은 JSON 우선이며, `API227`과 `API4_3`은 XML로 보존합니다.
- raw 응답은 파싱 후 재조립하지 않고 페이지별 원본 바이트를 그대로 저장합니다.
- 월 조회가 느린 `API227`은 `API4_3`에서 실제 경주일을 발견한 뒤 경주일 단위로 수집합니다.
- 비경주/예비·취소·시험성 기록은 raw에는 보존하되 연구용 race universe에서는 제외합니다.
- 원천 API의 coverage gap은 값을 임의로 0으로 채우지 않고 결측 flag로 관리합니다.

## 문서

- **[docs/API_FINDINGS.md](docs/API_FINDINGS.md)** — KRA 공개 API 조사 결과
- **[docs/PILOT_2020_2021.md](docs/PILOT_2020_2021.md)** — 2020·2021 최초 수집 범위와 검증 방침
- **[docs/COLLECTION_WORKFLOW.md](docs/COLLECTION_WORKFLOW.md)** — 실행 승인, 재개, 저장 계층과 종료 기준
- **[docs/CURRENT_STATUS_2016_2025.md](docs/CURRENT_STATUS_2016_2025.md)** — 10개년 최종 보존·검증 현황
- **[docs/SEMANTIC_AUDIT_2020_2021.md](docs/SEMANTIC_AUDIT_2020_2021.md)** — 2020·2021 경주 ID·승식 coverage 의미 감사
- **[docs/RESEARCH_DATASET_2016_2025.md](docs/RESEARCH_DATASET_2016_2025.md)** — 10개년 통합 연구용 데이터셋
- **[docs/DROPBOX_STORAGE.md](docs/DROPBOX_STORAGE.md)** — canonical Dropbox 계정·경로·검증 원칙

## 개발·검증

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m kra_data.preflight \
  --start-year 2020 --end-year 2021 --meets 1,2,3
```

실제 수집은 push로 시작되지 않습니다. 수동 workflow와 Environment 승인을 사용합니다.
연결 상태와 페이지 크기를 점검할 때는 `Probe one KRA API page`를 실행합니다.
