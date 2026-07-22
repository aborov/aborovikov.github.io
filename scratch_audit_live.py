#!/usr/bin/env python3
import urllib.request
import urllib.parse
import re
import json
from html.parser import HTMLParser

BASE_URL = "https://aborovikov.com"

PAGES_TO_TEST = [
    "https://aborovikov.com/",
    "https://film.aborovikov.com/",
    "https://dev.aborovikov.com/",
    "https://brother.aborovikov.com/",
    "https://aborovikov.com/ccc/",
    "https://aborovikov.com/musician/",
    "https://aborovikov.com/musician-ru/",
]

class LivePageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.meta_desc = ""
        self.canonical = ""
        self.in_title = False
        self.schemas = []
        self.in_schema = False
        self.schema_buf = ""
        self.links = []
        self.images = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == 'title':
            self.in_title = True
        elif tag == 'meta':
            name = attrs_dict.get('name', '').lower()
            if name == 'description':
                self.meta_desc = attrs_dict.get('content', '')
        elif tag == 'link':
            rel = attrs_dict.get('rel', '').lower()
            if rel == 'canonical':
                self.canonical = attrs_dict.get('href', '')
        elif tag == 'a':
            href = attrs_dict.get('href')
            if href:
                self.links.append(href)
        elif tag == 'img':
            src = attrs_dict.get('src')
            if src:
                self.images.append(src)
        elif tag == 'script':
            stype = attrs_dict.get('type', '').lower()
            if stype == 'application/ld+json':
                self.in_schema = True
                self.schema_buf = ""

    def handle_endtag(self, tag):
        if tag == 'title':
            self.in_title = False
        elif tag == 'script' and self.in_schema:
            self.in_schema = False
            self.schemas.append(self.schema_buf)

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif self.in_schema:
            self.schema_buf += data

print("=== LIVE SITE AUDIT ===")

headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 1. Sitemap & Robots.txt Check
for asset_path in ['/robots.txt', '/sitemap.xml']:
    url = BASE_URL + asset_path
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            print(f"\n[OK] {url} -> HTTP {res.status} ({len(res.read())} bytes)")
    except Exception as e:
        print(f"\n[ERROR] {url} -> {e}")

# 2. Audit Each Live Page
broken_links_found = []
large_images_found = []
schema_errors_found = []

for page_url in PAGES_TO_TEST:
    print(f"\n--------------------------------------------------")
    print(f"Auditing Live Page: {page_url}")
    print(f"--------------------------------------------------")
    req = urllib.request.Request(page_url, headers=headers)
    try:
        with urllib.request.urlopen(req) as res:
            status = res.status
            html_content = res.read().decode('utf-8', errors='ignore')
            print(f"Status: HTTP {status} | Size: {len(html_content)} bytes")
    except Exception as e:
        print(f"HTTP ERROR accessing {page_url}: {e}")
        continue

    parser = LivePageParser()
    parser.feed(html_content)
    
    title = parser.title.strip()
    print(f"  Title ({len(title)} chars): {title}")
    
    desc = parser.meta_desc.strip()
    desc_status = "OK" if len(desc) <= 160 else "TOO LONG (>160)"
    print(f"  Meta Description ({len(desc)} chars - {desc_status}): {desc}")
    
    print(f"  Canonical Tag: {parser.canonical}")
    
    # Check Schemas
    print(f"  JSON-LD Schemas ({len(parser.schemas)}):")
    for i, s_str in enumerate(parser.schemas):
        try:
            s_json = json.loads(s_str)
            print(f"    Schema #{i+1}: Valid JSON | @type={s_json.get('@type', 'Graph/Multiple')}")
        except Exception as err:
            print(f"    Schema #{i+1}: INVALID JSON ({err})")
            schema_errors_found.append((page_url, str(err)))

    # Check Page Images
    for img_src in parser.images:
        abs_img_url = urllib.parse.urljoin(page_url, img_src)
        img_req = urllib.request.Request(abs_img_url, headers=headers, method='HEAD')
        try:
            with urllib.request.urlopen(img_req) as img_res:
                content_length = int(img_res.headers.get('Content-Length', 0))
                size_kb = content_length / 1024
                if size_kb > 500:
                    print(f"    [WARN] Image too large: {abs_img_url} ({size_kb:.1f} KB)")
                    large_images_found.append((abs_img_url, size_kb))
        except Exception as e:
            # Retry with GET if HEAD fails
            try:
                g_req = urllib.request.Request(abs_img_url, headers=headers)
                with urllib.request.urlopen(g_req) as g_res:
                    content_length = len(g_res.read())
                    size_kb = content_length / 1024
                    if size_kb > 500:
                        print(f"    [WARN] Image too large: {abs_img_url} ({size_kb:.1f} KB)")
                        large_images_found.append((abs_img_url, size_kb))
            except Exception as get_err:
                print(f"    [ERROR] Image failed to load: {abs_img_url} ({get_err})")

    # Check Internal Links
    for link_href in parser.links:
        if link_href.startswith(('mailto:', 'tel:', 'javascript:', '#')):
            continue
        abs_link_url = urllib.parse.urljoin(page_url, link_href)
        # Only test links on domain aborovikov.com
        if 'aborovikov.com' in urllib.parse.urlparse(abs_link_url).netloc:
            link_req = urllib.request.Request(abs_link_url, headers=headers, method='HEAD')
            try:
                with urllib.request.urlopen(link_req) as l_res:
                    if l_res.status >= 400:
                        print(f"    [BROKEN LINK] {link_href} -> HTTP {l_res.status}")
                        broken_links_found.append((page_url, link_href, l_res.status))
            except urllib.error.HTTPError as he:
                print(f"    [BROKEN LINK] {link_href} on [{page_url}] -> HTTP {he.code}")
                broken_links_found.append((page_url, link_href, he.code))
            except Exception as l_err:
                pass

print("\n==================================================")
print("AUDIT RESULTS SUMMARY")
print("==================================================")
print(f"Large Images (>500KB): {len(large_images_found)}")
print(f"Broken Internal Links (4x/5xx): {len(broken_links_found)}")
print(f"Schema Validation Errors: {len(schema_errors_found)}")
