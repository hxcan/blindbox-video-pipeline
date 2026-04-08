import os
import sys
import argparse
import subprocess
import json
from pathlib import Path
import re

# ========================
# 配置路径
# ========================
CONFIG_DIR = Path.home() / ".blindbox" / "bilibili"
COOKIE_FILE = CONFIG_DIR / "cookies.json"
BILIUP_COOKIE_LINK = Path("cookies.json")  # 当前目录中的符号链接

def ensure_config_dir():
    """确保配置目录存在"""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

def is_logged_in():
    """检查是否已登录（带完整调试）"""
    print(f"🔍 检查登录态文件是否存在: {COOKIE_FILE}", file=sys.stderr)

    if not COOKIE_FILE.exists():
        print("❌ 文件不存在", file=sys.stderr)
        return False

    print(f"✅ 文件存在，大小: {COOKIE_FILE.stat().st_size} 字节", file=sys.stderr)

    try:
        content = COOKIE_FILE.read_text(encoding='utf-8')
        print(f"📄 文件内容前 200 字符:\n{content[:200]}...", file=sys.stderr)

        cookies = json.loads(content)
        has_sessdata = any(c.get('name') == 'SESSDATA' for c in cookies['cookie_info']['cookies'])

        if has_sessdata:
            print("🟢 登录有效：找到 SESSDATA", file=sys.stderr)
        else:
            print("🟡 登录无效：未找到 SESSDATA", file=sys.stderr)

        return has_sessdata

    except Exception as e:
        print(f"💥 解析 cookie 失败: {type(e).__name__}: {e}", file=sys.stderr)
        return False

def create_cookie_symlink():
    """创建符号链接，让 biliup 能找到 cookie"""
    if BILIUP_COOKIE_LINK.exists():
        BILIUP_COOKIE_LINK.unlink()

    BILIUP_COOKIE_LINK.symlink_to(COOKIE_FILE.resolve())
    print(f"🔗 符号链接已创建: {BILIUP_COOKIE_LINK} -> {COOKIE_FILE}")

def login_flow():
    """引导用户登录，并将生成的 cookie 移动到统一位置"""
    print("🔍 Bilibili 登录未检测到，请开始登录流程...", file=sys.stderr)
    print("💡 请在弹出的浏览器中扫码或手动登录。", file=sys.stderr)

    # 确保当前无残留
    if BILIUP_COOKIE_LINK.exists():
        BILIUP_COOKIE_LINK.unlink()

    result = subprocess.run(['biliup', 'login'], check=False)
    if result.returncode != 0:
        print("❌ 登录失败，请重试。", file=sys.stderr)
        sys.exit(1)

    # 将生成的 cookie 移动到全局位置
    if BILIUP_COOKIE_LINK.exists():
        content = BILIUP_COOKIE_LINK.read_text(encoding='utf-8')
        COOKIE_FILE.write_text(content, encoding='utf-8')
        BILIUP_COOKIE_LINK.unlink()  # 删除原始文件
        print(f"✅ 登录成功，cookies 已保存至 {COOKIE_FILE}")
    else:
        print("❌ 登录成功但未找到 cookies 文件。")
        sys.exit(1)

def extract_hashtags(text):
    """从描述中提取 #标签 作为 tag"""
    return ','.join(set(re.findall(r'#(\w+)', text)))

def upload_video(video_path, title, desc):
    """调用 biliup 上传视频"""
    tags = extract_hashtags(desc)
    if not tags:
        tags = "AI,语音合成,SadTalker"  # 默认标签

    cmd = ["biliup", "upload",
           str(video_path),
           "--title", title,
           "--desc", desc,
           "--tid", "27",           # 生活区
           "--tag", tags,
           "--copyright", "1"        # 1: 原创 | 2: 转载
    ]

    print("📤 正在上传视频到哔哩哔哩...", file=sys.stderr)
    print(f"📋 命令行: {' '.join(cmd)}", file=sys.stderr)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    if result.returncode != 0:
        print("❌ 上传失败:", file=sys.stderr)
        print(f"🔴 stderr:\n{result.stderr}", file=sys.stderr)
        print(f"🟢 stdout:\n{result.stdout}", file=sys.stderr)
        sys.exit(1)
    else:
        print("✅ 视频发布成功！", file=sys.stderr)

def main():
    parser = argparse.ArgumentParser(description="自动上传视频到哔哩哔哩")
    parser.add_argument("video_file", help="待上传的视频文件路径")
    parser.add_argument("--title", required=True, help="视频标题")
    parser.add_argument("--description", default="", help="视频描述")

    args = parser.parse_args()

    video_path = Path(args.video_file)
    if not video_path.is_file():
        print(f"❌ 文件不存在：{video_path}", file=sys.stderr)
        sys.exit(1)

    ensure_config_dir()

    # 如果已有登录态，则创建符号链接
    if is_logged_in():
        create_cookie_symlink()
        print(f"✅ 检测到登录状态，使用账号 {COOKIE_FILE}")
    else:
        login_flow()
        create_cookie_symlink()

    upload_video(
        video_path=video_path,
        title=args.title,
        desc=args.description
    )

if __name__ == "__main__":
    main()
