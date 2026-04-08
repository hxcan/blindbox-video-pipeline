# script3_crop.py

import sys
import os
import subprocess
import time
import json

# 读取或初始化 output_info.json
JSON_PATH = "output_info.json"
if os.path.exists(JSON_PATH):
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        try:
            metadata = json.load(f)
        except:
            metadata = {}
else:
    metadata = {}

def get_video_duration(video_path):
    import ffmpeg
    probe = ffmpeg.probe(video_path)
    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
    if video_stream is None:
        raise ValueError("未找到视频流")
    return float(video_stream['duration'])

def check_and_crop_video(duration, limit, script_name, output_filepath):
    """
    检查视频长度并决定是否裁剪
    :param duration: 当前视频时长
    :param limit: 裁剪限制时长（秒）
    :param script_name: 对应的裁剪脚本名
    :param output_filepath: 输出视频路径（原始文件路径）
    """
    cut_key = f"cut_video_{int(limit)}"

    # ✅ 无论是否裁剪，都写入对应时长的路径
    # 1. 如果时长 <= 限制，直接使用原始文件
    if duration <= limit:
        metadata[cut_key] = output_filepath  # 原始文件路径
        print(f"✅ 视频长度 {duration:.2f} 秒 ≤ {limit} 秒，使用原始视频: {output_filepath}")
        return  # 不调用裁剪脚本

    # 2. 如果时长 > 限制，才调用裁剪脚本
    script_dir = os.path.dirname(os.path.abspath(__file__))
    crop_script_path = os.path.join(script_dir, script_name)
    if os.path.exists(crop_script_path):
        print(f"📹 视频长度 {duration:.2f} 秒 > {limit} 秒，正在调用裁剪脚本: {script_name} 并传入时长 {limit}")
        subprocess.call(["python", crop_script_path, output_filepath, str(limit)])

        # 裁剪后生成的文件名：原名 + .{limit}.mp4
        name, ext = os.path.splitext(output_filepath)
        cut_output_path = f"{name}.{limit}{ext}"
        if os.path.exists(cut_output_path):
            metadata[cut_key] = cut_output_path
            print(f"💾 已记录裁剪后视频路径: {cut_key} → {cut_output_path}")
        else:
            print(f"⚠️  裁剪输出文件不存在: {cut_output_path}")
            metadata[cut_key] = output_filepath  # 降级：回退到原始文件
    else:
        print(f"⚠️  警告: 裁剪脚本不存在，跳过: {crop_script_path}")
        metadata[cut_key] = output_filepath  # 降级：回退到原始文件

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("使用方法: python script3_crop.py <输入视频路径>")
        sys.exit(1)

    input_filepath = sys.argv[1]

    # 等待文件写入完成（可选）
    while not os.path.exists(input_filepath):
        print(f"⏳ 等待文件 {input_filepath}...")
        time.sleep(1)

    try:
        duration = get_video_duration(input_filepath)
        print(f"📊 检测到视频时长: {duration:.2f} 秒")

        # 调用五次，分别对应 29s, 89s, 139s, 179s, 299s
        check_and_crop_video(duration, 29, "crop.movei.139.ffmpeg.v.py", input_filepath)
        check_and_crop_video(duration, 89, "crop.movei.139.ffmpeg.v.py", input_filepath)
        check_and_crop_video(duration, 139, "crop.movei.139.ffmpeg.v.py", input_filepath)
        check_and_crop_video(duration, 179, "crop.movei.139.ffmpeg.v.py", input_filepath)
        check_and_crop_video(duration, 299, "crop.movei.139.ffmpeg.v.py", input_filepath)

        # ✅ 最后保存更新后的 metadata
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        print(f"✅ metadata.json 已更新，所有 cut_video_XXX 字段已填充。")

    except Exception as e:
        print(f"❌ 处理视频时长时出错: {e}")
        sys.exit(1)
