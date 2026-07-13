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
parser.add_argument('--max-length', type=int, default=140,
                    help='推文最大字符长度（默认 140），超过将自动截断')
parser.add_argument('--no-truncate', action='store_true',
                    help='超过最大长度时不自动截断，而是报错退出')
args = parser.parse_args()

# ====== 文本长度检测与截断 ======
def truncate_text(text, max_length, add_ellipsis=True):
    """
    智能截断文本到指定长度。
    
    Twitter 标准：280 字符（中文算 1 个字符）
    短视频推荐 140 字符以内以避免 403
    
    Args:
        text: 原始文本
        max_length: 最大字符数
        add_ellipsis: 是否在末尾添加 "..."
    
    Returns:
        (截断后的文本, 是否被截断)
    """
    if len(text) <= max_length:
        return text, False
    
    if add_ellipsis:
        # 留出 3 个字符给 "..."
        truncated = text[:max_length - 3].rstrip() + "..."
    else:
        truncated = text[:max_length]
    
    return truncated, True

original_length = len(args.text)
print(f"📝 文本长度: {original_length} 字符 (限制: {args.max_length})")

if original_length > args.max_length:
    if args.no_truncate:
        print(f"❌ 文本超过 {args.max_length} 字符限制（当前 {original_length}）")
        print(f"   使用 --no-truncate 已禁止自动截断")
        print(f"   请手动精简文本或调高 --max-length")
        sys.exit(1)
    else:
        new_text, was_truncated = truncate_text(args.text, args.max_length, add_ellipsis=True)
        print(f"✂️  文本已自动截断: {original_length} → {len(new_text)} 字符")
        print(f"   截断处添加了 '...' 标记")
        args.text = new_text
else:
    print(f"✅ 文本长度符合要求，无需截断")

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