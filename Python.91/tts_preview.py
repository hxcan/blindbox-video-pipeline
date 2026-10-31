#!/usr/bin/env python3
"""
盲盒 TTS 试听工具（百炼业务空间 key）

用法:
    python3 tts_preview.py                     # 用配置里的默认音色合成
    python3 tts_preview.py Cherry               # 指定音色
    python3 tts_preview.py Serena "自定义台词"    # 指定音色 + 台词
    python3 tts_preview.py --list              # 列出可用音色

可用音色: Cherry(女) Serena(女) Chelsie(女) Ethan(男)
输出: /tmp/tts_<voice>.wav
"""
import json, os, sys, urllib.request

KEY = "sk-ws-H.EPREERH.XR6n.MEQCIADLHkp2v3Xjj_ccFeFexk8psqPlta3LESHwAo-U8ovrAiAoz1erLyb9fkEP98iMUn2-en5V77tvtlJ6EXhxcIEDAw"
URL = ("https://ws-83f1vjop70pg12u2.cn-beijing.maas.aliyuncs.com"
       "/api/v1/services/aigc/multimodal-generation/generation")
VOICES = ["Cherry", "Serena", "Chelsie", "Ethan"]


def synth(text, voice, out_path):
    payload = {"model": "qwen3-tts-flash",
               "input": {"text": text, "voice": voice, "language_type": "Chinese"}}
    req = urllib.request.Request(
        URL, data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + KEY,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = json.loads(r.read().decode("utf-8"))
    audio_url = ((data.get("output") or {}).get("audio") or {}).get("url")
    if not audio_url:
        raise RuntimeError("no audio url: %s" % str(data)[:200])
    with urllib.request.urlopen(audio_url, timeout=90) as r:
        raw = r.read()
    with open(out_path, "wb") as f:
        f.write(raw)
    return len(raw)


def main():
    args = sys.argv[1:]
    if args and args[0] == "--list":
        print("可用音色:")
        for v in VOICES:
            print("  -", v)
        return
    voice = args[0] if len(args) > 0 else "Cherry"
    text = args[1] if len(args) > 1 else "你好，这是盲盒故事配音测试。"
    if voice not in VOICES:
        print("警告: %s 不在常用音色列表 %s，尝试直接调用" % (voice, VOICES))
    out = "/tmp/tts_%s.wav" % voice
    n = synth(text, voice, out)
    print("OK %s -> %s (%d bytes)" % (voice, out, n))


if __name__ == "__main__":
    main()
