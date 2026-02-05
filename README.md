# connpass scraper (LINEDC)

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

ネットワーク制限などで `python3` 実行時に名前解決できない環境では、先に `curl` でHTMLを取得してからオフライン変換できます：

```sh
bash scripts/fetch_linedc_raw.sh data/raw/linedc
python3 scripts/scrape_linedc_connpass.py --raw-dir data/raw/linedc --rebuild --out data/linedc_events.md
```

## Visualization (都道府県マップ)

`data/linedc_events.md` を解析して、どの都道府県で開催したかを「日本地図（タイルマップ）」で可視化する静的サイトを `docs/` に置いています。

Generate JSON:

```sh
python3 scripts/build_events_json.py --in data/linedc_events.md --out docs/events.json
```

Run locally:

```sh
python3 -m http.server 8000 --directory docs
```

Open `http://localhost:8000/` to view.
