#!/usr/bin/env python3
"""YouTube チャンネルの毎日のデータ収集スクリプト.

GitHub Actions から1日1回実行される。
  1. OAuth リフレッシュトークンでアクセストークンを取得
  2. YouTube Data API（登録者数・動画ごとの再生数など）を取得
  3. YouTube Analytics API（YouTube Studio と同じ詳細データ）を取得
  4. 過去の履歴とマージし、アドバイスを生成
  5. パスワードで暗号化して docs/data/history.enc に保存

必要な環境変数（GitHub Secrets）:
  YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN, DASHBOARD_PASSWORD
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from advice import build_advice  # noqa: E402
from crypto import decrypt_json, encrypt_json  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "docs" / "data" / "history.enc"
JST = dt.timezone(dt.timedelta(hours=9))

DATA_API = "https://www.googleapis.com/youtube/v3"
ANALYTICS_API = "https://youtubeanalytics.googleapis.com/v2/reports"


# ---------------------------------------------------------------- HTTP helpers
def http_json(url: str, *, token: str | None = None, data: dict | None = None) -> dict:
    headers = {"Accept": "application/json"}
    body = None
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} for {url.split('?')[0]}: {detail[:500]}") from None


def access_token() -> str:
    res = http_json(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": os.environ["YT_CLIENT_ID"],
            "client_secret": os.environ["YT_CLIENT_SECRET"],
            "refresh_token": os.environ["YT_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
    )
    return res["access_token"]


def data_api(token: str, path: str, **params) -> dict:
    return http_json(f"{DATA_API}/{path}?{urllib.parse.urlencode(params)}", token=token)


def analytics(token: str, start: str, end: str, metrics: str, **params) -> list[dict]:
    q = {"ids": "channel==MINE", "startDate": start, "endDate": end, "metrics": metrics, **params}
    res = http_json(f"{ANALYTICS_API}?{urllib.parse.urlencode(q)}", token=token)
    cols = [h["name"] for h in res.get("columnHeaders", [])]
    return [dict(zip(cols, row)) for row in res.get("rows", []) or []]


def safe_analytics(label: str, *args, **kwargs) -> list[dict] | None:
    """失敗しても全体を止めない（一部のレポートはチャンネル規模で取得できないことがある）."""
    try:
        return analytics(*args, **kwargs)
    except RuntimeError as e:
        print(f"[warn] {label}: {e}", file=sys.stderr)
        return None


# ---------------------------------------------------------------- utilities
def iso_duration_seconds(s: str) -> int:
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", s or "")
    if not m:
        return 0
    d, h, mi, se = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + se


def is_short(video_id: str, duration_s: int) -> bool:
    """/shorts/URL がリダイレクトされなければショート動画."""
    if duration_s > 180:
        return False
    req = urllib.request.Request(f"https://www.youtube.com/shorts/{video_id}", method="HEAD")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return e.code == 200
    except Exception:
        return duration_s <= 60


def merge_by_key(old: list[dict], new: list[dict], key: str) -> list[dict]:
    merged = {r[key]: r for r in old}
    for r in new:
        merged[r[key]] = r
    return [merged[k] for k in sorted(merged)]


# ---------------------------------------------------------------- collection
def collect(history: dict) -> dict:
    token = access_token()
    today = dt.datetime.now(JST).date()
    today_s = today.isoformat()

    # --- チャンネル基本情報
    ch = data_api(token, "channels", part="snippet,statistics,contentDetails", mine="true")["items"][0]
    stats = ch["statistics"]
    history["channel"] = {
        "id": ch["id"],
        "title": ch["snippet"]["title"],
        "thumbnail": ch["snippet"]["thumbnails"].get("default", {}).get("url"),
        "publishedAt": ch["snippet"]["publishedAt"],
    }
    snap = {
        "date": today_s,
        "subscribers": int(stats.get("subscriberCount", 0)),
        "views": int(stats.get("viewCount", 0)),
        "videos": int(stats.get("videoCount", 0)),
    }
    history["snapshots"] = merge_by_key(history.get("snapshots", []), [snap], "date")

    # --- 全動画の一覧と統計
    uploads = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    ids, page = [], None
    while True:
        params = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
        if page:
            params["pageToken"] = page
        res = data_api(token, "playlistItems", **params)
        ids += [it["contentDetails"]["videoId"] for it in res.get("items", [])]
        page = res.get("nextPageToken")
        if not page:
            break

    videos = history.setdefault("videos", {})
    vsnaps = history.setdefault("videoSnapshots", {})
    for i in range(0, len(ids), 50):
        res = data_api(token, "videos", part="snippet,statistics,contentDetails,status",
                       id=",".join(ids[i:i + 50]))
        for v in res.get("items", []):
            vid = v["id"]
            dur = iso_duration_seconds(v["contentDetails"].get("duration", ""))
            prev = videos.get(vid, {})
            st = v["statistics"]
            videos[vid] = {
                "title": v["snippet"]["title"],
                "publishedAt": v["snippet"]["publishedAt"],
                "duration": dur,
                "privacy": v["status"].get("privacyStatus"),
                "short": prev["short"] if "short" in prev else is_short(vid, dur),
                "views": int(st.get("viewCount", 0)),
                "likes": int(st.get("likeCount", 0)),
                "comments": int(st.get("commentCount", 0)),
            }
            rows = [r for r in vsnaps.get(vid, []) if r[0] != today_s]
            rows.append([today_s, videos[vid]["views"], videos[vid]["likes"], videos[vid]["comments"]])
            vsnaps[vid] = rows
    for vid in list(videos):
        if vid not in ids:
            videos[vid]["removed"] = True

    # --- YouTube Analytics（Studio データ）
    a = history.setdefault("analytics", {})
    end = today_s
    ch_start = history["channel"]["publishedAt"][:10]
    d28 = (today - dt.timedelta(days=28)).isoformat()
    d90 = (today - dt.timedelta(days=90)).isoformat()
    d365 = (today - dt.timedelta(days=365)).isoformat()

    # 日別：初回はチャンネル開設日から、それ以降は直近45日（確定値で上書き）
    start = ch_start if not a.get("daily") else (today - dt.timedelta(days=45)).isoformat()
    daily = analytics(
        token, start, end,
        "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
        "subscribersGained,subscribersLost,likes,comments,shares",
        dimensions="day", sort="day",
    )
    a["daily"] = merge_by_key(a.get("daily", []), daily, "day")

    def per_video(since: str) -> list[dict] | None:
        return safe_analytics(
            "per-video", token, since, end,
            "views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
            "subscribersGained,likes,comments,shares",
            dimensions="video", sort="-views", maxResults=200,
        )

    for key, since in (("videos28", d28), ("videos90", d90), ("videosLifetime", ch_start)):
        rows = per_video(since)
        if rows is not None:
            a[key] = rows

    reports = {
        "traffic28": dict(metrics="views,estimatedMinutesWatched", dimensions="insightTrafficSourceType", sort="-views", since=d28),
        "traffic365": dict(metrics="views,estimatedMinutesWatched", dimensions="insightTrafficSourceType", sort="-views", since=d365),
        "searchTerms28": dict(metrics="views", dimensions="insightTrafficSourceDetail", filters="insightTrafficSourceType==YT_SEARCH", sort="-views", maxResults=25, since=d28),
        "contentType28": dict(metrics="views,estimatedMinutesWatched,subscribersGained", dimensions="creatorContentType", since=d28),
        "contentType365": dict(metrics="views,estimatedMinutesWatched,subscribersGained", dimensions="creatorContentType", since=d365),
        "subscribed28": dict(metrics="views,estimatedMinutesWatched", dimensions="subscribedStatus", since=d28),
        "countries90": dict(metrics="views,estimatedMinutesWatched", dimensions="country", sort="-views", maxResults=15, since=d90),
        "devices90": dict(metrics="views", dimensions="deviceType", sort="-views", since=d90),
        "demographics365": dict(metrics="viewerPercentage", dimensions="ageGroup,gender", since=d365),
    }
    for key, spec in reports.items():
        since = spec.pop("since")
        rows = safe_analytics(key, token, since, end, spec.pop("metrics"), **spec)
        if rows is not None:
            a[key] = rows

    history["updatedAt"] = dt.datetime.now(JST).isoformat(timespec="minutes")
    return history


def main() -> None:
    password = os.environ["DASHBOARD_PASSWORD"]
    history: dict = {}
    if DATA_FILE.exists():
        history = decrypt_json(DATA_FILE.read_text(), password)
    history = collect(history)
    history["advice"] = build_advice(history)
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(encrypt_json(history, password))
    s = history["snapshots"][-1]
    print(f"OK {s['date']}: 登録者 {s['subscribers']} / 総再生 {s['views']} / 動画 {s['videos']}")


if __name__ == "__main__":
    main()
