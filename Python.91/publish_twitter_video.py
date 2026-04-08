#!/usr/bin/env python3

import tweepy
import os
import sys
import argparse

# --- 设置代理逻辑：优先使用环境变量，否则设置默认值 ---
DEFAULT_PROXY = 'http://127.0.0.1:8118'

if 'HTTP_PROXY' not in os.environ and 'HTTPS_PROXY' not in os.environ:
    print(f"🔌 未检测到代理环境变量，启用默认代理: {DEFAULT_PROXY}")
    os.environ['HTTP_PROXY'] = DEFAULT_PROXY
    os.environ['HTTPS_PROXY'] = DEFAULT_PROXY
else:
    http_proxy = os.environ.get('HTTP_PROXY', 'Not set')
    https_proxy = os.environ.get('HTTPS_PROXY', 'Not set')
    print("🔌 使用现有代理设置:")
    print(f"   HTTP_PROXY = {http_proxy}")
    print(f"   HTTPS_PROXY = {https_proxy}")

# ====== 参数解析 ======
parser = argparse.ArgumentParser()
parser.add_argument('--consumer-key', required=True)
parser.add_argument('--consumer-secret', required=True)
parser.add_argument('--access-token', required=True)
parser.add_argument('--access-token-secret', required=True)
parser.add_argument('--video', required=True)
parser.add_argument('--text', required=True)
args = parser.parse_args()

# ====== 创建认证对象 ======
auth = tweepy.OAuth1UserHandler(
    args.consumer_key,
    args.consumer_secret,
    args.access_token,
    args.access_token_secret
)

# v1.1 API（上传视频）
api_v1 = tweepy.API(auth)

# v2 Client（发推文）
client = tweepy.Client(
    consumer_key=args.consumer_key,
    consumer_secret=args.consumer_secret,
    access_token=args.access_token,
    access_token_secret=args.access_token_secret,
)

# ====== 验证身份 ======
try:
    me = client.get_me()
    print(f"✅ 已登录账号: @{me.data.username}")
except Exception as e:
    print(f"❌ 身份验证失败: {e}")
    sys.exit(1)

# ====== 上传视频 ======
print("📤 正在上传视频...")
try:
    media = api_v1.media_upload(
        filename=args.video,
        media_category="tweet_video"
    )
    print(f"📎 媒体上传成功，ID: {media.media_id_string}")
except Exception as e:
    print(f"❌ 视频上传失败: {e}")
    sys.exit(1)

# ====== 发布带视频的推文 ======
print("🐦 正在发布推文...")
try:
    response = client.create_tweet(
        text=args.text,
        media_ids=[media.media_id_string]
    )
    tweet_id = response.data['id']
    print(f"✅ 推文发布成功！")
    print(f"🔗 查看链接: https://x.com/user/status/{tweet_id}")
except Exception as e:
    print(f"❌ 发推失败: {e}")
    sys.exit(1)
