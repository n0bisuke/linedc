#!/usr/bin/env python3
import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urlparse


LIST_URL_TEMPLATE = "https://linedevelopercommunity.connpass.com/event/?page={page}"

TWEET_DOMAINS = {
    "togetter.com",
    "posfie.com",
    "min.togetter.com",
    "twilog.togetter.com",
}

SLIDE_DOMAINS = {
    "speakerdeck.com",
    "www.slideshare.net",
    "slideshare.net",
    "docs.google.com",
}

SHORTENER_DOMAINS = {
    "t.co",
    "bit.ly",
    "tinyurl.com",
    "goo.gl",
    "buff.ly",
    "ow.ly",
}

_URL_RE = re.compile(r"https?://[^\s\"'<>]+")
_BARE_URL_RE = re.compile(
    r"(?:(?<=\s)|(?<=\()|(?<=\[)|(?<=\{)|^)"
    r"((?:www\.)?(?:togetter\.com|posfie\.com|speakerdeck\.com|slideshare\.net|www\.slideshare\.net|docs\.google\.com)/[^\s\"'<>]+)"
)

_SLIDE_CACHE: dict[str, bool] = {}
_SLIDE_CACHE_PATH: Optional[Path] = None


def _load_slide_cache(path: Path) -> None:
    global _SLIDE_CACHE, _SLIDE_CACHE_PATH
    _SLIDE_CACHE_PATH = path
    if not path.exists():
        _SLIDE_CACHE = {}
        return
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        _SLIDE_CACHE = loaded if isinstance(loaded, dict) else {}
    except Exception:
        _SLIDE_CACHE = {}


