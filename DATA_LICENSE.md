# Data licensing and attribution

## Public OpenAPI data

The project obtains factual racing data from OpenAPI services provided by the Korea Racing
Authority through the Korean Public Data Portal. Each released dataset records the exact source
endpoint and the license/usage scope shown on that endpoint's official catalog page at collection
time.

The API160 catalog page verified on 2026-08-18 states that the service is free and its permitted
use scope is unrestricted. Other endpoints must be checked and recorded individually rather than
assuming that one endpoint's terms apply to every source.

Attribution used by this project:

> Source: Korea Racing Authority, Korean Public Data Portal (data.go.kr).

## Project code

Project-authored source code is intended to be released under the MIT License.

## Exclusions

The following are not included in public data releases:

- API credentials and GitHub Actions secrets
- personal/local storage paths
- raw KRA website HTML, PDFs, images, logos, or other website content whose redistribution terms
  have not been verified
- third-party data without an explicit compatible license

Extracted factual values from a KRA web page are published only after the applicable terms and
provenance have been recorded.
