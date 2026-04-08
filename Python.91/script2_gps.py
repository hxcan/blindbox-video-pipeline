#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# script2_gps.py

import os
import sys
import subprocess
import random
import math
import json
from datetime import datetime
from pathlib import Path
import argparse

def load_twitter_credentials():
    """
    从环境变量或 ~/.blindbox/twitter.json 加载 Twitter API 凭据
    返回 dict 或 None（若均未找到）
    """
    # 1. 尝试从环境变量加载
    creds = {
        "consumer_key": os.getenv("TWITTER_CONSUMER_KEY"),
        "consumer_secret": os.getenv("TWITTER_CONSUMER_SECRET"),
        "access_token": os.getenv("TWITTER_ACCESS_TOKEN"),
        "access_token_secret": os.getenv("TWITTER_ACCESS_TOKEN_SECRET"),
    }

    if all(creds.values()):
        print("🔑 Twitter 凭据已从环境变量加载")
        return creds

    # 2. 回退到配置文件 ~/.blindbox/twitter.json
    config_path = Path.home() / ".blindbox" / "twitter.json"
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                file_creds = json.load(f)
            # 映射字段（支持常见命名）
            creds_from_file = {
                "consumer_key": file_creds.get("consumer_key") or file_creds.get("api_key"),
                "consumer_secret": file_creds.get("consumer_secret") or file_creds.get("api_secret"),
                "access_token": file_creds.get("access_token"),
                "access_token_secret": file_creds.get("access_token_secret"),
            }
            if all(creds_from_file.values()):
                print(f"🔑 Twitter 凭据已从配置文件加载: {config_path}")
                return creds_from_file
            else:
                missing = [k for k, v in creds_from_file.items() if not v]
                print(f"⚠️ 配置文件 {config_path} 缺少必要字段: {missing}")
        else:
            print(f"⚠️ Twitter 配置文件不存在: {config_path}")
    except Exception as e:
        print(f"❌ 读取 Twitter 配置文件失败: {e}")

    # 3. 仍缺失
    print("❌ 未找到完整的 Twitter API 凭据（环境变量或 ~/.blindbox/twitter.json）")
    return None


def dec_to_dms_str(deg):
    """将十进制度转换为 DMS 字符串（exiftool 格式）"""
    d = int(abs(deg))
    m = int((abs(deg) - d) * 60)
    s = round((abs(deg) - d - m/60) * 3600, 2)
    return f"{d} deg {m}' {s:.2f}\""


# -------------------------------
# 🔧 新增：从 assets/video_templates.json 加载候选视频文件列表
# -------------------------------
def get_real_video_clips():
    """
    从 ../Material/assets/video_templates.json 加载候选视频文件列表
    使用脚本自身路径作为基准，确保路径稳定
    """
    script_dir = Path(__file__).parent  # 脚本所在目录
    assets_dir = script_dir / "../Material/assets"  # 相对路径
    json_path = assets_dir / "video_templates.json"

    if not json_path.exists():
        print(f"❌ 配置文件不存在: {json_path}")
        return []

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            filenames = json.load(f)
        if not isinstance(filenames, list):
            print(f"❌ 配置文件格式错误，应为 JSON 数组: {json_path}")
            return []
    except Exception as e:
        print(f"❌ 读取配置文件失败: {e}")
        return []

    # 构建完整路径
    material_dir = script_dir / "../Material/Movie"
    material_dir = material_dir.resolve()
    video_files = []

    for fname in filenames:
        video_path = material_dir / fname
        if video_path.exists():
            video_files.append(video_path)
        else:
            print(f"⚠️ 候选视频文件不存在，已跳过: {video_path}")

    if not video_files:
        print("❌ 无可用的真实候选视频文件，请检查路径和文件名。")

    return video_files


