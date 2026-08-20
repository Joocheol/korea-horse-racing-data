# API 형식·호출량·Dropbox 경로 결정

*확정 2026-08-20*

## 1. 대상 API와 원본 형식

| 논리 이름 | 서비스 | 원본 형식 | 일일 한도 |
| --- | --- | --- | ---: |
| `single` | `API28_1` | JSON | 3,000 |
| `double` | `API29_1` | JSON | 3,000 |
| `triple` | `API30_1` | JSON | 3,000 |
| `sales` | `API179_1` | JSON | 3,000 |
| `entries` | `API26_2` | JSON | 3,000 |
| `results` | `API227` | XML | 3,000 |
| `race_record` | `API4_3` | XML | 3,000 |
| `quinella_crosscheck` | `API5` | JSON | 3,000 |

JSON이 가능한 서비스는 JSON으로 받고 `API227`과 `API4_3`은 XML을 사용한다. raw 파일은
응답 바이트를 변형하지 않고 페이지별 확장자 `.json` 또는 `.xml`로 저장한다.
공통 JSONL 변환은 staged/normalized 계층에서만 수행한다.

## 2. 호출 예산

한도는 8개 서비스를 합친 3,000회가 아니라 서비스별 3,000회다. 재시도와 추가
페이지도 실제 호출이므로 예산에 포함한다. `used_json`은 `API28_1` 같은 서비스
ID를 키로 사용한다.

2020·2021년 3개 경마장 파일럿은 792개 수집 단위다. 월간 삼쌍승이 100,000행을
넘을 수 있어 `API30_1`의 TRI 단위에 2페이지를 예약하면 총 예상 호출은 864회다.

## 3. Dropbox

사용자에게 보이는 기준 경로는 **`/앱/kra-data/`**다. 기존
`/앱/kra-actions-lab-joocheol/` 아래에 중첩하지 않는다.

```text
/앱/kra-data/
  raw/
  normalized/
  manifests/
  quarantine/
  docs/
```
