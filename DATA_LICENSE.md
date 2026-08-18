# Data licensing and attribution

## Release rule

Project source code and project-authored documentation are released under the repository's MIT
License. Source racing data are not blanket-relicensed by this project. Each data release inherits
the official permission and attribution terms of every source that contributed to that release.

An annual partition is public only when every contributing endpoint has a recorded catalog URL,
permission scope, verification date, and confirmation that redistribution of both raw responses
and normalized factual data is allowed. If any source remains unverified, that source is omitted or
the affected partition is withheld.

## Endpoint register

The following register is completed before the first data release. “Pending” means that the
endpoint may be used for a private pilot but cannot contribute to a public release.

| Endpoint | Permission scope | Verified | Official catalog URL | Public release gate |
|---|---|---|---|---|
| `API28_1/singlePredictionRateInfo_1` | Pending | Pending | Pending | Blocked |
| `API29_1/doublePredictionRateInfo_1` | Pending | Pending | Pending | Blocked |
| `API30_1/triplePredictionRateInfo_1` | Pending | Pending | Pending | Blocked |
| `API5/quinellaOddsInfo` | Pending | Pending | Pending | Blocked |
| `API179_1/salesAndDividendRate_1` | Pending | Pending | Pending | Blocked |
| `API26_2/entrySheet_2` | Pending | Pending | Pending | Blocked |
| `API214_1/RaceDetailResult_1` | Pending | Pending | Pending | Blocked |
| `API4_3/raceResult_3` | Pending | Pending | Pending | Blocked |
| `API160_1/integratedInfo_1` | Unrestricted use | 2026-08-18 | Record exact data.go.kr catalog URL before release | Blocked until URL recorded |
| `API301/Dividend_rate_total` | Pending | Pending | Pending | Blocked |

The API160 catalog page checked on 2026-08-18 described the service as free and its permitted use
scope as unrestricted. This does not establish the terms for any other endpoint.

## Release attribution

Every release includes the following text, expanded with endpoint URLs and the verification date:

> Source: Korea Racing Authority, Korean Public Data Portal (data.go.kr). Source permission terms
> verified on YYYY-MM-DD; see this release's DATA-LICENSE file.

The release-specific `DATA-LICENSE-YYYY-vN.txt` states the most restrictive compatible terms that
apply to the partition. It does not imply ownership of KRA source facts or waive source conditions.

## Exclusions

Public releases exclude:

- API credentials, GitHub Actions secrets, unredacted request URLs, and secret-bearing logs
- personal or local storage paths
- raw KRA website HTML, PDFs, images, logos, or other content without verified redistribution terms
- third-party data without an explicit compatible license

KRA web facts may be normalized only after the applicable terms and provenance are recorded. Raw
web material remains private and is removed under the retention rule in the collection plan unless
redistribution permission is confirmed.
