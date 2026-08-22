# Canonical Dropbox storage

*확정일: 2026-08-23*

이 프로젝트의 Dropbox 정본(canonical storage)은 **GitHub Actions repository secrets**에 등록된
`DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`이 가리키는 기존 Dropbox 앱 계정이다.

## 원칙

1. 이 앱 계정을 KRA 데이터의 유일한 Dropbox 정본으로 사용한다.
2. 다른 Dropbox 연결, 개인 계정, ChatGPT Dropbox 커넥터의 목록은 정본 판정에 사용하지 않는다.
3. 업로드 성공 여부는 GitHub Actions가 canonical 앱 계정으로 호출한 Dropbox API의 성공 응답과
   Actions evidence artifact로 검증한다.
4. Dropbox credentials 자체는 GitHub Secrets에만 보관하고 저장소에는 기록하지 않는다.
5. 기존 `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, `DROPBOX_REFRESH_TOKEN`을 계속 사용한다.

## canonical 경로

기본 사용자 표시 경로는 `/앱/kra-data/`이다.

- `/앱/kra-data/raw/`
- `/앱/kra-data/normalized/`
- `/앱/kra-data/manifests/`
- `/앱/kra-data/quarantine/`
- `/앱/kra-data/docs/`
- `/앱/kra-data/research/2016-2025/`

## 완료된 보존 작업

### 2016-2019, 2022-2025

- source run: `32544887677`
- archive run: `32553067249`
- 보존 감사: `docs/backfill-audit-2016-2025.json`
- 기술 감사: 5,210 / 5,210 complete
- Dropbox status: success

### 2020-2021

- source run: `32340684155`
- source artifact: `9396629882` (`kra-collection-state`)
- archive run: `32559614706`
- 보존 감사: `docs/pilot-audit-2020-2021.json`
- 기술 감사: 2,913 / 2,913 complete
- Dropbox status: success

### 2016-2025 통합 연구용 bundle

- build/archive run: `32595439823`
- job: `build-and-archive` — success
- research artifact: `9481498381` (`kra-research-2016-2025`)
- Dropbox evidence artifact: `9481506837` (`kra-research-dropbox-evidence`)
- Dropbox destination: `/앱/kra-data/research/2016-2025/`

Dropbox API가 성공 반환한 파일:

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

## 운영 규칙

앞으로 Dropbox 관련 작업은 다음 순서로 판정한다.

1. GitHub Actions에서 기존 Dropbox secrets로 인증한다.
2. 업로드 대상은 위 canonical 경로만 사용한다.
3. Dropbox API의 `path_display`, `size`, 필요 시 `content_hash`/`rev`를 evidence에 기록한다.
4. Actions job과 evidence가 성공하면 Dropbox 보존 완료로 판정한다.
5. 외부 Dropbox 커넥터가 같은 파일을 표시하지 않더라도 canonical 앱 계정의 증거와 혼동하지 않는다.

따라서 이 프로젝트에서 별도의 Dropbox 계정 전환이나 refresh token 교체는 하지 않는다.
