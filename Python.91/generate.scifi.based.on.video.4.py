import os
import sys
import base64
import requests
import subprocess
import dashscope
import random
from datetime import datetime
from dashscope.audio.tts import SpeechSynthesizer
import json


# 文件大小阈值：14 MiB（确保 Base64 编码后 < 20MB，以适配百炼 API 限制）
# 计算逻辑：20 MB / 1.33 (Base64 膨胀系数) ≈ 15 MB，留有余量设为 14 MB
MAX_FILE_SIZE_MIB = 14.0
MAX_FILE_SIZE_BYTES = int(MAX_FILE_SIZE_MIB * 1024 * 1024)


# === Coding Plan 配置 ===
# 主用 API Key（主人提供，2026-07-23）
CODING_PLAN_API_KEY = "sk-cp-2MIQ6WIKFj9sZmvWQxX7vv4PI8pZXzqrradj89cm4r1wh7ae7T14UcSZtzfyAaAa4qmb42SZNpUp38UoHu1keP6tlWbI6lYsL263iUJNuii1AtJ2XH10nXw"
# 备用 API Key（限流时切换使用，2026-07-14 旧 key）
BACKUP_API_KEYS = [
    "sk-cp-hXp92UESDiNfV4qDT6ZL2iAbDIdbUOmbYZL8ZmoDDsnKwWl8U9NGnaHW5vDCeMiyRszsqc39c_wFULHHJBE5mmBH04M1MgO3J9gneSVXdNuWHz0Va9ER4H8",
]
CODING_PLAN_BASE_URL = "https://api.minimaxi.com/v1"
CODING_PLAN_MODEL = "MiniMax-M3"
# === 配置结束 ===


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


