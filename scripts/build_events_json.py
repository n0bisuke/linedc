#!/usr/bin/env python3
import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any, Optional


PREFECTURES: list[str] = [
    "北海道",
    "青森県",
    "岩手県",
    "宮城県",
    "秋田県",
    "山形県",
    "福島県",
    "茨城県",
    "栃木県",
    "群馬県",
    "埼玉県",
    "千葉県",
    "東京都",
    "神奈川県",
    "新潟県",
    "富山県",
    "石川県",
    "福井県",
    "山梨県",
    "長野県",
    "岐阜県",
    "静岡県",
    "愛知県",
    "三重県",
    "滋賀県",
    "京都府",
    "大阪府",
    "兵庫県",
    "奈良県",
    "和歌山県",
    "鳥取県",
    "島根県",
    "岡山県",
    "広島県",
    "山口県",
    "徳島県",
    "香川県",
    "愛媛県",
    "高知県",
    "福岡県",
    "佐賀県",
    "長崎県",
    "熊本県",
    "大分県",
    "宮崎県",
    "鹿児島県",
    "沖縄県",
]


TOKYO_WARDS = [
    "千代田区",
    "中央区",
    "港区",
    "新宿区",
    "文京区",
    "台東区",
    "墨田区",
    "江東区",
    "品川区",
    "目黒区",
    "大田区",
    "世田谷区",
    "渋谷区",
    "中野区",
    "杉並区",
    "豊島区",
    "北区",
    "荒川区",
    "板橋区",
    "練馬区",
    "足立区",
    "葛飾区",
    "江戸川区",
]


COORD_RE = re.compile(r"^\s*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*$")

CITY_TO_PREF: list[tuple[str, str]] = [
    ("札幌市", "北海道"),
    ("仙台市", "宮城県"),
    ("さいたま市", "埼玉県"),
    ("千葉市", "千葉県"),
    ("横浜市", "神奈川県"),
    ("川崎市", "神奈川県"),
    ("新潟市", "新潟県"),
    ("金沢市", "石川県"),
    ("名古屋市", "愛知県"),
    ("京都市", "京都府"),
    ("大阪市", "大阪府"),
    ("堺市", "大阪府"),
    ("神戸市", "兵庫県"),
    ("岡山市", "岡山県"),
    ("広島市", "広島県"),
    ("福岡市", "福岡県"),
    ("北九州市", "福岡県"),
    ("熊本市", "熊本県"),
    ("那覇市", "沖縄県"),
]


def _split_md_row(line: str) -> list[str]:
    """
    Split a markdown table row by `|`, respecting escaped pipes (`\\|`).
    """
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for ch in line.rstrip("\n"):
        if escaped:
            current.append(ch)
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == "|":
            cells.append("".join(current))
            current = []
            continue
        current.append(ch)
    cells.append("".join(current))

    # Trim leading/trailing empty cell caused by leading/trailing pipes.
    if cells and cells[0].strip() == "":
        cells = cells[1:]
    if cells and cells[-1].strip() == "":
        cells = cells[:-1]
    return [unescape(c.strip()).replace("\\|", "|") for c in cells]


def _split_urls(cell: str) -> list[str]:
    text = cell.strip()
    if not text:
        return []
    parts = re.split(r"(?:<br\s*/?>|\s+)", text, flags=re.IGNORECASE)
    urls = [p.strip() for p in parts if p.strip()]
    return urls


def _infer_prefecture(*, address: str, title: str, venue: str) -> Optional[str]:
    addr = (address or "").strip()
    ttl = (title or "").strip()
    vnm = (venue or "").strip()

    if not addr:
        return None

    if "オンライン" in addr:
        return None

    # Overseas / non-prefecture locations.
    if any(token in addr for token in ("深圳", "台北", "上海", "海外")):
        return None

    for pref in PREFECTURES:
        if pref in addr:
            return pref

    for city, pref in CITY_TO_PREF:
        if city in addr:
            return pref

    # Some rows omit "東京都" but include ward.
    if any(ward in addr for ward in TOKYO_WARDS):
        return "東京都"

    # Coordinate-only entries: use title/venue as hint.
    if COORD_RE.match(addr):
        for pref in PREFECTURES:
            if pref in ttl or pref in vnm:
                return pref
        if "東京" in ttl or "東京" in vnm:
            return "東京都"
        return None

    return None


