#!/usr/bin/env python3
"""
盲盒 TTS 试听工具

用法:
    python3 tts_preview.py                     # 默认音色（知婷）
    python3 tts_preview.py zhiting              # 指定音色
    python3 tts_preview.py zhiting "自定义台词"   # 指定音色 + 台词
    python3 tts_preview.py --list              # 列出可用音色

可用音色:
  sambert 系列 (走 WebSocket 端点)
    zhiting   知婷（女，主人原音色）
    zhichu    智楚（女）
    zhixiao   智晓（女）
    zhiru     智如（女）
    zhiyuan   智远（男）
    yunxi     云汐（女）
  qwen3-tts 系列 (走 HTTP 端点)
    Cherry    樱桃（女）
    Serena    塞雷娜（女）
    Chelsie   巧慧（女）
    Ethan     伊森（男）

输出: /tmp/tts_<voice>.wav
"""
import json, os, sys, urllib.request, urllib.error

KEY = "sk-ws-H.EPREERH.XR6n.MEQCIADLHkp2v3Xjj_ccFeFexk8psqPlta3LESHwAo-U8ovrAiAoz1erLyb9fkEP98iMUn2-en5V77tvtlJ6EXhxcIEDAw"
WS_HOST = "wss://dashscope.aliyuncs.com/api-ws/v1/inference"
HTTP_HOST = "https://ws-83f1vjop70pg12u2.cn-beijing.maas.aliyuncs.com"

# sambert 音色走 WebSocket；其余走 HTTP
SAMBERT_VOICES = {
    "zhiting": "知婷(女)", "zhichu": "智楚(女)", "zhixiao": "智晓(女)",
    "zhiru": "智如(女)", "zhiyuan": "智远(男)", "yunxi": "云汐(女)",
}
QWEN_VOICES = {
    "Cherry": "樱桃(女)", "Serena": "塞雷娜(女)",
    "Chelsie": "巧慧(女)", "Ethan": "伊森(男)",
}


def synth_sambert(text, voice, out_path):
    """sambert 走 dashscope SDK 的 WebSocket 端点"""
    os.environ["DASHSCOPE_API_KEY"] = KEY
    import dashscope
    from dashscope.audio.tts import SpeechSynthesizer
    dashscope.api_key = KEY
    r = SpeechSynthesizer.call(model="sambert-%s-v1" % voice, text=text,
                              voice=voice, sample_rate=16000,
                              base_address=WS_HOST)
    data = r.get_audio_data()
    if not data:
        raise RuntimeError("no audio: %s" % str(r.get_response())[:200])
    open(out_path, "wb").write(data)
    return len(data)


def synth_qwen(text, voice, out_path):
    """qwen3-tts 走业务空间 HTTP generation 端点"""
    url = HTTP_HOST + "/api/v1/services/aigc/multimodal-generation/generation"
    payload = {"model": "qwen3-tts-flash",
               "input": {"text": text, "voice": voice, "language_type": "Chinese"}}
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode("utf-8"))
    audio = ((data.get("output") or {}).get("audio") or {})
    if audio.get("data"):
        import base64
        raw = base64.b64decode(audio["data"])
    elif audio.get("url"):
        with urllib.request.urlopen(audio["url"], timeout=90) as r:
            raw = r.read()
    else:
        raise RuntimeError("no audio in response: %s" % str(data)[:200])
    open(out_path, "wb").write(raw)
    return len(raw)


def main():
    args = sys.argv[1:]
    if args and args[0] == "--list":
        print("可用音色:")
        print("  sambert 系列 (WebSocket):")
        for k, v in SAMBERT_VOICES.items():
            print("    %-10s %s" % (k, v))
        print("  qwen3-tts 系列 (HTTP):")
        for k, v in QWEN_VOICES.items():
            print("    %-10s %s" % (k, v))
        return
    voice = args[0] if len(args) > 0 else "zhiting"
    text = args[1] if len(args) > 1 else "你好，这是盲盒故事配音测试。"
    out = "/tmp/tts_%s.wav" % voice
    if voice in SAMBERT_VOICES:
        n = synth_sambert(text, voice, out)
    elif voice in QWEN_VOICES:
        n = synth_qwen(text, voice, out)
    else:
        print("未知音色 %s，尝试按 sambert 处理" % voice)
        n = synth_sambert(text, voice, out)
    print("OK %s -> %s (%d bytes)" % (voice, out, n))


if __name__ == "__main__":
    main()
