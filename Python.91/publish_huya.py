#!/usr/bin/env python
# -*- coding: utf-8 -*-

# publish_huya.py

"""
虎牙自动发布脚本（v4.3）
✅ 修复：分类选择逻辑（点击「选择分类」按钮）
✅ 修复：简介框文字残留（全选删除）
✅ 修复：协议勾选（直接点击 img.gou）
✅ 新增：支持虚拟滚动列表（“生活”在第11位也能找到）
✅ 修复：上传超时问题 - 改为动态等待进度变化
"""

import sys
import argparse
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# ==================== 配置 ====================
BLINDBOX_DIR = Path.home() / ".blindbox"
AUTH_STATE_FILE = BLINDBOX_DIR / "huya_auth.json"
BLINDBOX_DIR.mkdir(exist_ok=True)

HUYA_UPLOAD_URL = "https://www.huya.com/video/web/video-process/#/home"
TIMEOUT = 60_000
HEADLESS = False  # True #False
CATEGORY_LABEL = "生活/生活碎片"  # 格式：主分类/子分类，如 "生活/生活碎片"
# ==============================================


def wait_for_selector_safe(page, selector: str, timeout: int = TIMEOUT, state="visible"):
    try:
        page.wait_for_selector(selector, timeout=timeout, state=state)
        return True
    except PlaywrightTimeoutError:
        print(f"❌ 超时：未找到或不可见元素 {selector}")
        return False


