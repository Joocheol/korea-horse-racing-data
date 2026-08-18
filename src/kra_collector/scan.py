from __future__ import annotations

import argparse
import gzip
import os
from pathlib import Path

from .client import secret_fingerprints


def scan_tree(root: Path, secret: str) -> list[str]:
    fingerprints = secret_fingerprints(secret)
    findings: list[str] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        content = path.read_bytes()
        payloads = [content]
        if path.suffix == ".gz":
            try:
                payloads.append(gzip.decompress(content))
            except (OSError, EOFError):
                findings.append(f"invalid_gzip:{path.relative_to(root).as_posix()}")
                continue
        if any(token in payload for token in fingerprints for payload in payloads):
            findings.append(f"secret_detected:{path.relative_to(root).as_posix()}")
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan KRA artifacts for service-key variants"
    )
    parser.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    secret = os.environ.get("DATA_GO_KR_SERVICE_KEY")
    if not secret:
        raise SystemExit("DATA_GO_KR_SERVICE_KEY is required")
    findings = scan_tree(Path(args.root), secret)
    for finding in findings:
        print(finding)
    return 2 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
