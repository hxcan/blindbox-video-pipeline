# script1_overlay.py

import ffmpeg
import sys
import os
import json
import subprocess

def get_video_dimensions(video_path):
    probe = ffmpeg.probe(video_path)
    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
    width = int(video_stream['width'])
    height = int(video_stream['height'])
    return width, height

def get_video_duration(video_path):
    probe = ffmpeg.probe(video_path)
    video_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'video'), None)
    duration = float(video_stream['duration'])
    return duration

def has_audio_stream(video_path):
    probe = ffmpeg.probe(video_path)
    audio_streams = [stream for stream in probe['streams'] if stream['codec_type'] == 'audio']
    return len(audio_streams) > 0

def overlay_videos(video1_path, video2_path, scale=0.35, left_margin=100, top_margin=100):
    video2_filename = os.path.splitext(os.path.basename(video2_path))[0]
    video1_width, video1_height = get_video_dimensions(video1_path)
    scaled_width = int(video1_width * scale)
    scaled_height = int(video1_height * scale)

    video1_duration = get_video_duration(video1_path)
    video2_duration = get_video_duration(video2_path)

    print(f"视频1的原始尺寸: {video1_width}x{video1_height}")
    print(f"缩放后的尺寸: {scaled_width}x{scaled_height}")
    print(f"视频1的持续时间: {video1_duration:.2f} 秒")
    print(f"视频2的持续时间: {video2_duration:.2f} 秒")

    # ✅ 关键修改：先 trim，再 scale，再 setpts
    video1 = (
        ffmpeg
        .input(video1_path)
        .filter_('trim', duration=min(video1_duration, video2_duration))  # ✅ 先裁剪
        .filter_('scale', w=scaled_width, h=scaled_height)
        .filter_('setpts', 'PTS-STARTPTS')  # ✅ 再重置时间戳
    )

    video2 = ffmpeg.input(video2_path)
    overlay = ffmpeg.overlay(video2, video1, x=left_margin, y=top_margin,
                             enable=f'between(t,0,{min(video1_duration, video2_duration)})')

    has_audio2 = has_audio_stream(video2_path)
    audio_inputs = []

    if has_audio2:
        audio1 = ffmpeg.input(video1_path).audio
        audio2 = ffmpeg.input(video2_path).audio
        combined_audio = ffmpeg.filter([audio1, audio2], 'amix', inputs=2, duration='longest')
        audio_inputs.append(combined_audio)
    else:
        audio1 = ffmpeg.input(video1_path).audio
        if audio1 is not None:
            audio_inputs.append(audio1)

    output_filename = f"{video2_filename}_overlayed.mp4"
    output_filepath = os.path.join(os.getcwd(), output_filename)

    print(f"正在输出视频: {output_filename}")

    if audio_inputs:
        out = ffmpeg.output(overlay, *audio_inputs, output_filepath, vcodec='libx264', acodec='aac', loglevel='error')
    else:
        out = ffmpeg.output(overlay, output_filepath, vcodec='libx264', an=None, loglevel='error')

    out.run(overwrite_output=True)
    print(f"视频叠加完成，输出文件: {output_filepath}")
    return output_filepath

def get_video1_path():
    with open('output_files.json', 'r') as file:
        data = json.load(file)
        last_output = data[-1]
        return last_output['output_file']

if __name__ == "__main__":
    video1_path = get_video1_path()

    if len(sys.argv) < 2:
        print("使用方法: python script1_overlay.py <视频2路径> [缩放比例] [左边距] [顶边距]")
        sys.exit(1)

    video2_path = sys.argv[1]
    scale = float(sys.argv[2]) if len(sys.argv) > 2 else 0.35
    left_margin = int(sys.argv[3]) if len(sys.argv) > 3 else 100
    top_margin = int(sys.argv[4]) if len(sys.argv) > 4 else 100

    output_filepath = overlay_videos(video1_path, video2_path, scale, left_margin, top_margin)

    # ✅ 调用下一个脚本：script2_gps.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    next_script = os.path.join(script_dir, "script2_gps.py")

    print(f"调用下一个脚本: {next_script}")
    subprocess.call(["python", next_script, output_filepath])