def _infer_location_kind(*, address: str) -> str:
    addr = (address or "").strip()
    if not addr:
        return "unknown"
    if "オンライン" in addr:
        return "online"
    if any(token in addr for token in ("深圳", "台北", "上海")):
        return "overseas"
    if COORD_RE.match(addr):
        return "onsite"
    # Heuristic: if address contains a prefecture marker or ward/city names, treat as onsite.
    if any(pref in addr for pref in PREFECTURES) or "区" in addr or "市" in addr:
        return "onsite"
    return "unknown"


def _parse_date(date_str: str) -> Optional[str]:
    s = (date_str or "").strip()
    if not s:
        return None
    try:
        dt = datetime.strptime(s, "%Y/%m/%d")
    except ValueError:
        return s
    return dt.date().isoformat()


@dataclass(frozen=True)
class EventRow:
    id: int
    vol: str
    event_type: str
    title: str
    venue_name: str
    address: str
    connpass_url: str
    tweet_urls: list[str]
    slide_urls: list[str]
    participants: Optional[int]
    date: Optional[str]
    prefecture: Optional[str]
    location_kind: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "vol": self.vol,
            "type": self.event_type,
            "title": self.title,
            "venue_name": self.venue_name,
            "address": self.address,
            "connpass_url": self.connpass_url,
            "tweet_urls": self.tweet_urls,
            "slide_urls": self.slide_urls,
            "participants": self.participants,
            "date": self.date,
            "prefecture": self.prefecture,
            "location_kind": self.location_kind,
        }


def parse_events(markdown_path: Path) -> list[EventRow]:
    lines = markdown_path.read_text(encoding="utf-8").splitlines()
    events: list[EventRow] = []
    for line in lines:
        if not line.startswith("|"):
            continue
        if re.match(r"^\|\s*-", line):
            continue
        if "| id |" in line:
            continue
        cells = _split_md_row(line)
        if len(cells) == 11:
            (
                id_str,
                vol,
                event_type,
                title,
                venue_name,
                address,
                connpass_url,
                tweet_url_cell,
                slide_url_cell,
                participants_str,
                date_str,
            ) = cells
        elif len(cells) == 14:
            (
                id_str,
                vol,
                event_type,
                title,
                _mode,
                venue_name,
                address,
                connpass_url,
                tweet_url_cell,
                slide_url_cell,
                participants_str,
                date_str,
                _weekday,
                _time_range,
            ) = cells
        else:
            # Skip malformed rows instead of guessing.
            continue

        try:
            event_id = int(id_str)
        except ValueError:
            continue

        participants: Optional[int] = None
        if participants_str.strip():
            try:
                participants = int(participants_str)
            except ValueError:
                participants = None

        date = _parse_date(date_str)
        slide_urls = _split_urls(slide_url_cell)
        tweet_urls = _split_urls(tweet_url_cell)
        prefecture = _infer_prefecture(address=address, title=title, venue=venue_name)
        location_kind = _infer_location_kind(address=address)

        events.append(
            EventRow(
                id=event_id,
                vol=vol,
                event_type=event_type,
                title=title,
                venue_name=venue_name,
                address=address,
                connpass_url=connpass_url,
                tweet_urls=tweet_urls,
                slide_urls=slide_urls,
                participants=participants,
                date=date,
                prefecture=prefecture,
                location_kind=location_kind,
            )
        )

    events.sort(key=lambda e: e.id)
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--in", dest="input_path", default="data/linedc_events.md")
    parser.add_argument("--out", dest="output_path", default="docs/events.json")
    args = parser.parse_args()

    input_path = Path(args.input_path)
    output_path = Path(args.output_path)
    events = parse_events(input_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "generated_from": str(input_path.as_posix()),
                "event_count": len(events),
                "events": [e.as_dict() for e in events],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
