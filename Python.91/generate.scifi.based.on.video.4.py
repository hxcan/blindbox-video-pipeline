import os
import sys
import base64
import requests
import subprocess
import dashscope
import random
from datetime import datetime
from dashscope.audio.tts import SpeechSynthesizer
from dashscope import MultiModalConversation
import json


# 文件大小阈值：338.4 MiB
MAX_FILE_SIZE_MIB = 338.4
MAX_FILE_SIZE_BYTES = int(MAX_FILE_SIZE_MIB * 1024 * 1024)


def get_video_duration(video_path):
    """获取视频时长（秒）"""
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', 
            '-of', 'default=noprint_wrappers=1:nokey=1', video_path],
            capture_output=True, text=True, timeout=30
        )
        duration = float(result.stdout.strip())
        return duration
    except Exception as e:
        print(f"⚠️ 获取视频时长失败：{e}")
        return None


def get_video_size(video_path):
    """获取视频文件大小（字节）"""
    try:
        return os.path.getsize(video_path)
    except Exception as e:
        print(f"⚠️ 获取视频大小失败：{e}")
        return 0


def trim_video_to_half_duration(input_path, output_path):
    """裁切视频到一半时长
    
    Args:
        input_path: 输入视频路径
        output_path: 输出临时视频路径
        
    Returns:
        bool: 是否成功
    """
    # 获取原始视频时长
    duration = get_video_duration(input_path)
    if duration is None:
        return False
    
    # 计算一半时长
    half_duration = duration / 2
    print(f"📐 视频总时长：{duration:.2f}秒，裁切到：{half_duration:.2f}秒")
    
    # 使用ffmpeg裁切前一半
    try:
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-t', str(half_duration),
            '-c', 'copy',  # 直接复制，不重新编码，速度快
            output_path
        ]
        print(f"🔧 执行命令：{' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )
        
        if result.returncode == 0:
            print(f"✅ 视频裁切成功：{output_path}")
            return True
        else:
            print(f"❌ 裁切失败：{result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"❌ 裁切超时（5分钟）")
        return False
    except Exception as e:
        print(f"❌ 裁切异常：{e}")
        return False


def check_and_trim_video(video_path):
    """检查视频大小，必要时裁切
    
    Args:
        video_path: 原始视频路径
        
    Returns:
        tuple: (处理后的视频路径, 是否需要裁切, 是否成功)
        - 如果不需要裁切，返回 (原路径, False, True)
        - 如果裁切成功，返回 (临时文件路径, True, True)
        - 如果裁切失败，返回 (None, True, False)
    """
    # 检查文件大小
    file_size = get_video_size(video_path)
    file_size_mib = file_size / (1024 * 1024)
    print(f"📁 视频文件大小：{file_size_mib:.2f} MiB")
    
    if file_size <= MAX_FILE_SIZE_BYTES:
        print(f"✅ 文件大小正常（≤{MAX_FILE_SIZE_MIB} MiB），无需裁切")
        return video_path, False, True
    
    print(f"⚠️ 文件过大（>{MAX_FILE_SIZE_MIB} MiB），需要裁切...")
    
    # 生成临时文件路径
    base, ext = os.path.splitext(video_path)
    temp_path = f"{base}.trimmed{ext}"
    
    # 执行裁切
    if trim_video_to_half_duration(video_path, temp_path):
        temp_size = get_video_size(temp_path)
        temp_size_mib = temp_size / (1024 * 1024)
        print(f"✅ 裁切后文件大小：{temp_size_mib:.2f} MiB")
        return temp_path, True, True
    else:
        return None, True, False


def cleanup_temp_file(temp_path):
    """清理临时文件"""
    try:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            print(f"🧹 已清理临时文件：{temp_path}")
    except Exception as e:
        print(f"⚠️ 清理临时文件失败：{e}")


# 构造提示词（支持视频或截屏图片）
def construct_prompt(app_name, media_type="视频"):
    if media_type == "视频":
        return f"以下是这个应用的名字，不要自己猜测应用的名字。结合这段视频内容，写一篇科幻小说，不超过 140 字。开头要给一个吸睛的标题，但是不要用书名号将标题包起来。末尾包含热门的#号标签，标签数量不超过 2, 标签尽可能跟当前这个应用的功能实际相关，并且是常用标签，不用自造标签。如果需要主角的话，女主角就以小美作为主角，一个漂亮的中国女人，男主角就以丧彪作为主角。避免出现 markdown 标记，我目前只需要纯文字的内容。避免将政治相关的东西写入小说中。\n{app_name}"
    else:  # 截屏图片
        return f"以下是这个应用的名字，不要自己猜测应用的名字。结合这张截屏图片内容，写一篇科幻小说，不超过 140 字。开头要给一个吸睛的标题，但是不要用书名号将标题包起来。末尾包含热门的#号标签，标签数量不超过 2, 标签尽可能跟当前这个应用的功能实际相关，并且是常用标签，不用自造标签。如果需要主角的话，女主角就以小美作为主角，一个漂亮的中国女人，男主角就以丧彪作为主角。避免出现 markdown 标记，我目前只需要纯文字的内容。避免将政治相关的东西写入小说中。\n{app_name}"


# 发送请求生成短科幻小说（支持视频或截屏图片）
def send_request(media_path, prompt, api_key, media_type="video"):
    file_url = f"file:///{os.path.abspath(media_path)}"
    
    if media_type == "video":
        content_list = [{'video': file_url, 'fps': 1, 'max_frames': 20}, {'text': prompt}]
        print(f"📌 正在调用 MultiModalConversation (视频模式)...")
        print(f"📁 视频路径：{file_url}")
    else:  # image
        content_list = [{'image': file_url}, {'text': prompt}]
        print(f"📌 正在调用 MultiModalConversation (截屏图片模式)...")
        print(f"🖼️ 图片路径：{file_url}")
    
    messages = [
        {
            'role': 'user',
            'content': content_list
        }
    ]
    print(f"📝 提示词：{prompt}")
    try:
        response = MultiModalConversation.call(
            api_key=api_key,
            model='qwen-vl-max-latest',
            messages=messages
        )
        print(f"📨 响应状态：{response.status_code}")
        if response.status_code != 200:
            print(f"❌ 错误代码：{response.code}, 消息：{response.message}")
            # 检查是否是 DataInspectionFailed 错误
            if response.code == "DataInspectionFailed" or "DataInspectionFailed" in str(response.message):
                print("⚠️ 检测到 DataInspectionFailed 错误，视频内容可能包含不当元素")
                return {"error": "DataInspectionFailed"}
            return None
        # 👁️ 调试输出 raw 结构
        print("🔍 Raw Response Output:")
        print(json.dumps(response.output, ensure_ascii=False, indent=2))
        output = response.output
        choices = output.get("choices", [])
        if not choices:
            print("❌ AI 返回结果为空")
            return None
        message = choices[0].get("message", {})
        content = message.get("content", "")
        print(f"📄 内容类型：{type(content)}, 内容：{content}")
        # ✅ 安全处理 content
        if isinstance(content, str):
            return {"choices": [{"message": {"content": content}}]}
        elif isinstance(content, list):
            text = ''.join([item['text'] for item in content if isinstance(item, dict) and 'text' in item])
            return {"choices": [{"message": {"content": text}}]}
        else:
            print(f"⚠️ 未知 content 格式：{type(content)}")
            return None
    except Exception as e:
        import traceback
        print(f"❌ 请求异常：{e}")
        print(f"📋 Traceback:\n{traceback.format_exc()}")
        return None


# 使用 Sambert 语音合成
def tts_request(text, api_key):
    dashscope.api_key = api_key
    result = SpeechSynthesizer.call(
        model='sambert-zhiting-v1',
        text=text,
        sample_rate=16000
    )
    if result.get_audio_data() is not None:
        output_file_path = './generated_story.wav'
        with open(output_file_path, 'wb') as f:
            f.write(result.get_audio_data())
        print(f'SUCCESS: get audio data in {output_file_path}')
        return output_file_path
    else:
        print('ERROR: response is %s' % (result.get_response()))
        return None


# 保存小说到带时间戳的文本文件
def save_story_to_file(text):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f'generated_story_{timestamp}.txt'
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"SUCCESS: 小说已保存至 {filename}")


# 加载人脸模板列表
def load_face_templates():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(script_dir, '..', 'Material', 'assets')
    json_path = os.path.join(assets_dir, 'face_templates.json')
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"❌ 未找到人脸模板配置文件：{json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return [item['filename'] for item in data['faces']]


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: script.py <video.mp4> <app_name>")
        sys.exit(1)
    
    video_path = sys.argv[1]
    app_name = sys.argv[2]
    
    # 从环境变量读取 API Key（推荐方式）
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    
    if not api_key:
        print("❌ 错误：未找到 DASHSCOPE_API_KEY 环境变量")
        print("💡 请设置环境变量后运行:")
        print("   export DASHSCOPE_API_KEY='your-api-key-here'")
        print("或者在 ~/.bashrc 或 ~/.zshrc 中添加:")
        print("   export DASHSCOPE_API_KEY='your-api-key-here'")
        sys.exit(1)
    
    # === 新增：检查并裁切大视频 ===
    processed_video_path, was_trimmed, trim_success = check_and_trim_video(video_path)
    
    if was_trimmed and not trim_success:
        print("❌ 视频裁切失败，无法继续")
        sys.exit(1)
    
    if was_trimmed:
        print(f"📹 使用处理后的视频：{processed_video_path}")
    # === 新增结束 ===
    
    # 第一次尝试：使用视频生成小说
    prompt = construct_prompt(app_name, media_type="视频")
    result = send_request(processed_video_path, prompt, api_key, media_type="video")
    
    # === 新增：清理临时文件 ===
    if was_trimmed and processed_video_path:
        cleanup_temp_file(processed_video_path)
    # === 新增结束 ===
    
    # 检查是否需要回退到截屏图片方式
    use_screenshot = False
    if result and isinstance(result, dict) and result.get("error") == "DataInspectionFailed":
        print("\n🔄 检测到 DataInspectionFailed 错误，尝试回退到截屏图片方式...")
        
        # 从当前工作目录的 output_info.json 读取截屏图片路径
        output_info_path = os.path.join(os.getcwd(), "output_info.json")
        screenshot_path = None
        
        if os.path.exists(output_info_path):
            try:
                with open(output_info_path, 'r', encoding='utf-8') as f:
                    output_info = json.load(f)
                screenshot_path = output_info.get("cover_image")
                
                if screenshot_path and os.path.exists(screenshot_path):
                    print(f"✅ 找到截屏图片：{screenshot_path}")
                    use_screenshot = True
                else:
                    print("⚠️ output_info.json 中未找到有效的 cover_image 路径")
            except Exception as e:
                print(f"⚠️ 读取 output_info.json 失败：{e}")
        else:
            print(f"⚠️ output_info.json 不存在：{output_info_path}")
        
        if use_screenshot:
            # 使用截屏图片重新生成小说
            prompt = construct_prompt(app_name, media_type="截屏图片")
            result = send_request(screenshot_path, prompt, api_key, media_type="Image")
        else:
            print("❌ 无法回退到截屏图片方式，生成失败")
            sys.exit(1)
    
    if result and isinstance(result, dict) and result.get("error") == "DataInspectionFailed":
        print("❌ 截屏图片方式也失败，无法生成小说")
        sys.exit(1)
    
    if result and 'choices' in result and len(result['choices']) > 0:
        generated_text = result['choices'][0]['message']['content']
        generated_text = generated_text + ' '
        print("Generated Sci-fi Story:")
        print(generated_text)
        # 保存小说到文本文件（带时间戳）
        save_story_to_file(generated_text)
        # === 新增：读取 output_info.json 获取 title，并生成 description ===
        output_info_path = 'output_info.json'
        try:
            with open(output_info_path, 'r', encoding='utf-8') as f:
                output_info = json.load(f)
            video_title = output_info.get("title", "").strip()
            if not video_title:
                print("Warning: 'title' is missing or empty in output_info.json")
                video_title = "Untitled"
        except FileNotFoundError:
            print(f"Error: {output_info_path} not found. Please run video.fps.60.rb first.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse {output_info_path}: {e}")
            sys.exit(1)
        # 拼接 description
        description = f"{video_title} {generated_text}".strip()
        # 输出到终端（便于手动复制到各平台）
        print("\n=== Final Description (Copy for platforms) ===")
        print(description)
        print("==============================================")
        # 写回 output_info.json，追加 description 字段
        output_info["description"] = description
        try:
            with open(output_info_path, 'w', encoding='utf-8') as f:
                json.dump(output_info, f, ensure_ascii=False, indent=4)
            print(f"SUCCESS: Description 已追加到 {output_info_path}")
        except Exception as e:
            print(f"Error writing to {output_info_path}: {e}")
        # === 原有逻辑继续：TTS 和调用 Ruby 脚本 ===
        output_file = tts_request(generated_text, api_key)
        if output_file:
            print(f"语音文件已保存至：{output_file}")
            current_script_path = os.path.abspath(__file__)
            script_dir = os.path.dirname(current_script_path)
            second_script_path = os.path.join(script_dir, '..', 'ruby.he', 'generate.face.video.p4.rb')
            # ✅ 加载外部模板列表
            candidate_images = load_face_templates()
            selected_image = random.choice(candidate_images)
            video_template_path = os.path.join(script_dir, '..', 'material.ache', 'image.e', selected_image)
            second_script_path = os.path.abspath(second_script_path)
            video_template_path = os.path.abspath(video_template_path)
            subprocess.call(['ruby', second_script_path, output_file, video_template_path])
    else:
        print("Failed to generate story.")
