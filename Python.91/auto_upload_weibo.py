#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
微博视频自动化发布脚本（防崩智能版）
- 防 context destroyed
- 页面稳定后再操作
- 智能上传监控 + 失败重试
"""

import argparse
import os
import json
import time
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


def log(msg, level="INFO"):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] [{level}] {msg}")


def is_valid_cover(src):
    return 'wx' in src and '/large/' in src and '.sinaimg.cn' in src


def main():
    parser = argparse.ArgumentParser(description="自动化发布视频到微博")
    parser.add_argument("video_path", type=str, help="本地视频文件路径")
    parser.add_argument("--title", type=str, default="", help="微博标题（可选）")
    parser.add_argument("--description", type=str, required=True, help="微博正文内容")
    parser.add_argument("--delay", type=float, default=3.0, help="操作间隔（秒）")
    parser.add_argument("--headless", type=str, default="false", help="是否无头模式 (true/false)")
    parser.add_argument("--proxy", type=str, default=None, help="代理地址，如 http://127.0.0.1:7890")

    args = parser.parse_args()

    video_path = Path(args.video_path)
    if not video_path.exists():
        log(f"❌ 视频文件不存在: {video_path}", "ERROR")
        exit(1)

    current_dir = Path.cwd()
    screenshot_path = current_dir / "weibo_screenshot.png"
    auth_file = Path.home() / ".blindbox" / "weibo.auth.v.json"

    headless = args.headless.lower() == "true"
    proxy_config = {"server": args.proxy} if args.proxy else None

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
            proxy=proxy_config,
            slow_mo=50,
        )
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        # 加载 Cookie
        if auth_file.exists():
            try:
                cookies = json.loads(auth_file.read_text(encoding="utf-8"))
                context.add_cookies(cookies)
                log(f"✅ 已加载登录态: {auth_file}")
            except Exception as e:
                log(f"⚠️ 加载 Cookie 失败（跳过）: {e}", "WARNING")

        page = context.new_page()
        page.set_default_timeout(60000)

        try:
            log("🚀 正在打开微博首页...")
            page.goto("https://weibo.com", wait_until="domcontentloaded")
            log("✅ 页面 DOM 加载完成")

            # === 等待页面真正稳定 ===
            log("⏳ 等待页面加载完成且 URL 稳定...")
            try:
                page.wait_for_load_state("load", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=30000)  # 关键：等网络空闲
            except:
                pass  # 即使超时也继续

            # === 登录检测：等待头像真实出现 ===
            log("🔍 正在检测登录状态（通过头像）...")
            avatar_selector = 'img[alt="profile"][class*="_avatar"]'
            for _ in range(60):
                try:
                    img = page.eval_on_selector(
                        avatar_selector,
                        "el => ({ src: el.src || '', visible: !!(el.offsetWidth || el.offsetHeight) })"
                    ) if page.query_selector(avatar_selector) else None
                    if img and img['src'] and 'http' in img['src']:
                        log("✅ 检测到有效头像，登录成功！")
                        break
                except:
                    pass  # 上下文可能重建
                time.sleep(1)
            else:
                log("❌ 登录超时，请检查网络", "ERROR")
                page.screenshot(path=screenshot_path, full_page=True)
                log(f"📸 截图已保存: {screenshot_path}")
                while True:
                    time.sleep(1)

            time.sleep(2)

            # === 填写内容 ===
            log("📝 正在查找输入框并填写...")
            text_area = None
            for _ in range(10):
                try:
                    text_area = page.wait_for_selector('textarea[placeholder="有什么新鲜事想分享给大家？"]', timeout=5000)
                    break
                except:
                    time.sleep(1)
            if not text_area:
                raise Exception("未找到输入框")

            content = (args.title.strip() + " " + args.description.strip()).strip()
            text_area.fill(content)
            log("✅ 内容已填写")

            # === 上传视频 ===
            log("📤 正在定位上传控件并上传视频...")
            upload_input = page.wait_for_selector('input[type="file"]._file_hqmwy_20', state="attached", timeout=15000)
            upload_input.set_input_files(str(video_path))
            log("✅ 文件已选择，开始监控上传...")

            # === 智能等待真实封面图 ===
            log("⏳ 正在等待真实封面图加载...")
            valid_cover_found = False
            last_progress = ""
            for i in range(120):
                try:
                    # 获取封面图
                    img = page.eval_on_selector(
                        "img.woo-picture-img",
                        "el => ({ src: el.src || '', classList: Array.from(el.classList).join(' ') })"
                    ) if page.query_selector("img.woo-picture-img") else None

                    # 获取进度条
                    loading_bar = page.query_selector("div._loading_1syq3_25 span")
                    progress_text = loading_bar.text_content() if loading_bar else None

                    log(f"🖼️ 第 {i+1}s | 图片 src: {img['src'] if img else 'null'} | 进度: {progress_text}")

                    if progress_text and progress_text != last_progress:
                        log(f"🔄 进度更新: {last_progress} → {progress_text}")
                        last_progress = progress_text

                    if img and is_valid_cover(img['src']):
                        log("✅ 检测到真实封面图，上传完成！")
                        valid_cover_found = True
                        break

                except Exception as e:
                    log(f"⚠️ 轮询中发生异常（可能是页面跳转）: {str(e)}")
                    time.sleep(1)
                    continue
                time.sleep(1)
            else:
                log("❌ 超时未完成上传")

            # === 等待发送按钮可用 ===
            log("⏳ 正在等待【发送】按钮变为可点击...")
            send_button = page.wait_for_selector("button:has-text('发送'):not([disabled])", timeout=10000)
            log("✅ 【发送】按钮已可点击")

            # === 发布（支持重试）===
            for attempt in range(2):
                try:
                    log(f"📨 第 {attempt+1} 次点击【发送】...")
                    send_button.click()
                    time.sleep(2)
                    if page.wait_for_selector("text=发布成功", timeout=10000):
                        log("🎉 发布成功！")
                        break
                except:
                    if attempt == 0:
                        log("🔁 准备重试")
                        time.sleep(3)
            else:
                log("❌ 两次尝试均失败")

            # === 保存状态 ===
            page.screenshot(path=screenshot_path, full_page=True)
            log(f"📸 截图已保存: {screenshot_path}")

            cookies = context.cookies()
            auth_file.parent.mkdir(parents=True, exist_ok=True)
            auth_file.write_text(json.dumps(cookies, indent=2, ensure_ascii=False), encoding="utf-8")
            log(f"💾 登录态已保存: {auth_file}")

            notify_path = current_dir / "weibo_notification.json"
            notify_data = {
                "platform": "weibo",
                "status": "success",
                "title": args.title or "未命名",
                "description": args.description[:50] + "...",
                "screenshot": str(screenshot_path),
                "timestamp": datetime.now().isoformat()
            }
            notify_path.write_text(json.dumps(notify_data, indent=2, ensure_ascii=False), encoding="utf-8")
            log(f"🔔 通知已生成: {notify_path}")

            browser.close()
            exit(0)

        except Exception as e:
            log(f"❌ 发布失败: {str(e)}", "ERROR")
            try:
                page.screenshot(path=screenshot_path, full_page=True)
                log(f"📸 错误截图已保存: {screenshot_path}")
            except:
                pass
            log("⏸️ 【等待中】请检查浏览器窗口。按 Ctrl+C 终止。")
            while True:
                time.sleep(1)


if __name__ == "__main__":
    main()