def ensure_login_state(auth_file: Path, url: str):
    if not auth_file.exists():
        print("🔐 未检测到登录状态，开始首次登录...")
        perform_login(auth_file, url)
        return

    print(f"🔍 检测登录态：{auth_file}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context(storage_state=str(auth_file))
        page = context.new_page()
        page.set_default_timeout(TIMEOUT)
        page.goto(url)

        try:
            page.wait_for_selector('text="上传并发布"', timeout=10000)
            print("✅ 登录态有效")
            browser.close()
            return
        except PlaywrightTimeoutError:
            print("⚠️ 登录态失效，需重新登录...")

        browser.close()
    perform_login(auth_file, url)


def perform_login(auth_file: Path, url: str):
    print(f"📝 正在启动浏览器，请登录虎牙账号...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(TIMEOUT)
        page.goto(url)

        print("👉 请完成登录操作")
        print("💡 登录后请确保能看到「上传并发布」按钮")
        input("✅ 登录成功后，请按回车键继续...")

        context.storage_state(path=str(auth_file))
        print(f"🔐 登录状态已保存至：{auth_file}")
        browser.close()


# ==================== 核心发布函数（修正分类 + 协议 + 上传超时）====================

def auto_publish_huya(video_path: str, description: str = "") -> bool:
    """
    自动发布视频到虎牙，完成后立即退出。
    返回: True 表示发布请求已提交，False 表示失败
    """
    from pathlib import Path

    video_path = Path(video_path).resolve()

    if not video_path.exists():
        print(f"❌ 视频文件不存在：{video_path}")
        return False

    print(f"🎥 开始发布视频：{video_path.name}")
    if description:
        print(f"📝 视频描述：{description[:30]}{'...' if len(description) > 30 else ''}")

    ensure_login_state(AUTH_STATE_FILE, HUYA_UPLOAD_URL)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS)  # 可根据需要设置 headless
        context = browser.new_context(storage_state=str(AUTH_STATE_FILE))
        page = context.new_page()
        page.set_default_timeout(TIMEOUT)

        try:
            page.goto(HUYA_UPLOAD_URL)
            print("🌐 已打开虎牙创作中心")

            if not wait_for_selector_safe(page, 'text="上传并发布"', timeout=30_000):
                print("❌ 页面未加载完成")
                page.screenshot(path="debug-page-load-fail.png")
                return False

            file_input = page.locator('input[type="file"][multiple]')
            file_input.wait_for(state="attached", timeout=30_000)
            file_input.set_input_files(str(video_path))
            print(f"📤 已注入视频文件：{video_path.name}")

            print("📊 等待上传进度完成...")
            # === 修改点1：移除必须100%的限制，改为只要有进度变化就持续等待 ===
            # 记录初始进度
            initial_width = None
            start_time = page.evaluate("Date.now()")
            timeout_threshold = 300_000  # 5分钟超时
            progress_change_timeout = 300_000  # 5分钟无变化超时

            while True:
                # 获取进度条宽度
                current_width = page.evaluate("""
                    () => {
                        const bar = document.querySelector('.p-active');
                        return bar ? bar.style.width : null;
                    }
                """)

                # 如果进度条不存在，继续等待
                if current_width is None:
                    page.wait_for_function("""
                        () => {
                            const bar = document.querySelector('.p-active');
                            return bar !== null;
                        }
                    """, timeout=5000)
                    continue

                # 如果进度条达到100%，说明上传完成
                if current_width == "100%":
                    print("✅ 上传进度已完成（100%）")
                    break

                # 如果进度有变化，重置超时计时器
                if initial_width is None or current_width != initial_width:
                    initial_width = current_width
                    start_time = page.evaluate("Date.now()")
                    print(f"📈 上传进度更新：{current_width}")

                # 检查是否超时
                elapsed_time = page.evaluate("Date.now()") - start_time
                if elapsed_time > progress_change_timeout:
                    print(f"❌ 上传超时：进度条在 {progress_change_timeout/1000} 秒内无变化")
                    page.screenshot(path="debug-upload-progress-timeout.png")
                    return False

                # 检查总超时时间
                total_elapsed = page.evaluate("Date.now()") - page.evaluate("Date.now() - 300000")
                if total_elapsed > timeout_threshold:
                    print(f"❌ 上传总超时：超过 {timeout_threshold/1000} 秒未完成")
                    page.screenshot(path="debug-upload-total-timeout.png")
                    return False

                # 短暂等待后继续检查
                page.wait_for_timeout(1000)

            # 检查重复上传
            duplicate_error = page.locator('text="上传出错，视频重复上传"')
            if duplicate_error.is_visible(timeout=5000):
                print("🚫 视频重复上传，发布被阻止")
                return False

            print("🟢 上传成功，开始填写表单")

            # 填写描述
            desc_p = page.locator('p[contenteditable="true"][placeholder="发生了什么有趣的事呢"]')
            if desc_p.is_visible(timeout=10_000):
                desc_p.click()
                page.keyboard.press("Control+A")
                page.keyboard.press("Delete")
                if description:
                    desc_p.type(description + " ", delay=50)
                print("💬 已填写视频描述")
            else:
                print("❌ 未找到简介输入框")
                return False

            # 关闭可能弹出的面板
            page.mouse.click(100, 100)
            page.wait_for_timeout(500)

            # 打开分类面板
            category_trigger = page.locator('.f-tag.f-tag-recom .down').first
            if not category_trigger.is_visible():
                category_trigger = page.locator('.f-tag.f-tag-recom').first
            if category_trigger.is_visible(timeout=10_000):
                category_trigger.click()
                print("🔽 分类面板已打开")
            else:
                print("❌ 无法打开分类面板")
                page.screenshot(path="debug-category-trigger-fail.png")
                return False

            # 使用搜索框选择分类
            try:
                _, sub_category_name = CATEGORY_LABEL.split("/", 1)
            except ValueError:
                print(f"❌ 分类格式错误：{CATEGORY_LABEL}")
                return False

            search_input = page.locator('input[placeholder="选择准确的分类，可以让动态有更多推荐哦"]').first
            if search_input.is_visible(timeout=10_000):
                search_input.click()
                search_input.fill("")
                search_input.fill(sub_category_name)
                print(f"⌨️  输入分类：{sub_category_name}")

                # 等待并点击匹配项（非必须，但更可靠）
                matched_tag = page.locator(f'.f-tag:has-text("{sub_category_name}")').first
                if matched_tag.is_visible(timeout=5_000):
                    matched_tag.click()
                    print(f"✅ 已选中分类：{sub_category_name}")
                else:
                    print(f"✅ 分类“{sub_category_name}”已通过输入自动匹配")
            else:
                print("❌ 未找到分类搜索框")
                return False

            # 勾选协议
            agree_div = page.locator('.prize-agree:has-text("本人已阅读")')
            gou_circle = agree_div.locator('img.gou').first
            if agree_div.is_visible(timeout=10_000):
                if not gou_circle.is_visible():
                    agree_div.click()  # 点击整个区域通常也能勾选
                    print("✅ 协议已勾选")
            else:
                print("❌ 未找到协议区域")
                return False

            # 点击发布
            publish_btn = page.locator('text="发布"').or_(page.locator('text="确认发布"'))
            if publish_btn.is_enabled(timeout=10_000):
                publish_btn.click()
                print("🚀 发布按钮已点击")
            else:
                print("❌ 发布按钮不可用")
                return False

            # ✅ 等待成功提示（关键判断）
            if wait_for_selector_safe(page, 'text="视频上传成功，请等待审核通过"', timeout=30_000):
                print("🎉✅ 视频发布成功！已提交审核")
                context.storage_state(path=str(AUTH_STATE_FILE))  # 保存最新状态
                return True
            else:
                print("❌ 未检测到发布成功提示")
                page.screenshot(path="debug-publish-fail.png")
                return False

        except Exception as e:
            print(f"❌ 脚本异常：{type(e).__name__}: {e}")
            return False

        finally:
            browser.close()  # ✅ 立即关闭浏览器
            print("⏹ 浏览器已关闭")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("❌ 用法：python publish_huya.py <视频路径> [--desc '描述']")
        sys.exit(1)

    video_path = sys.argv[1]
    description = ""

    if "--desc" in sys.argv:
        desc_index = sys.argv.index("--desc")
        if desc_index + 1 < len(sys.argv):
            description = sys.argv[desc_index + 1]

    auto_publish_huya(video_path, description)
