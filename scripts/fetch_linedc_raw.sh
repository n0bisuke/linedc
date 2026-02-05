#!/usr/bin/env bash
set -euo pipefail

RAW_DIR="${1:-data/raw/linedc}"
BASE_URL="https://linedevelopercommunity.connpass.com"

mkdir -p "${RAW_DIR}/list" "${RAW_DIR}/events"

echo "Fetching: ${BASE_URL} (raw -> ${RAW_DIR})" >&2
date "+%Y-%m-%d %H:%M:%S %z" > "${RAW_DIR}/fetched_at.txt"
echo "${BASE_URL}/event/" > "${RAW_DIR}/source_url.txt"

curl_fetch() {
  local url="$1"
  local out="${2:-}"
  local max_attempts="${3:-12}"

  local attempt=1
  while (( attempt <= max_attempts )); do
    if [[ -n "${out}" ]]; then
      if curl -L --max-time 25 --retry 2 --retry-all-errors --retry-delay 1 -sS "${url}" -o "${out}"; then
        return 0
      fi
    else
      if curl -L --max-time 25 --retry 2 --retry-all-errors --retry-delay 1 -sS "${url}"; then
        return 0
      fi
    fi

    local sleep_s=$(( attempt < 6 ? (2 ** attempt) : 30 ))
    echo "Retry (${attempt}/${max_attempts}) after ${sleep_s}s: ${url}" >&2
    sleep "${sleep_s}"
    attempt=$((attempt+1))
  done

  echo "Failed to fetch after ${max_attempts} attempts: ${url}" >&2
  return 1
}

probe_html="$(curl_fetch "${BASE_URL}/event/?page=999999")"
last_page="$(printf "%s" "${probe_html}" | python3 - <<'PY'
import re, sys
html=sys.stdin.read()
m=re.search(r'<li[^>]*class="active"[^>]*>\s*<span>\s*(\d+)\s*</span>', html)
if m:
    print(m.group(1))
    raise SystemExit(0)
pages=[int(x) for x in re.findall(r"[?&]page=(\d+)", html)]
if pages:
    print(max(pages))
    raise SystemExit(0)
raise SystemExit("could not detect last page")
PY
)"

echo "Detected last page: ${last_page}" >&2

tmp_urls="$(mktemp)"
trap 'rm -f "${tmp_urls}"' EXIT

for ((p=1; p<=last_page; p++)); do
  echo "List page ${p}/${last_page}" >&2
  html_path="${RAW_DIR}/list/page_${p}.html"
  curl_fetch "${BASE_URL}/event/?page=${p}" "${html_path}"
  python3 - <<'PY' "${html_path}" >> "${tmp_urls}"
import re, sys
path=sys.argv[1]
html=open(path,"r",encoding="utf-8",errors="ignore").read()
for href in re.findall(r'<a\s+class="url summary"\s+href="([^"]+)"', html):
    print(href.strip())
PY
done

sort -u "${tmp_urls}" > "${RAW_DIR}/event_urls.txt"
count="$(wc -l < "${RAW_DIR}/event_urls.txt" | tr -d ' ')"
echo "Detected event URLs: ${count}" >&2

idx=0
while IFS= read -r url; do
  idx=$((idx+1))
  event_id="$(printf "%s" "${url}" | python3 - <<'PY'
import re, sys
u=sys.stdin.read().strip()
m=re.search(r"/event/(\d+)/", u)
print(m.group(1) if m else "")
PY
)"
  if [[ -z "${event_id}" ]]; then
    continue
  fi
  out="${RAW_DIR}/events/${event_id}.html"
  if [[ -s "${out}" ]]; then
    continue
  fi
  echo "Event ${idx}/${count} id=${event_id}" >&2
  curl_fetch "${url}" "${out}"
done < "${RAW_DIR}/event_urls.txt"

echo "Done." >&2
