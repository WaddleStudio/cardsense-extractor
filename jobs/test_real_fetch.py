import os
import sys

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.append(project_root)

from extractor import ingest


def main() -> int:
    urls = ingest.get_real_source_urls()
    print(f"Testing {len(urls)} real source URL(s)...")

    for url in urls:
        print(f"\n=== Fetching: {url}")
        html = ingest.fetch_real_page(url)
        summary = ingest.extract_page_summary(html)
        print(summary)
        if len(html) < 5000:
            raise RuntimeError(f"Fetched content looks too small: {len(html)} bytes")

    print("\nREAL FETCH STATUS: SUCCESS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
