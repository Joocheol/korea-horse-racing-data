# 데이터 이용조건과 출처

## 공개 원칙

프로젝트 코드와 프로젝트가 작성한 문서는 저장소의 MIT License를 따른다.
KRA OpenAPI 원응답과 정규화 사실값은 아래 공공데이터포털 카탈로그에서
2026-08-18 직접 확인한 `이용허락범위 제한 없음` 조건에 따라 공개할 수 있다.
8개 데이터셋은 모두 무료이며 공공누리 유형은 별도로 표시되지 않았다.

## 확인된 OpenAPI 8종

| 데이터셋 | 엔드포인트 | 이용허락범위 | 개발계정 일일 한도 | 운영단계 | 포맷 | 카탈로그 |
| --- | --- | --- | ---: | --- | --- | --- |
| 15059137 | `API28_1/singlePredictionRateInfo_1` | 제한 없음 | 3,000 | 심의승인 | JSON+XML | [링크](https://www.data.go.kr/data/15059137/openapi.do) |
| 15057397 | `API29_1/doublePredictionRateInfo_1` | 제한 없음 | 3,000 | 심의승인 | JSON+XML | [링크](https://www.data.go.kr/data/15057397/openapi.do) |
| 15058258 | `API30_1/triplePredictionRateInfo_1` | 제한 없음 | 3,000 | 심의승인 | JSON+XML | [링크](https://www.data.go.kr/data/15058258/openapi.do) |
| 15057896 | `API179_1/salesAndDividendRate_1` | 제한 없음 | 3,000 | 심의승인 | JSON+XML | [링크](https://www.data.go.kr/data/15057896/openapi.do) |
| 15057090 | `API5/quinellaOddsInfo` | 제한 없음 | 3,000 | 심의승인 | **XML 전용** | [링크](https://www.data.go.kr/data/15057090/openapi.do) |
| 15058677 | `API26_2/entrySheet_2` | 제한 없음 | 3,000 | 심의승인 | JSON+XML | [링크](https://www.data.go.kr/data/15058677/openapi.do) |
| 15119524 | `API214_1/RaceDetailResult_1` | 제한 없음 | 3,000 | 심의승인 | JSON+XML | [링크](https://www.data.go.kr/data/15119524/openapi.do) |
| 15058305 | `API4_3/raceResult_3` | 제한 없음 | 3,000 | 심의승인 | JSON+XML | [링크](https://www.data.go.kr/data/15058305/openapi.do) |

위 표로 공개 API 원응답 bulk 재배포와 정규화 사실값 재배포의 확인 절차는
충족된 것으로 처리한다. 운영계정 트래픽 상향은 자동승인이 아니라 심의승인이므로
별도 승인 전에는 개발계정 한도를 적용한다.

## 출처표시

각 Release에는 다음 출처를 표시한다.

> 출처: 한국마사회, 공공데이터포털(data.go.kr). 이용조건 확인일: 2026-08-18.

API 기반 릴리스는 독립적인 공식 시행일 분모가 없으면
`provisional_api_only`로 표시한다. 이는 라이선스 제한이 아니라 개최일 통누락을
독립적으로 검출하지 못했다는 완전성 표시다.

## 별도 격리 대상

위 공개조건은 공공데이터포털 OpenAPI 8종에만 적용한다. KRA 웹사이트에서 별도로
스크래핑한 HTML·PDF·이미지·로고 등은 재배포 조건이 확인되기 전 공개하지 않고
비공개 격리한다. API 인증키, GitHub Actions Secret, 인증키가 포함된 URL·로그,
개인 저장경로도 공개하지 않는다.