# -------------------------------
# 🔧 新增：从真实视频复制元数据
# -------------------------------
def inject_gps_from_real_clip(input_path, output_path):
    """
    从随机真实拍摄的视频中复制全部元数据（包括GPS）
    """
    clips = get_real_video_clips()
    if not clips:
        print("⚠️ 无可用真实素材视频，无法注入GPS")
        return False

    source_video = random.choice(clips)
    print(f"📱 使用真实素材视频元数据源: {source_video.name}")

    # 构建 exiftool 命令：从源视频复制所有元数据到目标
    cmd = [
        "exiftool",
        "-overwrite_original",
        "-api", "QuickTimeLarge",
        "-TagsFromFile", str(source_video),
        "-all:all>all:all",  # 复制所有元数据（含GPS、时间、设备等）
        output_path
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ 元数据已从真实视频复制: {source_video.name}")
            print(f"📊 来源: 📱 真实手机拍摄素材")
            return True
        else:
            print(f"❌ exiftool 错误（真实素材）: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ 执行失败（真实素材）: {e}")
        return False


# -------------------------------
# ✅ 主注入函数：仅保留真实视频模式
# -------------------------------
def inject_gps_metadata(input_path, output_path):
    """
    主函数：仅从真实视频复制元数据（已知有效）
    移除了坐标池和随机全球坐标注入逻辑
    """
    print("🎲 GPS来源选择: real_clip（仅保留真实素材）")

    return inject_gps_from_real_clip(input_path, output_path)


# -------------------------------
# ✅ 主函数（修改版：支持 title 命名 + 自动上传 + 正确调用顺序）
# -------------------------------
def main():
    parser = argparse.ArgumentParser(description="注入GPS坐标并控制后续流程")
    parser.add_argument("input_video", help="输入视频文件路径")
    parser.add_argument(
        "--run_continue",
        choices=["true", "false"],
        default="true",
        help="是否继续后续步骤。默认为 true（保持原有行为）"
    )

    args = parser.parse_args()

    input_video = args.input_video
    if not os.path.exists(input_video):
        print(f"❌ 文件不存在: {input_video}")
        sys.exit(1)

    continue_after = args.run_continue == "true"

    # === 读取 output_info.json 获取 title、description 和 cover_image ===
    import json
    output_info_path = os.path.join(os.path.dirname(input_video), "output_info.json")
    try:
        with open(output_info_path, 'r', encoding='utf-8') as f:
            output_info = json.load(f)
        title = output_info.get("title", "").strip()
        description = output_info.get("description", "").strip()
        cover_image = output_info.get("cover_image", "").strip()
    except FileNotFoundError:
        print(f"⚠️ 未找到 {output_info_path}，使用默认命名规则")
        title = ""
        description = ""
        cover_image = ""
    except Exception as e:
        print(f"⚠️ 读取 output_info.json 失败: {e}")
        title = ""
        description = ""
        cover_image = ""

    # === 输出文件名：优先使用 title，否则回退到 _gps.mp4 ===
    if title:
        output_video = os.path.join(os.path.dirname(input_video), f"{title}.mp4")
    else:
        output_video = input_video.replace(".mp4", "_gps.mp4")

    # 复制原始文件
    os.system(f"cp '{input_video}' '{output_video}'")

    print(f"📍 正在为视频注入 GPS: {os.path.basename(input_video)}")
    success = inject_gps_metadata(input_video, output_video)

    if success:
        try:
            result = subprocess.run(
                ["exiftool", "-Duration", "-T", output_video],
                capture_output=True, text=True
            )
            duration_line = [l for l in result.stdout.split('\n') if 'Duration' in l]
            if duration_line:
                duration = duration_line[0].split()[-1]
                print(f"📊 检测到视频时长: {duration}")
        except:
            pass

        print("✅ GPS 注入流程完成")

        # ✅ 正确顺序：先调用时长裁剪脚本
        crop_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "script3_crop.py")
        print(f"✂️ 正在调用时长裁剪脚本: {crop_script}")
        try:
            subprocess.run(["python", crop_script, output_video], check=True)
            print("✅ 时长裁剪完成，输出文件已生成")
        except subprocess.CalledProcessError as e:
            print(f"❌ 时长裁剪失败: {e}")
            sys.exit(1)

        # ✅ 仅当 continue_after 为 True 时才调用发布脚本
        if continue_after:
            try:
                # 获取当前Python脚本所在目录
                script_dir = os.path.dirname(os.path.abspath(__file__))

                # 构造Ruby脚本的相对路径（相对于Python脚本目录）
                ruby_script_path = os.path.join(script_dir, "..", "ruby.he", "publish_all_platforms.rb")

                # 转换为绝对路径
                ruby_script = os.path.abspath(ruby_script_path)

                print(f"📤 正在调用Ruby发布脚本: {ruby_script}")
                subprocess.run(["ruby", ruby_script, output_video], check=True)
                print("✅ 所有平台发布完成")
            except subprocess.CalledProcessError as e:
                print(f"❌ Ruby发布脚本执行失败: {e}")
            except Exception as e:
                print(f"❌ 调用Ruby脚本时发生异常: {e}")
        else:
            print("⏸️  --run_continue false 已启用，跳过发布流程")

    else:
        print("❌ GPS 注入失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
