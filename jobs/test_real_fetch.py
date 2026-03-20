import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor import ingest


def _console_print(message: str) -> None:
    encoding = sys.stdout.encoding or "utf-8"
    safe_message = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe_message)


def main() -> int:
    urls = ingest.get_real_source_urls()
    _console_print(f"Testing {len(urls)} real source URL(s)...")

    for url in urls:
        _console_print(f"\n=== Fetching: {url}")
        html = ingest.fetch_real_page(url)
        summary = ingest.extract_page_summary(html)
        _console_print(summary)
        if len(html) < 1000:
            raise RuntimeError(f"Fetched content looks too small: {len(html)} bytes")

    _console_print("\nREAL FETCH STATUS: SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
