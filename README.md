# connpass scraper (IoTLT / LINEDC)

connpass のグループページからイベント情報を取得し、Markdown テーブルに保存します。

## IoTLT

Run (needs network access):
```sh
python3 scripts/scrape_iotlt_connpass.py --start-page 43 --limit 5 --out data/iotlt_events.md
```

Continue appending (script skips already-written connpass URLs):

```sh
# append next 20 events, starting from the oldest pages
python3 scripts/scrape_iotlt_connpass.py --start-page 43 --end-page 1 --limit 20 --out data/iotlt_events.md
```

Rebuild from scratch (recommended when schema changes):

```sh
python3 scripts/scrape_iotlt_connpass.py --rebuild --start-page 43 --end-page 1 --out data/iotlt_events.md
```

## LINEDC

`--start-page 0`（デフォルト）で「最古のページ番号」を自動検出します。

```sh
# full rebuild
python3 scripts/scrape_linedc_connpass.py --rebuild --out data/linedc_events.md
```

```sh
# append (skips already-written connpass URLs)
python3 scripts/scrape_linedc_connpass.py --limit 20 --out data/linedc_events.md
```

## Visualization (都道府県マップ)

`data/iotlt_events.md` を解析して、どの都道府県で開催したかを「日本地図（タイルマップ）」で可視化する静的サイトを `web/` に置いています。

Generate JSON:

```sh
python3 scripts/build_events_json.py --in data/iotlt_events.md --out web/events.json
python3 scripts/build_events_json.py --in data/linedc_events.md --out web/events_linedc.json
```

Run locally:

```sh
python3 -m http.server 8000 --directory web
```

Open:

- `http://localhost:8000/` (IoTLT)
- `http://localhost:8000/linedc.html` (LINEDC)
