"""データから「今日のアドバイス」を作る（ルールベース・無料）.

出力: [{"level": "good|info|warn|action", "title": str, "body": str}, ...]
level の意味:
  action … 今日やること   warn … 注意   good … 良い兆候   info … 参考
"""
from __future__ import annotations

import datetime as dt
import re
from statistics import median

JST = dt.timezone(dt.timedelta(hours=9))

TRAFFIC_JA = {
    "YT_SEARCH": "YouTube検索", "SHORTS": "ショートフィード", "SUBSCRIBER": "登録チャンネル・ホーム",
    "RELATED_VIDEO": "関連動画", "YT_OTHER_PAGE": "その他のYouTubeページ", "EXT_URL": "外部サイト・SNS",
    "NO_LINK_OTHER": "直接・不明", "PLAYLIST": "再生リスト", "YT_CHANNEL": "チャンネルページ",
    "NOTIFICATION": "通知", "END_SCREEN": "終了画面", "ANNOTATION": "カード", "HASHTAGS": "ハッシュタグ",
    "SOUND_PAGE": "サウンドページ", "SHORTS_CONTENT_LINKS": "ショートからのリンク", "LIVE_REDIRECT": "ライブリダイレクト",
    "YT_PLAYLIST_PAGE": "再生リストページ", "CAMPAIGN_CARD": "キャンペーン", "PRODUCT_PAGE": "商品ページ",
    "NO_LINK_EMBEDDED": "埋め込み", "VIDEO_REMIXES": "リミックス", "IMMERSIVE_LIVE": "ライブ",
    "ADVERTISING": "広告", "BROWSE": "ブラウジング機能",
}

# タイトルからテーマを推定（チャンネルの3本柱）
THEMES = {
    "歌・カバー": r"歌|カバー|Cover|cover|サザン|桑田|カラオケ|バラード|讃歌|Loving",
    "両声類・トランス女性": r"両声類|トランス|MtF|男の娘|地声|LGBT|lgbt|オカマ|女性として",
    "社会学・時事解説": r"社会学|解説|トランプ|首相|国防|戦略|現代戦|弱者|海峡|核融合",
}

DAILY_TIPS = [
    ("最初の3秒を見直す", "直近のショートを1本開き、最初の3秒で「何が起きるか」が伝わるか確認しましょう。地声→女声の切り替えなど一番のギャップを冒頭に置くと離脱が減ります。"),
    ("コメントに全部返信する", "今日ついたコメントにすべて返信しましょう。小規模チャンネルでは返信がそのまま常連づくりになります。返信に質問を入れると会話が続きます。"),
    ("ショートから長尺へ橋をかける", "伸びたショートの「関連動画」に、同じ曲や同じテーマの長尺動画を設定しましょう。ショート視聴者を登録者に変える最短ルートです。"),
    ("タイトルに検索される言葉を入れる", "曲名・アーティスト名は正確に、タイトルの前半に。「サザン」より「サザンオールスターズ」と正式名称も入れると検索に拾われやすくなります。"),
    ("サムネイルの文字は7文字以内", "スマホの小さい画面で読めるのは短い言葉だけ。顔＋大きな一言（例：「この声、同一人物」）にすると、クリック率が上がりやすいです。"),
    ("再生リストを整える", "「歌ってみた」「両声類ショート」「ゆるふわ社会学解説」のようにテーマ別の再生リストを作り、チャンネルトップに並べましょう。連続再生で総再生時間が伸びます。"),
    ("固定コメントで次の動画へ誘導", "最新動画に固定コメントを付け、関連する別の動画へのリンクと「どっちの声が好き？」のような質問を書きましょう。"),
    ("同じ企画の2本目を作る", "一番伸びた動画と「同じ型」の動画をもう1本作りましょう。YouTubeは一度反応した視聴者に似た動画を届けます。"),
    ("投稿時間をそろえる", "投稿する曜日と時刻を固定しましょう（例：毎週水・土の20時）。登録者が「待つ」習慣を持てるようになります。"),
    ("説明欄の最初の2行", "説明欄の最初の2行は検索結果にも表示されます。動画の内容を一言で＋関連キーワードを入れましょう。"),
    ("コミュニティ投稿で次回予告", "コミュニティ投稿（投稿タブ）で「次に歌ってほしい曲」のアンケートを取りましょう。リクエスト企画はコメントと再生の両方を増やします。"),
    ("終了画面を全動画に", "長尺動画の最後20秒に終了画面（次の動画＋登録ボタン）を設定しましょう。設定していない動画がないか確認を。"),
    ("ショートは縦画面いっぱいに", "ショートは字幕を画面中央付近に置き、下部（UIで隠れる部分）に大事な情報を置かないようにしましょう。"),
    ("過去の人気動画をリメイク", "過去に伸びた動画のテーマを、今の機材と編集でリメイクしましょう。実績のある企画は再現性が高いです。"),
    ("外部SNSで切り抜きを共有", "X・TikTok・Instagram に15秒の切り抜きを投稿し、YouTubeの本編に誘導しましょう。"),
    ("視聴維持率グラフの谷を探す", "YouTube Studio で直近の長尺動画の視聴者維持率グラフを開き、急に下がる場所を確認。そこで何が起きているかが次回の改善ポイントです。"),
    ("チャンネルの説明を一文で", "チャンネル紹介を「〇〇な人が△△を届けるチャンネル」と一文で言えるか確認し、バナーとチャンネル説明に書きましょう。"),
    ("コラボ・デュエット", "同じジャンルの小規模チャンネルとコラボ（ショートのリミックスやデュエット）を検討しましょう。お互いの視聴者が入れ替わります。"),
]