def _save_slide_cache() -> None:
    if _SLIDE_CACHE_PATH is None:
        return
    _SLIDE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _SLIDE_CACHE_PATH.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(_SLIDE_CACHE, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp_path.replace(_SLIDE_CACHE_PATH)


def _run_curl(
    url: str,
    *,
    timeout_seconds: int = 30,
    head_only: bool = False,
    retries: int = 3,
) -> tuple[int, str, bytes]:
    """
    Returns (http_status, effective_url, body_bytes).
    Uses curl so we can rely on the caller's network settings.
    """
    marker = b"__CURLMETA__"
    cmd = ["curl", "-L", "--max-time", str(timeout_seconds), "-sS"]
    if head_only:
        cmd += ["-o", "/dev/null", "-w", marker.decode("ascii") + "%{http_code} %{url_effective}"]
    else:
        cmd += ["-o", "-", "-w", "\n" + marker.decode("ascii") + "%{http_code} %{url_effective}\n"]
    cmd.append(url)

    last_err: Optional[str] = None
    for attempt in range(max(1, retries + 1)):
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode == 0:
            raw = proc.stdout
            break
        last_err = proc.stderr.decode("utf-8", "ignore")
        # Small backoff for transient DNS / network failures.
        if attempt < retries:
            time.sleep(min(6, 1.0 * (2**attempt)))
            continue
        raise RuntimeError(f"curl failed ({proc.returncode}) for {url}: {last_err}")

    if head_only:
        meta = raw
        body = b""
    else:
        idx = raw.rfind(b"\n" + marker)
        if idx == -1:
            idx = raw.rfind(marker)
        if idx == -1:
            raise RuntimeError(f"unexpected curl output (no meta marker) for {url}")
        body = raw[:idx]
        meta = raw[idx:].strip()

    meta_text = meta.decode("utf-8", "ignore")
    m = re.search(r"__CURLMETA__(\d{3})\s+(\S+)", meta_text)
    if not m:
        raise RuntimeError(f"unexpected curl meta for {url}: {meta_text!r}")
    status = int(m.group(1))
    effective_url = m.group(2)
    return status, effective_url, body


def _extract_title_from_html(html: str) -> Optional[str]:
    m = re.search(r"<title>\s*(.*?)\s*</title>", html, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    return title or None


def is_valid_slide_url(url: str) -> bool:
    cached = _SLIDE_CACHE.get(url)
    if cached is not None:
        return bool(cached)
    try:
        cmd = [
            "curl",
            "-L",
            "--max-time",
            "18",
            "-sS",
            "--range",
            "0-50000",
            "-o",
            "-",
            "-w",
            "\n__CURLMETA__%{http_code} %{url_effective}\n",
            url,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            _SLIDE_CACHE[url] = False
            return False
        raw = proc.stdout
        idx = raw.rfind(b"\n__CURLMETA__")
        if idx == -1:
            _SLIDE_CACHE[url] = False
            return False
        body = raw[:idx]
        meta_text = raw[idx:].decode("utf-8", "ignore").strip()
        m = re.search(r"__CURLMETA__(\d{3})\s+(\S+)", meta_text)
        if not m:
            _SLIDE_CACHE[url] = False
            return False
        status = int(m.group(1))
    except Exception:
        _SLIDE_CACHE[url] = False
        return False

    if status != 200:
        _SLIDE_CACHE[url] = False
        return False

    try:
        text = body[:50000].decode("utf-8", "ignore")
    except Exception:
        _SLIDE_CACHE[url] = True
        return True

    title = _extract_title_from_html(text) or ""
    lowered = title.lower()
    if "not found" in lowered or "page not found" in lowered or "404" in lowered:
        _SLIDE_CACHE[url] = False
        return False
    if "ページが見つかりません" in title:
        _SLIDE_CACHE[url] = False
        return False

    snippet = re.sub(r"\s+", " ", text[:2000]).lower()
    if "404" in snippet and "not found" in snippet:
        _SLIDE_CACHE[url] = False
        return False

    _SLIDE_CACHE[url] = True
    return True


def _domain(url: str) -> str:
    try:
        return (urlparse(url).netloc or "").lower()
    except Exception:
        return ""


def _is_tweet_summary_url(url: str) -> bool:
    try:
        u = urlparse(url)
    except Exception:
        return False
    host = (u.netloc or "").lower()
    path = u.path or ""

    if host in {"togetter.com", "min.togetter.com"}:
        return path.startswith("/li/") or path.startswith("/id/")
    if host.endswith(".togetter.com"):
        return False

    if host == "posfie.com" or host.endswith(".posfie.com"):
        return True
    if host == "twilog.togetter.com":
        return True
    return False


class _ConnpassEventListParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.event_urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag != "a":
            return
        attr = dict(attrs)
        href = attr.get("href") or ""
        if attr.get("class") == "url summary" and href:
            self.event_urls.append(href)


@dataclass(frozen=True)
class EventRow:
    vol: str
    event_type: str
    title: str
    mode: str
    venue_name: str
    address: str
    connpass_url: str
    tweet_urls: list[str]
    slide_urls: list[str]
    participants: int
    date_yyyy_mm_dd: str
    weekday_ja: str
    time_range: str


def _clean_text(s: str) -> str:
    s = re.sub(r"[\x00-\x1f\x7f]", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _extract_between(html: str, start_pat: str, end_pat: str) -> Optional[str]:
    start = re.search(start_pat, html, re.IGNORECASE)
    if not start:
        return None
    end = re.search(end_pat, html[start.end() :], re.IGNORECASE)
    if not end:
        return None
    return html[start.end() : start.end() + end.start()]


def _extract_title(html: str) -> str:
    m = re.search(r'<div\s+class="current_event_title">\s*(.*?)\s*</div>', html, re.IGNORECASE | re.DOTALL)
    if m:
        return _clean_text(re.sub(r"<[^>]+>", "", m.group(1)))
    m = re.search(r"<title>\s*(.*?)\s*</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        return _clean_text(m.group(1))
    raise RuntimeError("could not extract event title")


def _extract_date(html: str) -> str:
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})\([^)]*\)", html)
    if not m:
        m = re.search(r"(\d{4})/(\d{2})/(\d{2})", html)
    if not m:
        raise RuntimeError("could not extract date")
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"


def _extract_weekday_and_timerange(html: str) -> tuple[str, str]:
    html = html.replace("&nbsp;", " ").replace("&#160;", " ")
    m = re.search(
        r"\d{4}/\d{2}/\d{2}\(([^)]+)\)\s*(\d{1,2}:\d{2})\s*(?:～|〜|-)\s*(\d{1,2}:\d{2})",
        html,
    )
    if m:
        weekday = _clean_text(m.group(1))
        time_range = f"{m.group(2)}~{m.group(3)}"
        return weekday, time_range

    m = re.search(r"\d{4}/\d{2}/\d{2}\(([^)]+)\)\s*(\d{1,2}:\d{2})", html)
    if m:
        weekday = _clean_text(m.group(1))
        return weekday, f"{m.group(2)}~"

    return "", ""


def _extract_participants(html: str) -> int:
    patterns = [
        r"参加者（\s*(\d+)\s*人）",
        r"参加者（\s*(\d+)\s*名）",
        r"参加者\s*[（(]\s*(\d+)\s*(?:人|名)\s*[）)]",
        r"参加者一覧（\s*(\d+)\s*(?:人|名)）",
        r"参加者一覧\s*[（(]\s*(\d+)\s*(?:人|名)\s*[）)]",
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return int(m.group(1))
    if "当サイト以外で申し込み" in html or "申し込み不要" in html:
        return 0
    raise RuntimeError("could not extract participants")


def _extract_place_name_and_address(html: str) -> tuple[str, str]:
    place_block = _extract_between(html, r'<p\s+class="place_name[^"]*">', r"</p>")
    if place_block is None:
        venue_name = ""
    else:
        venue_name = _clean_text(re.sub(r"<[^>]+>", "", place_block))

    adr_block = _extract_between(html, r'<p\s+class="adr">', r"</p>")
    if adr_block is None:
        address = ""
    else:
        address = _clean_text(re.sub(r"<[^>]+>", "", adr_block))
    return venue_name, address


def _infer_mode(venue_name: str, address: str) -> str:
    venue = (venue_name or "").strip()
    adr = (address or "").strip()
    combined = f"{venue} {adr}"

    online_keywords = ["オンライン", "Zoom", "Teams", "Google Meet", "YouTube", "配信", "ウェビナー"]
    is_online = any(k in combined for k in online_keywords)

    if venue == "未定" and not adr:
        return "未定"
    if is_online and adr and adr != "オンライン":
        return "オンライン / 対面"
    if is_online or venue == "オンライン" or adr == "オンライン":
        return "オンライン"
    if adr:
        return "対面"
    return "未定"


def _normalize_candidate_url(raw: str) -> Optional[str]:
    raw = (raw or "").strip()
    raw = raw.strip("<>\"'")
    raw = raw.rstrip(").,;]")
    if not raw:
        return None
    if raw.startswith("//"):
        return "https:" + raw
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw
    if raw.startswith("www."):
        return "https://" + raw
    if re.match(r"^(togetter\.com|posfie\.com|speakerdeck\.com|slideshare\.net|www\.slideshare\.net|docs\.google\.com)/", raw):
        return "https://" + raw
    return None


def _extract_links(html: str) -> list[str]:
    hrefs = re.findall(r'<a\s+[^>]*href="([^"]+)"', html, re.IGNORECASE)
    hrefs += _URL_RE.findall(html)
    hrefs += _BARE_URL_RE.findall(html)
    out: list[str] = []
    seen: set[str] = set()
    for href in hrefs:
        href = _normalize_candidate_url(href) or ""
        if not href:
            continue
        if href.startswith("#"):
            continue
        if href.startswith("javascript:"):
            continue
        if href in seen:
            continue
        seen.add(href)
        out.append(href)
    return out


def _infer_type_and_vol(title: str) -> tuple[str, str]:
    vol = ""
    patterns = [
        r"vol\.?\s*(\d+)",
        r"(?:^|[^\w])#\s*(\d+)\b",
        r"第\s*(\d+)\s*(?:回|回目)",
    ]
    for pat in patterns:
        m = re.search(pat, title, re.IGNORECASE)
        if m:
            vol = f"vol.{m.group(1)}"
            break

    lowered = (title or "").lower()
    if "lunch time input" in lowered:
        return "Lunch Time Input", vol
    if "lt" in lowered and ("大会" in title or "lt大会" in lowered):
        return "LT大会", vol
    if "ハンズオン" in title:
        return "ハンズオン", vol
    return "本体", vol


def _event_row_from_html(
    html: str,
    *,
    url: str,
    validate_slides: bool,
    resolve_shorteners: bool,
    participants_override: Optional[int] = None,
    allow_missing_participants: bool = False,
) -> EventRow:
    try:
        title = _extract_title(html)
        event_type, vol = _infer_type_and_vol(title)
        date = _extract_date(html)
        weekday, time_range = _extract_weekday_and_timerange(html)
        participants: Optional[int] = participants_override
        if participants is None:
            try:
                participants = _extract_participants(html)
            except RuntimeError:
                participants = None
        if participants is None:
            if allow_missing_participants:
                participants = 0
            else:
                raise RuntimeError("could not extract participants")
        venue_name, address = _extract_place_name_and_address(html)
        mode = _infer_mode(venue_name, address)
    except Exception as e:
        raise RuntimeError(f"{e} (url={url})") from e

    links = _extract_links(html)
    tweet_urls: list[str] = []
    slide_urls_raw: list[str] = []
    for link in links:
        d = _domain(link)
        if resolve_shorteners and d in SHORTENER_DOMAINS:
            try:
                _st, effective, _b = _run_curl(link, timeout_seconds=12, head_only=True)
                link = effective
                d = _domain(link)
            except Exception:
                pass
        if _is_tweet_summary_url(link):
            tweet_urls.append(link)
            continue
        if any(d == sd or d.endswith("." + sd) for sd in SLIDE_DOMAINS):
            if d == "docs.google.com" and "/presentation/" not in link:
                continue
            slide_urls_raw.append(link)

    if validate_slides:
        slide_urls: list[str] = []
        for link in slide_urls_raw:
            if is_valid_slide_url(link):
                slide_urls.append(link)
    else:
        # Fast path: skip HTTP validation to keep full rebuilds practical.
        slide_urls = list(dict.fromkeys(slide_urls_raw))

    return EventRow(
        vol=vol,
        event_type=event_type,
        title=title,
        mode=mode,
        venue_name=venue_name,
        address=address,
        connpass_url=url,
        tweet_urls=tweet_urls,
        slide_urls=slide_urls,
        participants=participants,
        date_yyyy_mm_dd=date,
        weekday_ja=weekday,
        time_range=time_range,
    )


def _event_row_from_url(url: str, *, validate_slides: bool) -> EventRow:
    status, _effective, body = _run_curl(url, timeout_seconds=25, head_only=False)
    if status != 200:
        raise RuntimeError(f"unexpected status {status} for {url}")
    html = body.decode("utf-8", "ignore")

    try:
        return _event_row_from_html(
            html,
            url=url,
            validate_slides=validate_slides,
            resolve_shorteners=True,
        )
    except RuntimeError as e:
        if "could not extract participants" not in str(e):
            raise

    p_status, _p_eff, p_body = _run_curl(url.rstrip("/") + "/participation/", timeout_seconds=25, head_only=False)
    if p_status != 200:
        raise RuntimeError(f"could not extract participants (status={p_status}) (url={url})")
    p_html = p_body.decode("utf-8", "ignore")
    participants = _extract_participants(p_html)
    return _event_row_from_html(
        html,
        url=url,
        validate_slides=validate_slides,
        resolve_shorteners=True,
        participants_override=participants,
    )


def _event_urls_from_list_page(page: int) -> list[str]:
    list_url = LIST_URL_TEMPLATE.format(page=page)
    status, _effective, body = _run_curl(list_url, timeout_seconds=30, head_only=False)
    if status != 200:
        raise RuntimeError(f"unexpected status {status} for list page {list_url}")

    html = body.decode("utf-8", "ignore")
    p = _ConnpassEventListParser()
    p.feed(html)

    seen: set[str] = set()
    urls: list[str] = []
    for u in p.event_urls:
        if u in seen:
            continue
        seen.add(u)
        urls.append(u)
    return urls


def _try_event_urls_from_list_page(page: int) -> list[str]:
    try:
        return _event_urls_from_list_page(page)
    except Exception:
        return []


def _detect_oldest_page() -> int:
    """
    connpass group pages don't always show a link to the last page, and
    out-of-range pages may render the last page's content while keeping the
    requested `?page=` in the URL.

    Strategy: fetch a very large page number and read the "active" page number
    from the pagination, which represents the actual last page.
    """
    status, _effective, body = _run_curl(LIST_URL_TEMPLATE.format(page=999999), timeout_seconds=20, head_only=False)
    if status != 200:
        raise RuntimeError("could not detect oldest page (non-200 on probe)")

    html = body.decode("utf-8", "ignore")
    m = re.search(r'<li[^>]*class="active"[^>]*>\s*<span>\s*(\d+)\s*</span>', html)
    if m:
        return int(m.group(1))

    # Fallback: use maximum page number visible in pagination links.
    pages = [int(x) for x in re.findall(r"[?&]page=(\d+)", html)]
    if pages:
        return max(pages)

    raise RuntimeError("could not detect oldest page (no pagination found)")


def _ensure_table_header(path: Path) -> None:
    if path.exists() and path.read_text(encoding="utf-8").strip():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "| id | vol | タイプ | タイトル | 実施形態 | 会場名 | 住所 | connpass URL | ツイートまとめ URL | LTスライド | 参加者数 | 日付 | 曜日 | 時間 |\n"
        "|---:|:---:|:---|:---|:---:|:---|:---|:---|:---|:---|---:|:---:|:---:|:---:|\n",
        encoding="utf-8",
    )


def _next_id_from_file(path: Path) -> int:
    if not path.exists():
        return 1
    max_id = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if not cols:
            continue
        try:
            v = int(cols[0])
        except Exception:
            continue
        max_id = max(max_id, v)
    return max_id + 1


def _existing_connpass_urls(path: Path) -> set[str]:
    if not path.exists():
        return set()
    urls: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 8:
            continue
        url = cols[7]
        if url.startswith("http"):
            urls.add(url)
    return urls


def _format_cell_links(urls: Iterable[str]) -> str:
    urls = list(urls)
    if not urls:
        return ""
    return "<br>".join(urls)


def _md_escape_cell(s: str) -> str:
    s = (s or "").replace("\r\n", "\n").replace("\r", "\n").replace("\n", " ")
    return s.replace("|", "&#124;").strip()


def append_rows(path: Path, rows: list[EventRow], start_id: int) -> None:
    lines: list[str] = []
    for idx, row in enumerate(rows):
        row_id = start_id + idx
        tweet_cell = _md_escape_cell(_format_cell_links(row.tweet_urls))
        slide_cell = _md_escape_cell(_format_cell_links(row.slide_urls))
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row_id),
                    _md_escape_cell(row.vol),
                    _md_escape_cell(row.event_type),
                    _md_escape_cell(row.title),
                    _md_escape_cell(row.mode),
                    _md_escape_cell(row.venue_name),
                    _md_escape_cell(row.address),
                    _md_escape_cell(row.connpass_url),
                    tweet_cell,
                    slide_cell,
                    str(row.participants),
                    row.date_yyyy_mm_dd,
                    _md_escape_cell(row.weekday_ja),
                    _md_escape_cell(row.time_range),
                ]
            )
            + " |\n"
        )
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start-page", type=int, default=0, help="oldest list page to start from (0=auto-detect)")
    ap.add_argument("--end-page", type=int, default=None, help="end page (inclusive). If omitted, only start-page is processed.")
    ap.add_argument("--limit", type=int, default=5, help="number of NEW events to append")
    ap.add_argument("--out", type=str, default="data/linedc_events.md", help="output markdown file")
    ap.add_argument("--slide-cache", type=str, default="data/slide_url_cache.json", help="JSON cache for slide URL validation")
    ap.add_argument("--validate-slides", action="store_true", help="validate slide URLs by HTTP access (slow)")
    ap.add_argument("--raw-dir", type=str, default=None, help="offline mode: directory containing event_urls.txt and events/*.html")
    ap.add_argument("--sleep", type=float, default=0.0, help="sleep seconds between requests (politeness)")
    ap.add_argument("--rebuild", action="store_true", help="rebuild the markdown from scratch (overwrites --out)")
    args = ap.parse_args(argv)

    out_path = Path(args.out)
    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    sleep_s = max(0.0, float(args.sleep or 0.0))

    if raw_dir is not None and not args.rebuild:
        raise RuntimeError("--raw-dir requires --rebuild")

    if args.validate_slides:
        _load_slide_cache(Path(args.slide_cache))

    start_page = args.start_page
    if raw_dir is None and start_page == 0:
        start_page = _detect_oldest_page()

    end_page = (1 if args.rebuild and args.end_page is None else start_page) if args.end_page is None else args.end_page
    if end_page > start_page:
        raise RuntimeError("--end-page must be <= --start-page")

    if args.rebuild:
        if raw_dir is not None:
            urls_path = raw_dir / "event_urls.txt"
            if not urls_path.exists():
                raise RuntimeError(f"missing {urls_path}")
            urls = [u.strip() for u in urls_path.read_text(encoding="utf-8").splitlines() if u.strip()]

            all_rows: list[EventRow] = []
            for u in urls:
                m = re.search(r"/event/(\\d+)/", u)
                if not m:
                    continue
                html_path = raw_dir / "events" / f"{m.group(1)}.html"
                if not html_path.exists():
                    continue
                html = html_path.read_text(encoding="utf-8", errors="ignore")
                all_rows.append(
                    _event_row_from_html(
                        html,
                        url=u,
                        validate_slides=False,
                        resolve_shorteners=False,
                        allow_missing_participants=True,
                    )
                )
                if sleep_s:
                    time.sleep(sleep_s)

            all_rows.sort(key=lambda r: (r.date_yyyy_mm_dd, r.time_range, r.connpass_url))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text("", encoding="utf-8")
            _ensure_table_header(out_path)
            append_rows(out_path, all_rows, 1)
            return 0

        all_rows: list[EventRow] = []
        seen_urls: set[str] = set()
        for page in range(start_page, end_page - 1, -1):
            urls = _event_urls_from_list_page(page)
            if not urls:
                raise RuntimeError(f"no event URLs found on page={page}")
            if sleep_s:
                time.sleep(sleep_s)
            for u in urls:
                if u in seen_urls:
                    continue
                seen_urls.add(u)
                all_rows.append(_event_row_from_url(u, validate_slides=args.validate_slides))
                if sleep_s:
                    time.sleep(sleep_s)
            if args.validate_slides:
                _save_slide_cache()

        all_rows.sort(key=lambda r: (r.date_yyyy_mm_dd, r.time_range, r.connpass_url))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8")
        _ensure_table_header(out_path)
        append_rows(out_path, all_rows, 1)
        if args.validate_slides:
            _save_slide_cache()
        return 0

    _ensure_table_header(out_path)
    next_id = _next_id_from_file(out_path)
    existing_urls = _existing_connpass_urls(out_path)

    remaining = args.limit
    current_id = next_id
    for page in range(start_page, end_page - 1, -1):
        if remaining <= 0:
            break

        urls = _event_urls_from_list_page(page)
        if not urls:
            raise RuntimeError(f"no event URLs found on page={page}")
        if sleep_s:
            time.sleep(sleep_s)

        rows: list[EventRow] = []
        for u in urls:
            if u in existing_urls:
                continue
            rows.append(_event_row_from_url(u, validate_slides=args.validate_slides))
            if sleep_s:
                time.sleep(sleep_s)
        rows.sort(key=lambda r: (r.date_yyyy_mm_dd, r.connpass_url))

        rows = rows[:remaining]
        if rows:
            append_rows(out_path, rows, current_id)
            for r in rows:
                existing_urls.add(r.connpass_url)
            current_id += len(rows)
            remaining -= len(rows)
            if args.validate_slides:
                _save_slide_cache()

    if args.validate_slides:
        _save_slide_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
