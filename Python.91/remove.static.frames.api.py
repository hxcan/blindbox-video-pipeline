import ffmpeg
import os
import sys
from tqdm import tqdm
import uuid
import logging
from datetime import datetime
import cv2
import numpy as np
import subprocess
import json  # 导入 json 模块

# 设置日志记录
log_filename = f"debug_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logging.basicConfig(filename=log_filename, level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

def log_info(message):
    print(message)
    logging.info(message)

def log_error(message):
    print(f"ERROR: {message}")
    logging.error(message)

def save_output_to_json(output_path, json_file="processed_video_output.json"):
    """
    将输出视频文件的完整路径保存到 JSON 文件中。
    :param output_path: 输出视频文件的完整路径
    :param json_file: JSON 文件名
    """
    data = {"output_video_path": output_path}
    try:
        # 如果文件已存在，读取现有内容并追加新数据
        if os.path.exists(json_file):
            with open(json_file, 'r', encoding='utf-8') as f:
                existing_data = json.load(f)
            if isinstance(existing_data, list):
                existing_data.append(data)
            else:
                existing_data = [existing_data, data]
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(existing_data, f, ensure_ascii=False, indent=4)
        else:
            # 如果文件不存在，直接创建并写入数据
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
        log_info(f"成功将输出路径保存到 JSON 文件: {json_file}")
    except Exception as e:
        log_error(f"保存 JSON 文件时发生错误: {e}")

