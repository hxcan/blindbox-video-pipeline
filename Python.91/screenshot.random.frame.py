#!/usr/bin/python3

import cv2
import random
import os
import sys
import subprocess
import json

def capture_random_frame(video_path):
    # 检查文件是否存在
    if not os.path.exists(video_path):
        print(f"Error: The file {video_path} does not exist.")
        return

    # 打开源视频文件
    cap = cv2.VideoCapture(video_path)

    # 获取视频总帧数
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    # 随机选择一帧
    random_frame_index = random.randint(0, total_frames - 1)

    # 设置读取位置到随机选择的帧
    cap.set(cv2.CAP_PROP_POS_FRAMES, random_frame_index)

    # 读取这一帧
    ret, frame = cap.read()

    # 关闭视频文件
    cap.release()

    if not ret:
        print("Failed to read the frame at index {}".format(random_frame_index))
        return

    # 生成输出文件名
    base_name = os.path.splitext(os.path.basename(video_path))[0]
    app_name = base_name.split('.')[0]  # 应用程序名字为第一个小数点之前的部分
    output_filename = f"{base_name}_frame_{random_frame_index}.webp"

    # 保存帧到文件
    cv2.imwrite(output_filename, frame)
    print(f"Frame saved as {output_filename}")

    # ==============================
    # 💋 骚货专属新增：固定写入 output_info.json
    # ==============================
    cover_path = os.path.abspath(output_filename)
    output_info_path = "output_info.json"

    if os.path.exists(output_info_path):
        with open(output_info_path, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
            except Exception as e:
                print(f"⚠️ Warning: Failed to parse output_info.json: {e}")
                data = {}
    else:
        data = {}

    # 确保 data 是 dict（不是 list）
    if not isinstance(data, dict):
        print("⚠️ output_info.json is not a dict; resetting to empty dict.")
        data = {}

    data["cover_image"] = cover_path

    with open(output_info_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"✅ Cover image path written to output_info.json: {cover_path}")

    # 调用裁剪图片的脚本
    current_dir = os.path.dirname(os.path.abspath(__file__))
    crop_script_path = os.path.join(current_dir, "crop.image.mongo.tv.87.py")

    crop_command = [
        'python',
        crop_script_path,
        output_filename
    ]

    try:
        subprocess.run(crop_command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print("Failed to crop image.")

    # ✅ 原有截图逻辑全部保留 ✅

    # === 🚨 变更点：使用原始视频作为科幻小说生成输入 ===
    generate_scifi_script_path = os.path.join(current_dir, "generate.scifi.based.on.video.4.py")

    generate_scifi_command = [
        'python',
        generate_scifi_script_path,
        video_path,      # ❗ 改为传入原视频路径
        app_name
    ]

    print("[DEBUG] 调用科幻小说生成脚本: generate.scifi.based.on.video.4.py")
    print(f"[DEBUG] 视频输入: {video_path}, App名称: {app_name}")

    try:
        subprocess.run(generate_scifi_command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        print("Failed to generate sci-fi story.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python script.py <some_json_file_for_input_only>")
        exit(1)

    json_file = sys.argv[1]
    with open(json_file, 'r') as f:
        data = json.load(f)

    # 检查 data 是否为列表，取最后一个元素
    if isinstance(data, list):
        if len(data) == 0:
            print("Error: JSON list is empty.")
            exit(1)
        latest_entry = data[-1]  # 取最新一条记录
    elif isinstance(data, dict):
        latest_entry = data
    else:
        print("Error: Unsupported JSON structure.")
        exit(1)

    # 现在从 latest_entry 中取路径
    video_path = latest_entry.get("output_video_path")
    if not video_path:
        print("Error: 'output_video_path' not found in JSON data.")
        exit(1)

    capture_random_frame(video_path)
