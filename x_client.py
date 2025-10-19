
from __future__ import annotations
import os
from datetime import datetime
from typing import Optional
import tweepy

def _get_x_clients():
    ck = os.getenv("TWITTER_API_KEY")
    cs = os.getenv("TWITTER_API_SECRET")
    at = os.getenv("TWITTER_ACCESS_TOKEN")
    ats = os.getenv("TWITTER_ACCESS_SECRET")
    if not all([ck, cs, at, ats]):
        raise RuntimeError("X(Twitter) のAPI鍵が未設定です（.env を確認）")

    client = tweepy.Client(consumer_key=ck, consumer_secret=cs, access_token=at, access_token_secret=ats, wait_on_rate_limit=True)
    auth = tweepy.OAuth1UserHandler(ck, cs, at, ats)
    api = tweepy.API(auth, wait_on_rate_limit=True)
    return client, api

def _log_x(message: str):
    import os
    os.makedirs("outputs/logs", exist_ok=True)
    path = f"outputs/logs/x_post_{datetime.now():%Y%m%d}.log"
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now():%H:%M:%S}] {message}\n")

def post_to_x(text: str, image_path: Optional[str] = None) -> str:
    """Xに投稿。画像あり→v1.1でアップロード→v2でツイート作成。投稿URLを返す。"""
    if not text or not text.strip():
        raise ValueError("投稿テキストが空です。")
    text = text.strip()
    if len(text) > 280:
        text = text[:277] + "…"

    client, api = _get_x_clients()
    media_ids = None

    if image_path and os.path.exists(image_path):
        try:
            media = api.media_upload(filename=image_path)
            media_ids = [media.media_id]
        except Exception as e:
            _log_x(f"画像アップロード失敗: {e}")
            raise RuntimeError(f"画像アップロードに失敗しました: {e}")

    try:
        resp = client.create_tweet(text=text, media_ids=media_ids)
        tweet_id = resp.data.get("id")
        url = f"https://x.com/i/web/status/{tweet_id}"
        _log_x(f"投稿成功: {url}")
        return url
    except Exception as e:
        _log_x(f"投稿失敗: {e}")
        raise RuntimeError(f"ツイート作成に失敗しました: {e}")
