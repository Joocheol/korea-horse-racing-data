# Korea Horse Racing Data

한국 경마 공개데이터를 재현 가능하게 수집·검증·배포하기 위한 비공식 연구 프로젝트입니다.

## 파일럿 범위

2020·2021년, 서울·제주·부경의 다음 8개 공개 API를 수집합니다.

`API28_1`, `API29_1`, `API30_1`, `API179_1`, `API26_2`, `API214_1`, `API4_3`, `API5`

- 원본 형식은 JSON 우선이며, JSON 원응답을 제공하지 않는 `API4_3`만 XML로 보존합니다.
- raw 응답은 파싱 후 재조립하지 않고 페이지별 원본 바이트를 그대로 저장합니다.
- 서비스별 개발계정 한도 3,000회를 각각 검사합니다.
- 파일럿 전체는 792개 수집 단위이며, 추가 페이지 예산을 포함해 864회 호출로 계획합니다.
- Dropbox 사용자 표시 경로는 `/앱/kra-data/`이고, 그 아래 `raw`, `normalized`,
  `manifests`, `quarantine`, `docs`를 둡니다.

## 문서

- **[docs/API_FINDINGS.md](docs/API_FINDINGS.md)** — KRA 공개 API 조사 결과
- **[docs/PILOT_2020_2021.md](docs/PILOT_2020_2021.md)** — 첫 수집 범위와 검증 방침
- **[docs/COLLECTION_WORKFLOW.md](docs/COLLECTION_WORKFLOW.md)** — 실행 승인, 재개, 저장 계층과 종료 기준

## 개발·검증

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
PYTHONPATH=src python -m kra_data.preflight \
  --start-year 2020 --end-year 2021 --meets 1,2,3
```

실제 수집은 push로 시작되지 않습니다. `Collect KRA pilot batch`를 수동 실행하고
`kra-collection` Environment 승인을 받아야 합니다.

연결 상태와 페이지 크기를 점검할 때는 `Probe one KRA API page`를 실행합니다.
이 진단 워크플로우는 전체 월을 수집하지 않고 지정한 페이지 한 장만 요청하며,
인증키를 출력하지 않은 채 행 수·전체 건수·응답 크기·SHA-256을 기록합니다.