def trim_video_to_half_duration(input_path, output_path, target_duration=None):
    """裁切视频到指定时长"""
    duration = get_video_duration(input_path)
    if duration is None:
        return False
    
    if target_duration is None:
        target_duration = duration / 2
    
    print(f"📐 视频总时长：{duration:.2f}秒，裁切到：{target_duration:.2f}秒")
    try:
        cmd = [
            'ffmpeg', '-y', '-i', input_path,
            '-t', str(target_duration),
            '-c', 'copy',
            output_path
        ]
        print(f"🔧 执行命令：{' '.join(cmd)}")
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print(f"✅ 视频裁切成功：{output_path}")
            return True
        else:
            print(f"❌ 裁切失败：{result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        print(f"❌ 裁切超时（5 分钟）")
        return False
    except Exception as e:
        print(f"❌ 裁切异常：{e}")
        return False


def check_and_trim_video(video_path):
    """检查视频大小，必要时循环裁切"""
    file_size = get_video_size(video_path)
    file_size_mib = file_size / (1024 * 1024)
    print(f"📁 视频文件大小：{file_size_mib:.2f} MiB")
    
    if file_size <= MAX_FILE_SIZE_BYTES:
        print(f"✅ 文件大小正常（≤{MAX_FILE_SIZE_MIB} MiB），无需裁切")
        return video_path, False, True
    
    print(f"⚠️ 文件过大（>{MAX_FILE_SIZE_MIB} MiB），需要裁切...")
    original_duration = get_video_duration(video_path)
    if original_duration is None:
        return None, True, False
    
    base, ext = os.path.splitext(video_path)
    current_input = video_path
    current_duration = original_duration
    iteration = 0
    max_iterations = 10
    last_successful_output = None
    
    while current_duration > 1.0:
        iteration += 1
        if iteration > max_iterations:
            print(f"⚠️ 已达最大裁切次数（{max_iterations}），停止裁切")
            break
        
        print(f"\n🔄 第 {iteration} 次裁切尝试...")
        temp_path = f"{base}.trimmed.{iteration}{ext}"
        target_duration = current_duration / 2
        print(f"📐 当前时长 {current_duration:.2f}秒，裁切到 {target_duration:.2f}秒...")
        
        if not trim_video_to_half_duration(current_input, temp_path, target_duration):
            if last_successful_output:
                print(f"⚠️ 裁切失败，使用上一次成功的文件：{last_successful_output}")
                return last_successful_output, True, True
            return None, True, False
        
        new_size = get_video_size(temp_path)
        new_size_mib = new_size / (1024 * 1024)
        print(f"📁 裁切后文件大小：{new_size_mib:.2f} MiB")
        
        if new_size <= MAX_FILE_SIZE_BYTES:
            print(f"✅ 文件大小符合要求（≤{MAX_FILE_SIZE_MIB} MiB）")
            return temp_path, True, True
        
        print(f"⚠️ 文件仍然过大，继续裁切...")
        last_successful_output = temp_path
        current_input = temp_path
        current_duration = target_duration
    
    print(f"⚠️ 时长已降至 {current_duration:.2f}秒，无法继续裁切")
    if last_successful_output:
        print(f"📹 使用最后一次成功的文件：{last_successful_output}")
        return last_successful_output, True, True
    return None, True, False


def cleanup_temp_file(temp_path):
    """清理临时文件"""
    try:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
            print(f"🧹 已清理临时文件：{temp_path}")
    except Exception as e:
        print(f"⚠️ 清理临时文件失败：{e}")


def construct_prompt(app_name, media_type="视频"):
    if media_type == "视频":
        return f"以下是这个应用的名字，不要自己猜测应用的名字。结合这段视频内容，写一篇科幻小说，不超过 140 字。开头要给一个吸睛的标题，但是不要用书名号将标题包起来。末尾包含热门的#号标签，标签数量不超过 2, 标签尽可能跟当前这个应用的功能实际相关，并且是常用标签，不用自造标签。如果需要主角的话，女主角就以小美作为主角，一个漂亮的中国女人，男主角就以丧彪作为主角。避免出现 markdown 标记，我目前只需要纯文字的内容。避免将政治相关的东西写入小说中。\n{app_name}"
    else:
        return f"以下是这个应用的名字，不要自己猜测应用的名字。结合这张截屏图片内容，写一篇科幻小说，不超过 140 字。开头要给一个吸睛的标题，但是不要用书名号将标题包起来。末尾包含热门的#号标签，标签数量不超过 2, 标签尽可能跟当前这个应用的功能实际相关，并且是常用标签，不用自造标签。如果需要主角的话，女主角就以小美作为主角，一个漂亮的中国女人，男主角就以丧彪作为主角。避免出现 markdown 标记，我目前只需要纯文字的内容。避免将政治相关的东西写入小说中。\n{app_name}"


# === 关键修改：使用 Base64 编码本地文件 ===
def encode_file_to_base64(file_path):
    """将本地文件编码为 Base64 字符串"""
    try:
        with open(file_path, 'rb') as f:
            file_data = f.read()
        base64_str = base64.b64encode(file_data).decode('utf-8')
        
        # 根据文件扩展名确定 MIME 类型
        ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            '.mp4': 'video/mp4',
            '.mov': 'video/quicktime',
            '.avi': 'video/x-msvideo',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.gif': 'image/gif',
            '.webp': 'image/webp',
            '.bmp': 'image/bmp',
        }
        mime_type = mime_types.get(ext, 'application/octet-stream')
        
        return f"data:{mime_type};base64,{base64_str}"
    except Exception as e:
        print(f"❌ 文件编码失败：{e}")
        return None


