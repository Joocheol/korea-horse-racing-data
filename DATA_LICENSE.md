# Data licensing and attribution

## Release rule

Project source code and project-authored documentation are released under the repository's MIT
License. Source racing data are not blanket-relicensed by this project. Each data release inherits
the official permission and attribution terms of every source that contributed to that release.

Each asset is gated separately. An annual partition may publish normalized facts only when every
contributing endpoint has a recorded catalog URL, use scope, Public Nuri/attribution type,
verification date, terms-text hash, next verification date, and permission for normalized-fact
redistribution. Bulk raw responses are added only where bulk raw redistribution is separately
confirmed. If normalized-fact permission for a source remains unverified, records depending on it
are withheld. Derived states may be released only after they are recomputed without that source and,
when evidence becomes insufficient, downgraded to `evidence_insufficient`.

## Endpoint register

The following register is completed before the first data release. “Pending” means that the
endpoint may be used for a private pilot but cannot contribute to a public release. Endpoint and
behavioral evidence must be read from `docs/API_FINDINGS.md`, not inferred from README alone.

| Endpoint | Use scope | Public Nuri / attribution | Bulk raw redistribution | Normalized facts | Verified / next check | Terms hash | Catalog URL | Gate |
|---|---|---|---|---|---|---|---|---|
| `API28_1/singlePredictionRateInfo_1` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked |
| `API29_1/doublePredictionRateInfo_1` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked |
| `API30_1/triplePredictionRateInfo_1` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked |
| `API5/quinellaOddsInfo` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked |
| `API179_1/salesAndDividendRate_1` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked |
| `API26_2/entrySheet_2` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked |
| `API214_1/RaceDetailResult_1` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked |
| `API4_3/raceResult_3` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked |
| `API72_2/racePlan_2` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked; path unverified |
| `API301/Dividend_rate_total` | Pending | Pending | Pending | Pending | Pending | Pending | Pending | Blocked; path unverified |

An investigated catalog page checked on 2026-08-18 described its portal use scope as unrestricted.
That field alone does not establish a Public Nuri type, attribution duty, or permission for bulk
redistribution, and a non-v1 service's terms establish nothing for the endpoints above.

The recorded terms text is normalized and hashed with SHA-256. A changed hash or an overdue next
check returns the endpoint to Pending until a human re-verifies the terms.

## Release attribution

Every release includes the following text, expanded with endpoint URLs and the verification date:

> Source: Korea Racing Authority, Korean Public Data Portal (data.go.kr). Source permission terms
> verified on YYYY-MM-DD; see this release's DATA-LICENSE file.

The release-specific `DATA-LICENSE-YYYY-vN.txt` states the most restrictive compatible terms that
apply to the partition. It does not imply ownership of KRA source facts or waive source conditions.
It also declares `final` or `provisional_api_only`. A provisional release states prominently that
whole-meeting-day omission could not be checked against an independent schedule denominator.
Only an official schedule/change/cancellation/sales-suspension notice published outside the same
OpenAPI delivery path qualifies as the independent denominator for `final`; API26 or API72 alone
does not.

## Exclusions

Public releases exclude:

- API credentials, GitHub Actions secrets, unredacted request URLs, and secret-bearing logs
- personal or local storage paths
- raw KRA website HTML, PDFs, images, logos, or other content without verified redistribution terms
- third-party data without an explicit compatible license

KRA web facts may be normalized only after the applicable terms and provenance are recorded. Raw
web material remains private and is removed under the retention rule in the collection plan unless
redistribution permission is confirmed.
