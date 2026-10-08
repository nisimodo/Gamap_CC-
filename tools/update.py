#!/usr/bin/env python3
"""OneDrive の共有リンクから最新の xlsx を取得し、更新されていれば data/stores.js を作り直す

使い方:
    python3 tools/update.py            # 更新があるときだけ作り直す
    python3 tools/update.py --force    # 更新が無くても作り直す

共有リンクは tools/config.json の "shareUrl" に設定します。
OneDrive 個人用の共有リンクは、ブラウザと同じ匿名トークン（Badger トークン）を使ってダウンロードします。
Microsoft 側の仕様変更で取得できなくなった場合は、xlsx を手動でダウンロードして
    python3 tools/build_data.py <xlsxのパス>
を実行してください。
"""
import base64
import json
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CONFIG_PATH = TOOLS / "config.json"
STATE_PATH = TOOLS / "source_state.json"
XLSX_PATH = TOOLS / "source.xlsx"

TOKEN_URL = "https://api-badgerp.svc.ms/v1.0/token"
TOKEN_APP_ID = "5cbed6ac-a083-4e14-b191-b4ba07653de2"  # OneDrive Web が匿名アクセスに使う公開アプリ ID
API = "https://my.microsoftpersonalcontent.com/_api/v2.0/shares/{}/driveitem"
UA = "taiko-arcade-map/1.0"


def short_url(url):
    """onedrive.live.com の長い URL なら redeem パラメータから 1drv.ms の共有 URL を取り出す"""
    redeem = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("redeem")
    if redeem:
        b = redeem[0]
        return base64.urlsafe_b64decode(b + "=" * (-len(b) % 4)).decode()
    return url


def share_id(url):
    return "u!" + base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")


def request(url, headers=None, data=None):
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    return urllib.request.urlopen(req, timeout=120)


def get_token():
    body = json.dumps({"appId": TOKEN_APP_ID}).encode()
    with request(TOKEN_URL, {"Content-Type": "application/json"}, body) as r:
        return json.loads(r.read())["token"]


def main():
    sys.stdout.reconfigure(line_buffering=True)
    force = "--force" in sys.argv
    config = json.loads(CONFIG_PATH.read_text("utf-8"))
    sid = share_id(short_url(config["shareUrl"]))
    headers = {"Authorization": "Badger " + get_token(), "Prefer": "autoredeem"}

    with request(API.format(sid) + "?$select=name,size,lastModifiedDateTime,eTag", headers) as r:
        meta = json.loads(r.read())
    print(f"共有ファイル: {meta['name']}  更新日時 {meta['lastModifiedDateTime']}")

    state = json.loads(STATE_PATH.read_text("utf-8")) if STATE_PATH.exists() else {}
    if not force and state.get("eTag") == meta["eTag"]:
        print("更新はありません")
        return

    with request(API.format(sid) + "/content", headers) as r:
        XLSX_PATH.write_bytes(r.read())
    print(f"ダウンロードしました ({XLSX_PATH.stat().st_size:,} bytes)")

    subprocess.run([sys.executable, str(TOOLS / "build_data.py"), str(XLSX_PATH),
                    "--source-name", meta["name"], "--source-updated", meta["lastModifiedDateTime"]], check=True)
    STATE_PATH.write_text(json.dumps({k: meta[k] for k in ("name", "eTag", "lastModifiedDateTime")},
                                     ensure_ascii=False, indent=2), "utf-8")


if __name__ == "__main__":
    main()