def send_request(media_path, prompt, api_key, media_type="video"):
    """使用原生 HTTP 请求调用 Coding Plan 接入点（Base64 模式）"""
    
    # 将本地文件编码为 Base64 Data URL
    base64_url = encode_file_to_base64(media_path)
    if not base64_url:
        return None
    
    file_size_mb = len(base64_url) / 1024 / 1024
    print(f"📦 Base64 编码后大小：{file_size_mb:.2f} MB")
    
    # 构造消息内容（OpenAI 兼容格式）
    if media_type == "video":
        content_list = [
            {"type": "video_url", "video_url": {"url": base64_url}},
            {"type": "text", "text": prompt}
        ]
        print(f"📌 正在调用 Coding Plan qwen3.5-plus (视频模式)...")
    else:
        content_list = [
            {"type": "image_url", "image_url": {"url": base64_url}},
            {"type": "text", "text": prompt}
        ]
        print(f"📌 正在调用 Coding Plan qwen3.5-plus (截屏图片模式)...")
    
    messages = [{'role': 'user', 'content': content_list}]
    print(f"📝 提示词：{prompt}")
    print(f"🔗 使用接入点：{CODING_PLAN_BASE_URL}")
    print(f"🤖 模型：{CODING_PLAN_MODEL}")
    
    # 构造 OpenAI 兼容的请求体
    payload = {
        "model": CODING_PLAN_MODEL,
        "messages": messages
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    url = f"{CODING_PLAN_BASE_URL}/chat/completions"
    
    try:
        print(f"📡 发送 HTTP POST 请求...")
        response = requests.post(url, headers=headers, json=payload, timeout=300)
        print(f"📨 HTTP 状态码：{response.status_code}")
        
        if response.status_code == 429:
            error_text = response.text
            print(f"⚠️ 触发限流 (HTTP 429)：{error_text}")
            return {"error": "RateLimit429", "status_code": 429, "message": error_text}

        if response.status_code != 200:
            error_text = response.text
            print(f"❌ 错误：{error_text}")

            # 🆕 #823789924736 捕获通用 HTTP 500 错误（unknown error, 512 (1000) 等）
            if response.status_code == 500:
                print(f"⚠️ 检测到 HTTP 500 错误（服务端错误），准备降级到截图模式")
                return {"error": "HTTP_500", "status_code": 500, "message": error_text}
            
            if "DataInspectionFailed" in error_text:
                print("⚠️ 检测到 DataInspectionFailed 错误")
                return {"error": "DataInspectionFailed"}
            # 🆕 #818357892915 捕获视频内容敏感错误 (HTTP 422)
            if response.status_code == 422 and ("video is sensitive" in error_text or "new_sensitive" in error_text):
                print("⚠️ 检测到视频内容敏感错误 (video is sensitive)")
                return {"error": "VideoSensitive"}
            return None
        
        result = response.json()
        print("🔍 Raw Response Output:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        
        choices = result.get("choices", [])
        if not choices:
            print("❌ AI 返回结果为空")
            return None
        
        message = choices[0].get("message", {})
        content_text = message.get("content", "")
        print(f"📄 内容类型：{type(content_text)}, 内容：{content_text}")
        
        if isinstance(content_text, str):
            return {"choices": [{"message": {"content": content_text}}]}
        elif isinstance(content_text, list):
            text = ''.join([item['text'] for item in content_text if isinstance(item, dict) and 'text' in item])
            return {"choices": [{"message": {"content": text}}]}
        else:
            print(f"⚠️ 未知 content 格式：{type(content_text)}")
            return None
            
    except requests.exceptions.Timeout:
        print("❌ 请求超时（300 秒）")
        return {"error": "RequestTimeout"}
    except requests.exceptions.SSLError as e:
        # SSL 错误可能是由于内容审核或传输问题，尝试降级到图片模式
        print(f"⚠️ SSL 连接错误（可能触发内容审核或传输限制）：{e}")
        return {"error": "SSLError"}
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求异常：{e}")
        import traceback
        print(f"📋 Traceback:\n{traceback.format_exc()}")
        return {"error": "RequestException"}
    except Exception as e:
        print(f"❌ 请求异常：{e}")
        import traceback
        print(f"📋 Traceback:\n{traceback.format_exc()}")
        return {"error": "UnknownError"}
# === 修改结束 ===


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


# === TTS multi-credential failover (added 2026-10-31) ===
# Previously speech synthesis relied on a single DASHSCOPE_API_KEY env var.
# If that key expired / got disabled / ran out of quota, the whole pipeline
# failed with no fallback. Now several credentials are supported and tried
# one by one: the first one that succeeds wins, and only when all of them
# fail does the script raise an error.
# Credential sources, in priority order:
#   1) config file tts_credentials.json (next to this script)
#   2) env var TTS_API_KEYS (comma separated list of keys)
#   3) env var DASHSCOPE_API_KEY (legacy single key support)
# The config file accepts both a JSON array and plain text (one key per line).

TTS_CREDENTIALS_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "tts_credentials.json"
)


def mask_api_key(api_key):
    """Mask an API key for logging: keep first 8 and last 4 chars only."""
    if not api_key:
        return "(empty)"
    if len(api_key) <= 12:
        return api_key[:4] + "*" * 4
    return api_key[:8] + "*" * 6 + api_key[-4:]


def load_tts_credentials():
    """
    Load TTS credentials, returns [(api_key, note), ...]
    Order: config file -> TTS_API_KEYS -> DASHSCOPE_API_KEY
    """
    credentials = []
    seen = set()

    def add_key(key, note):
        key = (key or "").strip()
        if not key or key in seen:
            return
        seen.add(key)
        credentials.append((key, note))

    # 1) config file
    try:
        if os.path.exists(TTS_CREDENTIALS_FILE):
            with open(TTS_CREDENTIALS_FILE, "r", encoding="utf-8") as f:
                raw = f.read()
            stripped = raw.strip()
            if stripped.startswith("["):
                # JSON array: [{"api_key": "sk-xxx", "note": "primary"}, ...]
                try:
                    items = json.loads(stripped)
                except Exception as e:
                    print(f"WARNING: failed to parse TTS credential JSON: {e}")
                    items = []
                for item in items:
                    if isinstance(item, dict):
                        add_key(item.get("api_key"), item.get("note") or "config file")
                    elif isinstance(item, str):
                        add_key(item, "config file")
            else:
                # plain text: one key per line ('#' starts a comment)
                for line in raw.splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    add_key(line, "config file")
            print(f"Loaded TTS credentials from file: {TTS_CREDENTIALS_FILE}")
    except Exception as e:
        print(f"WARNING: failed to read TTS credential file: {e}")

    # 2) TTS_API_KEYS env var (comma separated)
    env_multi = os.environ.get("TTS_API_KEYS", "")
    if env_multi.strip():
        for key in env_multi.replace(chr(10), ",").split(","):
            add_key(key, "env TTS_API_KEYS")

    # 3) legacy single key env var
    env_single = os.environ.get("DASHSCOPE_API_KEY", "")
    if env_single.strip():
        add_key(env_single, "env DASHSCOPE_API_KEY")

    if credentials:
        print(f"Available TTS credentials: {len(credentials)}")
        for i, (key, note) in enumerate(credentials, 1):
            print(f"   [{i}] {mask_api_key(key)}  ({note})")
    return credentials


def tts_request_with_failover(text, credentials=None):
    """
    Try each TTS credential in turn. Returns the wav path on success,
    or None when every credential failed.
    """
    if credentials is None:
        credentials = load_tts_credentials()
    if not credentials:
        print("ERROR: no TTS credential available")
        print("   Configure tts_credentials.json, or set DASHSCOPE_API_KEY / TTS_API_KEYS")
        return None

    failures = []
    total = len(credentials)
    for idx, (api_key, note) in enumerate(credentials, 1):
        print(f"Trying TTS credential [{idx}/{total}]: {mask_api_key(api_key)}  ({note})")
        output_file = None
        try:
            output_file = tts_request(text, api_key)
        except Exception as e:
            reason = f"{type(e).__name__}: {e}"
            print(f"Credential [{idx}/{total}] raised an exception: {reason}")
        if output_file:
            print(f"SUCCESS: TTS credential [{idx}/{total}] worked: {mask_api_key(api_key)}")
            return output_file
        reason = "no audio data returned"
        failures.append((idx, mask_api_key(api_key), note, reason))
        print(f"Credential [{idx}/{total}] failed: {reason}, trying next...")

    print("ERROR: all TTS credentials failed")
    for idx, masked, note, reason in failures:
        print(f"   [{idx}] {masked} ({note}) -> {reason}")
    return None
# === end of TTS multi-credential failover ===

def save_story_to_file(text):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f'generated_story_{timestamp}.txt'
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(text)
    print(f"SUCCESS: 小说已保存至 {filename}")


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
    # 🆕 解析可选参数 --image / -i：直接以图片模式运行，跳过视频处理与裁切
    image_mode = False
    filtered_argv = []
    for arg in sys.argv[1:]:
        if arg in ("--image", "-i"):
            image_mode = True
        else:
            filtered_argv.append(arg)
    if len(filtered_argv) < 2:
        print("Usage: script.py <video.mp4|image> <app_name> [--image|-i]")
        sys.exit(1)
    
    video_path = filtered_argv[0]
    app_name = filtered_argv[1]
    
    api_key = CODING_PLAN_API_KEY
    print(f"💡 使用 Coding Plan API Key: {api_key[:10]}...")
    print(f"🔗 使用接入点：{CODING_PLAN_BASE_URL}")
    
    # 🆕 图片模式：跳过视频处理与所有视频错误检测，直接进入图片生成流程
    if image_mode:
        if not os.path.exists(video_path):
            print(f"❌ 图片文件不存在：{video_path}")
            sys.exit(1)
        print(f"🖼️ 直接图片模式：{video_path}")
        prompt = construct_prompt(app_name, media_type="截屏图片")
        keys_to_try = [CODING_PLAN_API_KEY] + BACKUP_API_KEYS
        result = None
        for attempt, current_key in enumerate(keys_to_try, 1):
            print(f"\n🔑 尝试 API key {attempt}/{len(keys_to_try)}: {current_key[:10]}...")
            result = send_request(video_path, prompt, current_key, media_type="image")
            if result and isinstance(result, dict) and result.get("error") == "RateLimit429":
                print(f"⚠️ API key {attempt} 触发限流，尝试下一个 key...")
                result = None
                continue
            break
        if result is None:
            print("❌ 所有 API key 都不可用")
            sys.exit(1)
        if result and isinstance(result, dict) and result.get("error"):
            print(f"❌ 图片生成失败 (错误：{result.get('error')})，无法生成小说")
            sys.exit(1)
        # 直接复用现有"生成成功后写文件"的代码块
        if result and 'choices' in result and len(result['choices']) > 0:
            # === 直接图片模式专用：读 output_info.json 用作 title / 后续写回 ===
            output_info_path = 'output_info.json'
            try:
                with open(output_info_path, 'r', encoding='utf-8') as f:
                    output_info = json.load(f)
            except FileNotFoundError:
                print(f"⚠️ {output_info_path} 不存在，使用空配置")
                output_info = {}
            except json.JSONDecodeError as e:
                print(f"⚠️ 解析 {output_info_path} 失败：{e}")
                output_info = {}
            
            generated_text = result['choices'][0]['message']['content']
            import re
            generated_text = re.sub(r'<think>.*?</think>', '', generated_text, flags=re.DOTALL)
            generated_text = generated_text.strip()
            generated_text = generated_text + ' '
            print("Generated Sci-fi Story:")
            print(generated_text)
            save_story_to_file(generated_text)
            
            video_title = output_info.get("title", "").strip()
            if not video_title:
                print("Warning: 'title' is missing or empty in output_info.json")
                video_title = "Untitled"
            
            description = f"{video_title} {generated_text}".strip()
            print("\n=== Final Description (Copy for platforms) ===")
            print(description)
            print("==============================================")
            
            output_info["description"] = description
            try:
                with open(output_info_path, 'w', encoding='utf-8') as f:
                    json.dump(output_info, f, ensure_ascii=False, indent=4)
                print(f"SUCCESS: Description 已追加到 {output_info_path}")
            except Exception as e:
                print(f"Error writing to {output_info_path}: {e}")
            
            tts_credentials = load_tts_credentials()
            if not tts_credentials:
                print("ERROR: no TTS credential found, cannot run speech synthesis")
                sys.exit(1)
            output_file = tts_request_with_failover(generated_text, tts_credentials)
            if output_file:
                    print(f"语音文件已保存至：{output_file}")
                    current_script_path = os.path.abspath(__file__)
                    script_dir = os.path.dirname(current_script_path)
                    second_script_path = os.path.join(script_dir, '..', 'ruby.he', 'generate.face.video.p4.rb')
                    candidate_images = load_face_templates()
                    selected_image = random.choice(candidate_images)
                    video_template_path = os.path.join(script_dir, '..', 'material.ache', 'image.e', selected_image)
                    second_script_path = os.path.abspath(second_script_path)
                    video_template_path = os.path.abspath(video_template_path)
                    subprocess.call(['ruby', second_script_path, output_file, video_template_path])
        else:
            print("❌ 图片生成结果为空")
            sys.exit(1)
        sys.exit(0)
    
    processed_video_path, was_trimmed, trim_success = check_and_trim_video(video_path)
    
    if was_trimmed and not trim_success:
        print("❌ 视频裁切失败，无法继续")
        sys.exit(1)
    
    if was_trimmed:
        print(f"📹 使用处理后的视频：{processed_video_path}")
    
    prompt = construct_prompt(app_name, media_type="视频")
    # 🆕 #848622252536 遇到 429 限流时自动切换备用 API key 重试
    keys_to_try = [CODING_PLAN_API_KEY] + BACKUP_API_KEYS
    result = None
    for attempt, current_key in enumerate(keys_to_try, 1):
        print(f"\n🔑 尝试 API key {attempt}/{len(keys_to_try)}: {current_key[:10]}...")
        result = send_request(processed_video_path, prompt, current_key, media_type="video")
        if result and isinstance(result, dict) and result.get("error") == "RateLimit429":
            print(f"⚠️ API key {attempt} 触发限流，尝试下一个 key...")
            result = None
            continue
        # 成功获取结果或非限流错误（如 DataInspectionFailed）跳出循环
        break
    if result is None:
        print("❌ 所有 API key 都不可用")
        sys.exit(1)
    
    if was_trimmed and processed_video_path:
        cleanup_temp_file(processed_video_path)
    
    use_screenshot = False
    # 检查是否需要回退到截屏图片方式（包括 DataInspectionFailed、SSL 错误、超时、HTTP 500 等）
    error_type = result.get("error") if result and isinstance(result, dict) else None
    if error_type in ["DataInspectionFailed", "VideoSensitive", "SSLError", "RequestTimeout", "RequestException", "HTTP_500"]:
        print(f"\n🔄 检测到错误 ({error_type})，尝试回退到截屏图片方式...")
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
            prompt = construct_prompt(app_name, media_type="截屏图片")
            # 🆕 #848622252536 截图模式也尝试多个 key
            for attempt, current_key in enumerate(keys_to_try, 1):
                result = send_request(screenshot_path, prompt, current_key, media_type="image")
                if result and isinstance(result, dict) and result.get("error") == "RateLimit429":
                    print(f"⚠️ 截图模式 key {attempt} 触发限流，尝试下一个...")
                    result = None
                    continue
                break
            if result is None:
                print("❌ 截图模式所有 API key 都不可用")
        else:
            print("❌ 无法回退到截屏图片方式，生成失败")
            sys.exit(1)
    
    if result and isinstance(result, dict) and result.get("error"):
        print(f"❌ 截屏图片方式也失败 (错误：{result.get('error')})，无法生成小说")
        sys.exit(1)
    
    if result and 'choices' in result and len(result['choices']) > 0:
        generated_text = result['choices'][0]['message']['content']
        # === Fix for minimax-M3 think blocks (2026-06-14, task #814331422060) ===
        # M3 model returns <think>...</think> reasoning blocks mixed into content.
        # Stripping them prevents story inflation, which would otherwise make
        # downstream TTS audio very long and SadTalker exceed the FC 440s timeout.
        import re
        generated_text = re.sub(r'<think>.*?</think>', '', generated_text, flags=re.DOTALL)
        generated_text = generated_text.strip()
        generated_text = generated_text + ' '
        print("Generated Sci-fi Story:")
        print(generated_text)
        save_story_to_file(generated_text)
        
        output_info_path = 'output_info.json'
        try:
            with open(output_info_path, 'r', encoding='utf-8') as f:
                output_info = json.load(f)
            video_title = output_info.get("title", "").strip()
            if not video_title:
                print("Warning: 'title' is missing or empty in output_info.json")
                video_title = "Untitled"
        except FileNotFoundError:
            print(f"Error: {output_info_path} not found.")
            sys.exit(1)
        except json.JSONDecodeError as e:
            print(f"Error: Failed to parse {output_info_path}: {e}")
            sys.exit(1)
        
        description = f"{video_title} {generated_text}".strip()
        print("\n=== Final Description (Copy for platforms) ===")
        print(description)
        print("==============================================")
        
        output_info["description"] = description
        try:
            with open(output_info_path, 'w', encoding='utf-8') as f:
                json.dump(output_info, f, ensure_ascii=False, indent=4)
            print(f"SUCCESS: Description 已追加到 {output_info_path}")
        except Exception as e:
            print(f"Error writing to {output_info_path}: {e}")
        
        # Speech synthesis uses pay-per-use API keys (not Coding Plan keys).
        # Multiple credentials are tried one by one until one succeeds.
        tts_credentials = load_tts_credentials()
        if not tts_credentials:
            print("ERROR: no TTS credential found, cannot run speech synthesis")
            import sys
            sys.exit(1)
        output_file = tts_request_with_failover(generated_text, tts_credentials)
        if output_file:
                print(f"语音文件已保存至：{output_file}")
                current_script_path = os.path.abspath(__file__)
                script_dir = os.path.dirname(current_script_path)
                second_script_path = os.path.join(script_dir, '..', 'ruby.he', 'generate.face.video.p4.rb')
                candidate_images = load_face_templates()
                selected_image = random.choice(candidate_images)
                video_template_path = os.path.join(script_dir, '..', 'material.ache', 'image.e', selected_image)
                second_script_path = os.path.abspath(second_script_path)
                video_template_path = os.path.abspath(video_template_path)
                subprocess.call(['ruby', second_script_path, output_file, video_template_path])
    else:
        print("Failed to generate story.")