# IoTLT connpass 全イベント取得エージェント向け手順書

このリポジトリは、IoTLT の connpass グループページ（`https://iotlt.connpass.com/event/`）からイベント情報をスクレイピングし、Markdown テーブルとして保存するための作業一式です。

## 目的

- connpass 上の **全イベント** を取得して `data/iotlt_events.md` に書き出す
- 取得は **最古ページ `page=43` → 新しい方へ** の順で ID を採番（`1..`）
- スライド URL は **実際にアクセス可能なものだけ**を掲載（Not Found 等は除外）
- ツイートまとめ URL（Togetter/posfie 等）は **まとめページのみ**を掲載（画像 CDN などは除外）

## 重要な前提（制約）

- connpass API（`https://connpass.com/api/v1/...`）は環境によって 403 ブロックされることがあるため、基本は **HTML を `curl` で取得して解析**する。
- ネットワークアクセスが必要（多数のリクエストが発生）。

## 実装の入口

- スクレイパー: `scripts/scrape_iotlt_connpass.py`
- 出力: `data/iotlt_events.md`
- スライド検証キャッシュ: `data/slide_url_cache.json`

## 出力フォーマット（Markdown テーブル）

`data/iotlt_events.md` は以下の列で固定：

|列名|意味|
|---|---|
|id|`page=43` 側の最古イベントから順に採番（1,2,3...）|
|vol|タイトルから抽出した `vol.N`（抽出できない場合は空）|
|タイプ|`本体` / `〇〇IoTLT`（サブイベントは併記）/ その他|
|タイトル|connpass のイベントタイトル（テーブル崩れ防止のため `|` はエスケープ済み）|
|実施形態|`オンライン` / `対面` / `オンライン / 対面` / `未定`|
|会場名|connpass の会場名（DOMの `place_name`）|
|住所|connpass の住所（DOMの `adr`）|
|connpass URL|イベントページ URL|
|ツイートまとめ URL|Togetter/posfie 等の URL（複数は `<br>` 区切り）|
|LTスライド|Speaker Deck / SlideShare / Google Slides 等（有効なもののみ。複数は `<br>` 区切り）|
|参加者数|ページ上部の「参加者（XX人/名）」を優先。connpass 外申込は `0` 扱い|
|日付|`yyyy/mm/dd`|
|曜日|日本語の曜日（例: `月`）|
|時間|`HH:MM~HH:MM`（終了未取得時は `HH:MM~`）|

## 取得ロジック（要点）

### ID 採番・順序

- connpass の一覧ページは `page=43` が最古側。
- スクリプトはページ内のイベントを取得後、日付で昇順に整列して出力する。
- `--rebuild` では全イベントを集めて日付（＋時間）でソートし、`id=1..` を振り直す。

### vol 抽出

タイトルから以下を拾う（例）：

- `vol.93`, `Vol.6`, `IoTLTvol6`, `IoTLT vol.6`
- `IoTLT #1`（`vol.1` として扱う）
- `第N回`、`#N`

※ タイトルに `vol` 相当があるのに空になる場合は、正規表現を追加・調整すること。

### ツイートまとめ URL

- 対象ドメイン: `togetter.com` / `min.togetter.com` / `posfie.com` / `twilog.togetter.com`
- **Togetter はまとめページのみ**を採用（`/li/` または `/id/`）。`pimg.togetter.com` 等の画像/CDN系は除外。
- `t.co` など短縮 URL は `curl -I -L` 相当でリダイレクト解決してから判定する。

### LT スライド URL

- 対象: Speaker Deck / SlideShare / Google Slides（`/presentation/` のみ）
- URL が存在しても Not Found のことがあるため、HTTP で実アクセスして検証する。
- 検証結果は `data/slide_url_cache.json` にキャッシュして高速化する。

### 参加者数

- `参加者（XX人/名）` または `参加者一覧（XX人/名）` から抽出。
- connpass 外申込（「申し込み不要、もしくは当サイト以外で申し込み」等）イベントは connpass が人数を持たないため `0` とする。

### 実施形態（オンライン/対面）

会場名・住所に `オンライン` / `Zoom` / `配信` 等のキーワードがある場合にオンライン寄りと判定する。

## 実行手順

### フルリビルド（推奨）

スキーマ変更や抽出ロジック更新後は必ずリビルドする：

```sh
python3 scripts/scrape_iotlt_connpass.py --rebuild --start-page 43 --end-page 1 --out data/iotlt_events.md
```

### 追記（差分取得）

既存ファイルに追記する場合（既に書いた connpass URL はスキップ）：

```sh
python3 scripts/scrape_iotlt_connpass.py --start-page 43 --end-page 1 --limit 10000 --out data/iotlt_events.md
```

## QA（最低限の検証）

以下を満たすこと：

- 行数が `427`（connpass 側のイベント件数と一致）
- `id=1..427` の欠番・重複なし
- `connpass URL` が全行 `http` で始まる
- `曜日` と `時間` が空でない（空が出るなら抽出正規表現を修正）
- `vol` 抽出が明らかに欠けていない（タイトルに `vol` があるのに空、などを検出）

簡易チェック例（参考）：

```sh
python3 - <<'PY'
from pathlib import Path
p=Path('data/iotlt_events.md')
rows=[]
for l in p.read_text(encoding='utf-8').splitlines():
    if l.startswith('| ') and l.split('|')[1].strip().isdigit():
        rows.append([c.strip() for c in l.strip('|').split('|')])
print('rows',len(rows))
ids=[int(r[0]) for r in rows]
print('max_id',max(ids),'dupes',len(ids)-len(set(ids)))
bad=[r for r in rows if not r[7].startswith('http')]
print('bad_connpass_url',len(bad))
mv=[r for r in rows if r[1]=='' and 'vol' in r[3].lower()]
print('missing_vol_but_has_vol_in_title',len(mv))
PY
```

## 修正依頼が来たときの方針

- **一括リビルド**で再生成できる状態を維持する（小手先の手修正で合わせない）
- テーブル崩れ（`|`）や URL 誤抽出は最優先で潰す
- 取得不能フィールドがある場合は、例外で止めずに「空/0/未定」などの合意済みフォールバックを使う

