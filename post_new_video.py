"""
YouTubeチャンネルの新着動画を検知して、サムネイル画像付きでXに自動投稿するスクリプト。

必要な環境変数（GitHub Actionsの Secrets に設定する）:
  YT_CHANNEL_ID     : 監視したいYouTubeチャンネルのチャンネルID (UCから始まるもの)
  X_API_KEY         : XアプリのAPI Key
  X_API_SECRET      : XアプリのAPI Key Secret
  X_ACCESS_TOKEN    : ユーザーのAccess Token
  X_ACCESS_SECRET   : ユーザーのAccess Token Secret

状態の保存:
  last_video_id.txt に最後に投稿した動画IDを保存し、
  次回実行時にそのファイルと比較して新着かどうかを判定する。
  GitHub Actions側でこのファイルをコミットして永続化する。
"""

import os
import sys
import requests
import feedparser
import tweepy

STATE_FILE = "last_video_id.txt"
THUMBNAIL_TMP_PATH = "thumbnail.jpg"


def get_latest_video():
    channel_id = os.environ["YT_CHANNEL_ID"]
    feed_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    feed = feedparser.parse(feed_url)

    if not feed.entries:
        print("フィードから動画が取得できませんでした")
        sys.exit(0)

    latest = feed.entries[0]
    video_id = latest.yt_videoid
    title = latest.title
    url = latest.link
    return video_id, title, url


def load_last_posted_id():
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return f.read().strip()


def save_last_posted_id(video_id):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        f.write(video_id)


def download_thumbnail(video_id):
    """
    YouTubeのサムネイルは動画IDから直接URLが決まるので、
    YouTube API不要でダウンロードできる。
    maxresdefault が無い動画（一部のShortsなど）もあるので、
    失敗したら順に画質を落として再試行する。
    """
    qualities = ["maxresdefault", "sddefault", "hqdefault", "mqdefault"]
    for q in qualities:
        url = f"https://img.youtube.com/vi/{video_id}/{q}.jpg"
        res = requests.get(url, timeout=15)
        # YouTubeは画像が無い場合も120x90のダミー画像を200で返すことがあるため、
        # サイズで簡易チェックする
        if res.status_code == 200 and len(res.content) > 2000:
            with open(THUMBNAIL_TMP_PATH, "wb") as f:
                f.write(res.content)
            return THUMBNAIL_TMP_PATH
    return None


def post_to_x(title, url, thumbnail_path):
    # 画像アップロードは v1.1 のエンドポイントしか対応していないため、
    # メディアアップロード用に tweepy.API(OAuth1.0a) を使う
    auth = tweepy.OAuth1UserHandler(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_SECRET"],
    )
    api_v1 = tweepy.API(auth)

    # 投稿本体（テキスト）は v2 のクライアントを使う
    client_v2 = tweepy.Client(
        consumer_key=os.environ["X_API_KEY"],
        consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"],
        access_token_secret=os.environ["X_ACCESS_SECRET"],
    )

    text = f"【新着動画更新!!】\n\n是非参考に見てみてね！\n\n{title}\n{url}"
    text = text[:280]

    media_ids = None
    if thumbnail_path:
        media = api_v1.media_upload(thumbnail_path)
        media_ids = [media.media_id]

    response = client_v2.create_tweet(text=text, media_ids=media_ids)
    print("投稿完了:", response)


def main():
    video_id, title, url = get_latest_video()
    last_id = load_last_posted_id()

    if video_id == last_id:
        print("新着動画はありません。何もしません。")
        return

    print(f"新着動画を検知: {title} ({url})")
    thumbnail_path = download_thumbnail(video_id)
    if not thumbnail_path:
        print("サムネイルの取得に失敗したので、画像なしで投稿します")

    post_to_x(title, url, thumbnail_path)
    save_last_posted_id(video_id)


if __name__ == "__main__":
    main()