def _median(xs):
    xs = [x for x in xs if x is not None]
    return median(xs) if xs else 0


def _pct(a, b):
    return (a - b) / b * 100 if b else None


def _fmt(n):
    return f"{int(round(n)):,}"


def build_advice(h: dict) -> list[dict]:
    out: list[dict] = []
    today = dt.datetime.now(JST).date()
    a = h.get("analytics", {})
    videos = {k: v for k, v in h.get("videos", {}).items() if not v.get("removed")}
    public = {k: v for k, v in videos.items() if v.get("privacy") == "public"}

    def add(level, title, body):
        out.append({"level": level, "title": title, "body": body})

    # ---- 1. 直近7日 vs その前7日（Analytics は2〜3日遅れなので3日前までで比較）
    daily = [r for r in a.get("daily", []) if r["day"] <= (today - dt.timedelta(days=3)).isoformat()]
    if len(daily) >= 14:
        last7, prev7 = daily[-7:], daily[-14:-7]
        v1, v0 = sum(r["views"] for r in last7), sum(r["views"] for r in prev7)
        s1 = sum(r["subscribersGained"] - r["subscribersLost"] for r in last7)
        ch = _pct(v1, v0)
        period = f"{last7[0]['day'][5:]}〜{last7[-1]['day'][5:]}"
        if ch is not None and ch >= 15:
            add("good", f"再生数が前週比 +{ch:.0f}%", f"{period} の再生数は {_fmt(v1)} 回（前の7日間 {_fmt(v0)} 回）。純増登録者 {s1:+d} 人。伸びている今のうちに同じテーマで次の動画を出しましょう。")
        elif ch is not None and ch <= -15:
            add("warn", f"再生数が前週比 {ch:.0f}%", f"{period} の再生数は {_fmt(v1)} 回（前の7日間 {_fmt(v0)} 回）。純増登録者 {s1:+d} 人。投稿間隔が空いていないか、下の「伸びている動画」を確認しましょう。")
        else:
            add("info", "再生数は横ばい", f"{period} の再生数は {_fmt(v1)} 回（前の7日間 {_fmt(v0)} 回）。純増登録者 {s1:+d} 人。")

    # ---- 2. 最終投稿からの日数
    if public:
        last = max(public.values(), key=lambda v: v["publishedAt"])
        days = (today - dt.date.fromisoformat(last["publishedAt"][:10])).days
        if days >= 14:
            add("action", f"最後の投稿から {days} 日", f"最新は「{last['title'][:40]}」。間隔が2週間を超えると、登録者のおすすめに出にくくなります。まずは短いショート1本でも投稿しましょう。")
        elif days >= 7:
            add("action", f"最後の投稿から {days} 日", "週1本以上のペースを保つと、登録者のホーム画面に表示されやすくなります。今週中に1本出しましょう。")

    # ---- 3. 今伸びている動画（Data API の日次スナップショット差分）
    snaps = h.get("videoSnapshots", {})
    gains = []
    for vid, rows in snaps.items():
        if vid not in public or len(rows) < 2:
            continue
        rows = sorted(rows)
        cutoff = (today - dt.timedelta(days=7)).isoformat()
        base = next((r for r in rows if r[0] >= cutoff), rows[0])
        g = rows[-1][1] - base[1]
        if g > 0:
            gains.append((g, vid))
    gains.sort(reverse=True)
    if gains:
        top = gains[:3]
        lines = "／".join(f"「{public[v]['title'][:28]}」+{g}" for g, v in top)
        add("good", "今週伸びている動画", f"{lines}。伸びている動画には、関連動画リンク・固定コメントを付けて他の動画へ誘導しましょう。")

    # ---- 4. ショート vs 長尺（Analytics の creatorContentType）
    ct = {r["creatorContentType"]: r for r in a.get("contentType365", []) or []}
    sh, lo = ct.get("SHORTS"), ct.get("VIDEO_ON_DEMAND")
    if sh and lo and (sh["views"] + lo["views"]) > 0:
        sh_share = sh["views"] / (sh["views"] + lo["views"]) * 100
        sub_per_k_sh = sh["subscribersGained"] / sh["views"] * 1000 if sh["views"] else 0
        sub_per_k_lo = lo["subscribersGained"] / lo["views"] * 1000 if lo["views"] else 0
        add("info", f"過去1年の再生の {sh_share:.0f}% がショート",
            f"ショート {_fmt(sh['views'])} 回（1000回あたり登録 {sub_per_k_sh:.1f} 人）／長尺 {_fmt(lo['views'])} 回（1000回あたり登録 {sub_per_k_lo:.1f} 人）。"
            + ("ショートで見つけてもらい、長尺で登録してもらう流れを作りましょう。" if sub_per_k_lo > sub_per_k_sh else "ショートが登録者獲得の主力です。ショートの投稿頻度を上げましょう。"))

    # ---- 5. テーマ別の成績（直近2年の公開動画、再生数の中央値）
    since = (today - dt.timedelta(days=730)).isoformat()
    theme_stats = []
    for name, pat in THEMES.items():
        for kind, is_sh in (("ショート", True), ("長尺", False)):
            vs = [v["views"] for v in public.values()
                  if v["publishedAt"] >= since and v.get("short") == is_sh and re.search(pat, v["title"])]
            if len(vs) >= 2:
                theme_stats.append((_median(vs), f"{name}（{kind}）", len(vs)))
    if len(theme_stats) >= 2:
        theme_stats.sort(reverse=True)
        best, worst = theme_stats[0], theme_stats[-1]
        add("info", f"一番強い型：{best[1]}",
            f"直近2年の再生数の中央値は {best[1]} が {_fmt(best[0])} 回（{best[2]}本）、{worst[1]} が {_fmt(worst[0])} 回（{worst[2]}本）。"
            "強い型を軸に、他のテーマはその型に寄せる（例：社会学の話題を両声類ショートで紹介）と伸ばしやすくなります。")

    # ---- 6. 視聴維持率（長尺）
    life = {r["video"]: r for r in a.get("videosLifetime", []) or []}
    longs = [(life[v]["averageViewPercentage"], v) for v, meta in public.items()
             if v in life and not meta.get("short") and life[v]["views"] >= 30]
    if longs:
        avg = sum(p for p, _ in longs) / len(longs)
        low_p, low_v = min(longs)
        add("warn" if avg < 35 else "info", f"長尺の平均視聴率 {avg:.0f}%",
            f"最も低いのは「{public[low_v]['title'][:30]}」の {low_p:.0f}%。冒頭30秒で「この動画で何がわかるか」を言い切り、前置きを削ると改善しやすいです。")

    # ---- 7. 登録率（直近28日）
    last28 = daily[-28:]
    v28 = sum(r["views"] for r in last28)
    g28 = sum(r["subscribersGained"] for r in last28)
    if v28 >= 100:
        rate = g28 / v28 * 1000
        level = "good" if rate >= 5 else "info"
        add(level, f"1000回再生あたり登録 {rate:.1f} 人（28日）",
            "目安は 2〜5 人。" + ("高い登録率です。再生数を増やせば素直に登録者が増える状態です。" if rate >= 5
                               else "動画の最後や固定コメントで「こういう動画を続けます」と次回の期待を伝えると登録率が上がります。"))

    # ---- 8. 流入元
    tr = a.get("traffic28") or []
    tot = sum(r["views"] for r in tr)
    if tot >= 50:
        share = {r["insightTrafficSourceType"]: r["views"] / tot * 100 for r in tr}
        top3 = sorted(share.items(), key=lambda x: -x[1])[:3]
        desc = "、".join(f"{TRAFFIC_JA.get(k, k)} {p:.0f}%" for k, p in top3)
        tip = ""
        if share.get("YT_SEARCH", 0) < 10:
            tip = "検索流入が少なめです。曲名・アーティスト名・社会学のキーワードをタイトル前半に入れましょう。"
        elif share.get("RELATED_VIDEO", 0) < 10:
            tip = "関連動画からの流入が少なめです。人気チャンネルと同じ曲・同じ話題を扱うと関連動画に載りやすくなります。"
        add("info", "どこから見られているか（28日）", f"{desc}。{tip}")

    terms = a.get("searchTerms28") or []
    if terms:
        t = "、".join(f"「{r['insightTrafficSourceDetail']}」" for r in terms[:5])
        add("info", "検索されている言葉", f"{t}。この言葉をタイトル・説明欄・次の動画のテーマに使いましょう。")

    # ---- 9. テスト動画などの公開ミス
    for v in public.values():
        if re.fullmatch(r"\s*(test|テスト)\s*", v["title"], re.I):
            add("action", "「テスト」動画が公開になっています", f"「{v['title']}」は非公開か限定公開にしましょう。チャンネルの印象と平均成績を下げてしまいます。")
            break

    # ---- 10. 今日の一手（毎日入れ替わる）
    title, body = DAILY_TIPS[today.toordinal() % len(DAILY_TIPS)]
    add("action", f"今日の一手：{title}", body)

    order = {"action": 0, "warn": 1, "good": 2, "info": 3}
    out.sort(key=lambda x: order[x["level"]])
    return out
