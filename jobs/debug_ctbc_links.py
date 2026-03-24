import os, sys, re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from extractor.ingest import fetch_with_playwright as fetch_with_cloudscraper

url = "https://www.ctbcbank.com/twrbo/zh_tw/cc_index/cc_product/cc_introduction_index.html"
print("Fetching...", url)
html = fetch_with_cloudscraper(url)
print(f"HTML length: {len(html)}")

t = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL)
print(f"Title: {t.group(1)[:100] if t else '(none)'}")

# All hrefs
hrefs = re.findall(r'href="([^"]+)"', html)
print(f"\nAll hrefs ({len(hrefs)} total), first 40:")
for h in hrefs[:40]:
    print(" ", h)

# Card-specific hrefs
for pattern in ["cc_introduction_index", "cc_product", "cc_index"]:
    matched = [h for h in hrefs if pattern in h]
    print(f"\nHrefs containing '{pattern}' ({len(matched)}):")
    for h in sorted(set(matched))[:30]:
        print(" ", h)

# First 2000 chars of body
print("\n--- First 2000 chars of HTML ---")
print(html[:2000])
