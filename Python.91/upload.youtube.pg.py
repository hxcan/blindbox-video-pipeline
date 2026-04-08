import os
import google.auth
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
import argparse
from google.auth.transport.requests import Request  # ✅ 必须添加这一行
import httplib2  # 可选：用于更稳定的 HTTP 连接


# --- 设置代理逻辑：优先使用环境变量，否则设置默认值 ---
DEFAULT_PROXY = 'http://127.0.0.1:8118'

if 'HTTP_PROXY' not in os.environ and 'HTTPS_PROXY' not in os.environ:
    print(f"No proxy environment variables found. Setting default proxy: {DEFAULT_PROXY}")
    os.environ['HTTP_PROXY'] = DEFAULT_PROXY
    os.environ['HTTPS_PROXY'] = DEFAULT_PROXY
else:
    http_proxy = os.environ.get('HTTP_PROXY', 'Not set')
    https_proxy = os.environ.get('HTTPS_PROXY', 'Not set')
    print(f"Using existing proxy settings:")
    print(f"  HTTP_PROXY = {http_proxy}")
    print(f"  HTTPS_PROXY = {https_proxy}")


# 如果修改了这些范围，请删除文件 token.json（如果存在）
SCOPES = ['https://www.googleapis.com/auth/youtube.upload']


def get_authenticated_service():
    creds = None
    
    # === 智能查找认证文件 ===
    credentials_dir = os.path.expanduser('~/.blindbox/youtube.credentials.h')
    credentials_file = None
    
    if os.path.exists(credentials_dir):
        for filename in os.listdir(credentials_dir):
            if filename.startswith('client_secret_') and filename.endswith('.json'):
                credentials_file = os.path.join(credentials_dir, filename)
                print(f"🔑 Found credentials file: {filename}")
                break
    
    if not credentials_file:
        print(f"Error: No client_secret_*.json found in {credentials_dir}")
        return None
    
    # === Token 文件路径（固定文件名）===
    token_dir = os.path.expanduser('~/.blindbox/youtube.token')
    os.makedirs(token_dir, exist_ok=True)  # 确保目录存在
    token_file = os.path.join(token_dir, 'token.json')
    
    # 加载已保存的凭据
    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    # 如果没有有效的凭据，则让用户登录
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Failed to refresh credentials: {e}")
                creds = None

        if not creds:
            if not os.path.exists(credentials_file):
                print(f"Error: Credentials file not found at {credentials_file}")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
            # 保存凭据以备下次运行
            with open(token_file, 'w') as token:
                token.write(creds.to_json())

    try:
        service = build('youtube', 'v3', credentials=creds)
        return service
    except HttpError as error:
        print(f'An HTTP error {error.resp.status} occurred: {error.content}')
        return None


def upload_video(service, video_file, title, description, tags, category_id):
    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': category_id,
            'defaultLanguage': 'zh'
        },
        'status': {
            'privacyStatus': 'public',
            'selfDeclaredMadeForKids': False
        }
    }

    # 检查文件是否存在
    if not os.path.exists(video_file):
        print(f"Error: Video file not found: {video_file}")
        return

    media = MediaFileUpload(video_file, chunksize=-1, resumable=True)
    request = service.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            print(f"Uploaded {int(status.progress() * 100)}%.")

    print("Upload Complete!")
    video_id = response['id']
    print(f"Video ID: {video_id}")
    watch_url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"Video URL: {watch_url}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload a video to YouTube.")
    parser.add_argument("video_file", help="Path to the video file to upload")
    parser.add_argument("--title", default="Untitled Video", help="Video title")
    parser.add_argument("--description", default="", help="Video description")
    parser.add_argument("--tags", nargs="*", default=[], help="List of tags (e.g. --tags tag1 tag2 tag3)")
    parser.add_argument("--category", default="22", help="YouTube category ID (default: 22 'Entertainment')")

    args = parser.parse_args()

    youtube_service = get_authenticated_service()
    if youtube_service:
        upload_video(
            service=youtube_service,
            video_file=args.video_file,
            title=args.title,
            description=args.description,
            tags=args.tags,
            category_id=args.category
        )
    else:
        print("Failed to authenticate with YouTube.")