def get_frame_rate(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Could not open video file.")
    frame_rate = cap.get(cv2.CAP_PROP_FPS)
    cap.release()
    return frame_rate

def calculate_frame_differences(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Could not open video file.")
    
    ret, prev_frame = cap.read()
    if not ret:
        raise ValueError("Could not read frame.")
    
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    frame_differences = []
    frame_timestamps = []
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
    with tqdm(total=total_frames, desc="Calculating frame differences") as pbar:
        while True:
            ret, curr_frame = cap.read()
            if not ret:
                break
            
            curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(curr_gray, prev_gray)
            avg_diff = np.mean(diff)
            frame_differences.append(avg_diff)
            frame_timestamps.append(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000.0)
            
            prev_gray = curr_gray
            pbar.update(1)
    
    cap.release()
    return frame_differences, frame_timestamps

def find_threshold(frame_differences, threshold=None):
    if threshold is None:
        sorted_diffs = sorted(frame_differences)
        threshold = sorted_diffs[int(0.1 * len(sorted_diffs))]
    return threshold

def find_static_segments(frame_differences, frame_timestamps, threshold):
    static_segments = []
    start_frame = None
    for i, diff in enumerate(frame_differences):
        if diff < threshold:
            if start_frame is None:
                start_frame = i
        else:
            if start_frame is not None:
                end_frame = i - 1
                start_time = frame_timestamps[start_frame]
                end_time = frame_timestamps[end_frame]
                static_segments.append((start_time, end_time))
                start_frame = None
    if start_frame is not None:
        end_frame = len(frame_differences) - 1
        start_time = frame_timestamps[start_frame]
        end_time = frame_timestamps[end_frame]
        static_segments.append((start_time, end_time))
    return static_segments

def adjust_static_segments(static_segments, frame_timestamps):
    adjusted_segments = []
    for start, end in static_segments:
        end_index = next(i for i, ts in enumerate(frame_timestamps) if ts >= end)
        adjusted_end_index = max(0, end_index - 5)
        adjusted_end = frame_timestamps[adjusted_end_index]
        if adjusted_end >= start:
            adjusted_segments.append((start, adjusted_end))
    return adjusted_segments

def get_non_static_segments(static_segments, total_duration):
    non_static_segments = []
    last_end = 0
    for start, end in static_segments:
        if last_end < start:
            non_static_segments.append((last_end, start))
        last_end = end
    if last_end < total_duration:
        non_static_segments.append((last_end, total_duration))
    return non_static_segments

def extract_and_merge_segments_batch(video_path, segments, batch_size, output_path, temp_dir='temp_clips'):
    os.makedirs(temp_dir, exist_ok=True)

    batches = [segments[i:i + batch_size] for i in range(0, len(segments), batch_size)]
    temp_files = []

    input_stream = ffmpeg.input(video_path)
    
    # Check if the video contains an audio stream
    probe = ffmpeg.probe(video_path)
    audio_streams = [stream for stream in probe['streams'] if stream['codec_type'] == 'audio']
    has_audio = len(audio_streams) > 0

    for batch_index, batch in enumerate(batches, start=1):
        video_streams = []
        audio_streams_to_concat = []  # Only used if there's audio

        for start, end in batch:
            duration = end - start
            log_info(f"Processing segment: Start={start}, End={end}, Duration={duration:.2f}s")
            video_clip = (
                input_stream.video
                .filter_('trim', start=start, duration=duration)
                .filter_('setpts', 'PTS-STARTPTS')
            )
            video_streams.append(video_clip)

            if has_audio:
                audio_clip = (
                    input_stream.audio
                    .filter_('atrim', start=start, duration=duration)
                    .filter_('asetpts', 'PTS-STARTPTS')
                )
                audio_streams_to_concat.append(audio_clip)

        try:
            log_info(f"Processing batch {batch_index}/{len(batches)}: Combining video and audio clips")

            # Combine video streams together
            combined_video = ffmpeg.concat(*video_streams, v=1, a=0)

            # If there's audio, combine it with the video
            if has_audio:
                combined_audio = ffmpeg.concat(*audio_streams_to_concat, v=0, a=1)
                combined_clip = ffmpeg.concat(combined_video, combined_audio, v=1, a=1)
            else:
                combined_clip = combined_video

            combined_temp_file = os.path.join(temp_dir, f'combined_{uuid.uuid4()}.mp4')
            log_info(f"Temporary file name for this batch: {combined_temp_file}")

            if os.path.exists(combined_temp_file):
                os.remove(combined_temp_file)
                log_info(f"Removed existing temporary file: {combined_temp_file}")

            # Directly run the command using ffmpeg.run()
            (
                ffmpeg
                .output(combined_clip, combined_temp_file, vcodec='libx264', acodec='aac' if has_audio else 'copy', strict='experimental', loglevel='error')
                .global_args('-y')  # Automatically overwrite output files
                .run(capture_stdout=True, capture_stderr=True)
            )
            temp_files.append(combined_temp_file)

        except Exception as e:
            log_error(f"Error during processing batch {batch_index}: {str(e)}")
            raise

    # Merge all temporary files into the final output file using concat protocol
    merge_temp_files(temp_files, output_path)

def merge_temp_files(temp_files, output_path):
    # Remove existing output file if it exists
    if os.path.exists(output_path):
        try:
            os.remove(output_path)
            log_info(f"Removed existing output file: {output_path}")
        except OSError as e:
            log_error(f"Error removing existing output file: {e}")
            raise

    with open('filelist.txt', 'w') as f:
        for temp_file in temp_files:
            f.write(f"file '{temp_file}'\n")

    cmd = [
        'ffmpeg',
        '-f', 'concat',
        '-safe', '0',
        '-i', 'filelist.txt',
        '-c', 'copy',
        '-loglevel', 'error',
        output_path
    ]
    log_info(f"FFmpeg command for merging using concat protocol: {' '.join(cmd)}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        log_error(f"Error executing FFmpeg command: {result.stderr}")
        raise RuntimeError(f"Failed to execute FFmpeg command: {' '.join(cmd)}")

    os.remove('filelist.txt')

def debug_sync_issues(video_path, non_static_segments, output_path):
    extract_and_merge_segments_batch(video_path, non_static_segments, batch_size=100, output_path=output_path)

def main():
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        print("Usage: python script.py <path_to_video> [threshold]")
        return

    video_path = sys.argv[1]
    threshold = float(sys.argv[2]) if len(sys.argv) == 3 else None

    frame_differences, frame_timestamps = calculate_frame_differences(video_path)
    threshold = find_threshold(frame_differences, threshold)
    log_info(f"Using threshold: {threshold:.2f}")

    static_segments = find_static_segments(frame_differences, frame_timestamps, threshold)
    adjusted_static_segments = adjust_static_segments(static_segments, frame_timestamps)
    total_duration = frame_timestamps[-1] + (1 / get_frame_rate(video_path))
    non_static_segments = get_non_static_segments(adjusted_static_segments, total_duration)

    base_name = os.path.splitext(os.path.basename(video_path))[0]
    output_path = f"{base_name}_threshold_{threshold:.2f}.mp4"
    debug_sync_issues(video_path, non_static_segments, output_path)

    # 输出实际准备提取并合并的片段时间戳列表
    log_info("Non-static segments:")
    for segment in non_static_segments:
        log_info(f"Start: {segment[0]:.2f} s, End: {segment[1]:.2f} s")

    # 保存输出路径到 JSON 文件
    save_output_to_json(output_path)

    # 🔧 精准构造 video.fps.30.rb 的路径
    current_script_dir = os.path.dirname(os.path.abspath(__file__))  # Python.91/
    common_parent_dir = os.path.dirname(current_script_dir)          # blindbox.n/
    ruby_script_path = os.path.join(common_parent_dir, 'ruby.he', 'video.fps.30.rb')

    # 检查 Ruby 脚本是否存在
    if not os.path.exists(ruby_script_path):
        log_error(f"Ruby 脚本未找到: {ruby_script_path}")
        raise FileNotFoundError(f"Ruby script not found: {ruby_script_path}")

    # 构造命令：ruby video.fps.30.rb <output_video> <json_file>
    command = [
        'ruby',
        ruby_script_path,
        output_path,                    # 输入视频（60fps 去静止帧）
        "processed_video_output.json"   # JSON 状态文件（保持一致）
    ]

    try:
        log_info(f"调用 Ruby 脚本进行降帧率处理: {' '.join(command)}")
        subprocess.run(command, check=True)
        log_info("✅ 成功调用 video.fps.30.rb，已启动后续流程。")
    except subprocess.CalledProcessError as e:
        log_error(f"❌ 调用 video.fps.30.rb 失败: {e}")
        raise
    except Exception as e:
        log_error(f"❌ 执行过程中发生未知错误: {e}")
        raise

if __name__ == "__main__":
    main()
