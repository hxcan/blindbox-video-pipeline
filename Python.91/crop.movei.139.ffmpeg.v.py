#!/usr/bin/python

import sys
import subprocess
import os

def trim_video(input_path, duration):
    # 检查输入文件是否存在
    if not os.path.isfile(input_path):
        print(f"Error: The file {input_path} does not exist.")
        return

    # 构造输出文件名：在原文件名后插入 .{duration}
    name, ext = os.path.splitext(input_path)
    output_path = f"{name}.{duration}{ext}"

    # 使用FFmpeg截取视频的前 {duration} 秒
    command = [
        'ffmpeg',
        '-i', input_path,
        '-t', str(duration),        # 裁剪时长（秒）
        '-c', 'copy',               # 复制流，不重新编码
        '-map_metadata', '0',       # 保留元数据（GPS等）
        '-movflags', '+faststart',  # ✅ 关键修复：将 moov 移到开头
        output_path
    ]

    try:
        subprocess.run(command, check=True)
        print(f"✅ Trimmed video saved to: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print("Failed to trim video.")

if __name__ == "__main__":
    # 修改：现在需要 2 个参数：文件路径 + 裁剪秒数
    if len(sys.argv) != 3:
        print("Usage: python crop.py <path_to_video_file> <duration_seconds>")
        print("Example: python crop.py video.mp4 139")
        sys.exit(1)

    input_path = sys.argv[1]
    try:
        duration = int(sys.argv[2])  # 确保是整数秒数
        if duration <= 0:
            raise ValueError
    except ValueError:
        print("Error: Duration must be a positive integer.")
        sys.exit(1)

    trim_video(input_path, duration)
