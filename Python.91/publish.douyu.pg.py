#!/usr/bin/env python
# -*- coding: utf-8 -*-

from playwright.sync_api import sync_playwright, TimeoutError
import os
import sys
import time  # ✅ 新增：用于延时

def publish_douyu_video(video_path, title="分享此刻的精彩"):
    STATE_FILE = "douyu_login_state.json"
    browser = None
    context = None
    page = None

    try:
        with sync_playwright() as p:
            print("🚀 启动浏览器...")

            browser = p.chromium.launch(
                headless=False,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-extensions",
                    "--disable-plugins-discovery",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--disable-notifications",
                    "--start-maximized",
                ],
                ignore_default_args=["--enable-automation"]
            )

            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
                java_script_enabled=True,
                ignore_https_errors=True,
            )

            # 绕过自动化检测
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => false });
                Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
                Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
                Object.defineProperty(navigator, 'mimeTypes', { get: () => [1, 2, 3, 4] });
                window.chrome = { runtime: {}, loadTimes: () => {}, csi: () => {} };
            """)

            page = context.new_page()
            page.set_default_timeout(30000)

            # ==================== 登录流程：自动检测登录状态 ====================
            if os.path.exists(STATE_FILE):
                try:
                    context.storage_state(path=STATE_FILE)
                    page.goto("https://www.douyu.com/creator/upload/videos")
                    if "login" not in page.url and page.locator("text=上传视频").is_visible(timeout=5000):
                        print("📁 已自动登录，使用缓存状态")
                    else:
                        print("🔒 登录态失效，需重新扫码")
                        os.remove(STATE_FILE)
                except:
                    print("🔒 登录态加载失败，需重新扫码")
                    if os.path.exists(STATE_FILE):
                        os.remove(STATE_FILE)

            # ==================== 扫码登录 ====================
            if not os.path.exists(STATE_FILE):
                print("🔒 未登录，开始扫码...")
                page.goto("https://passport.douyu.com/member/login?lang=cn&verify=1&client_id=1&ru=https%3A%2F%2Fwww.douyu.com%2F")
                print("⏳ 请扫码登录斗鱼...")

                # ✅ 等待登录成功：通过 DOM 变化判断
                print("⏳ 正在等待扫码登录成功...")

                # 等待 UnLogin 元素从 DOM 中移除
                try:
                    page.wait_for_function("() => !document.querySelector('div.UnLogin')")
                    print("✅ 未登录区域已消失")
                except TimeoutError:
                    print("⚠️ 未登录区域未消失，继续检测...")

                # 等待 UserInfo 容器出现（关键判断）
                try:
                    page.wait_for_selector("div.UserInfo.public-DropMenu", timeout=120000)
                    print("✅ 检测到用户登录状态（UserInfo 出现）")
                except TimeoutError:
                    raise TimeoutError("❌ 超时：未检测到登录状态，请确认是否扫码成功")

                # ✅ 登录成功，跳转上传页
                page.goto("https://www.douyu.com/creator/upload/videos")
                page.wait_for_timeout(3000)

                # ✅ 保存登录状态
                context.storage_state(path=STATE_FILE)
                print("💾 登录状态已保存（扫码后）")

            # ==================== 确保进入上传页 ====================
            page.goto("https://www.douyu.com/creator/upload/videos")
            page.wait_for_timeout(3000)

            # ✅ 上传文件
            print("📁 正在上传视频文件...")
            try:
                file_input = page.locator("input[type='file'][accept*='mp4']").first
                file_input.set_input_files(video_path)
                print(f"✅ 文件已设置: {os.path.basename(video_path)}")
            except Exception as e:
                print(f"❌ 文件上传失败: {e}")
                raise

            # ✅ 等待上传完成
            print("⏳ 等待视频上传进度...")
            try:
                page.wait_for_selector("span.precent-num:text('100%')", timeout=300000)
                print("✅ 上传进度已达到100%")
            except TimeoutError:
                print("⚠️ 进度条未显示100%，尝试通过样式判断...")
                page.wait_for_function("""
                    () => {
                        const el = document.querySelector('.shark-Progress-line-bg');
                        return el && window.getComputedStyle(el).width === '100%';
                    }
                """, timeout=300000)
                print("✅ 进度条样式已达到100%")

            # ✅ 等待进入详情页
            print("⏳ 等待进入视频详情页...")
            page.wait_for_selector("input[placeholder='请输入标题']", timeout=10000)
            print("✅ 已进入视频详情页")

            # ✅ 填写标题
            title_input = page.locator("input[placeholder='请输入标题']")
            title_input.fill(title)
            print(f"✍️ 标题已填写：{title}")

            # ✅ 填写标签
            print("🏷️ 正在填写标签...")
            try:
                tag_input = page.locator("input[placeholder='按回车键Enter创建标签']")
                tag_input.wait_for(timeout=5000)
                tag_input.click()
                tag_input.fill("日常")
                page.keyboard.press("Enter")
                print("✅ 标签已添加：日常")
            except Exception as e:
                print(f"⚠️ 标签添加失败（可忽略）: {e}")

            # ✅ 选择分类
            print("📂 正在选择分类...")
            try:
                category_trigger = page.locator("div.cate-info--1dwd72_:has-text('点击选择')")
                category_trigger.click()
                page.wait_for_timeout(1000)

                page.locator("div.cate-item-content--2OUsdRN:has-text('生活')").click()
                page.wait_for_timeout(500)

                page.locator("p:has(span.hl--1JxHNDv) >> text=生活综合").click()
                page.wait_for_timeout(500)

                page.mouse.click(0, 0)  # 关闭下拉
                print("✅ 分类已选择：生活 → 生活综合")
            except Exception as e:
                print(f"❌ 分类选择失败: {e}")
                raise

            # ✅ 发布：点击“立即投稿”
            print("📌 正在点击【立即投稿】按钮...")
            try:
                # 先定位元素
                submit_button = page.locator("div.videoSubmit-btn--2Y4qii8:has-text('立即投稿')")
                # 等待可见
                submit_button.wait_for(timeout=10000)
                # 点击
                submit_button.click()
                print("📤 视频已提交发布！")
            except Exception as e:
                print(f"❌ 发布按钮点击失败: {e}")
                raise

            # ✅ 保存状态
            context.storage_state(path=STATE_FILE)
            print("💾 登录状态已保存")

            print("🎉 视频已成功发布到斗鱼！")

            # 保持浏览器打开，便于确认结果
            print("\n📌 浏览器保持打开，请确认发布结果...")
            # ✅ 删除 input()，改为延时
            time.sleep(5)  # ✅ 延时 5 秒后自动退出

    except Exception as e:
        print(f"\n❌ 脚本执行出错: {e}")
        print("\n🛑 脚本暂停，浏览器保持打开，请检查页面状态！")
        print("   - 是否卡在某个步骤？")
        print("   - 元素是否可见？")
        print("   - 有无弹窗或验证码？")
        # ✅ 删除 input()，改为延时
        time.sleep(5)  # ✅ 延时 5 秒后自动退出

    finally:
        if browser:
            try:
                browser.close()
            except:
                pass
        print("👋 脚本结束")

# ========== 主程序入口 ==========
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("💡 用法: python publish.douyu.pg.py <视频文件路径> [标题]")
        print("   示例: python publish.douyu.pg.py \"/Ibotex/Videos/test.mp4\" \"我的精彩瞬间\"")
        sys.exit(1)

    video_path = sys.argv[1]
    title = sys.argv[2] if len(sys.argv) > 2 else "分享此刻的精彩"

    if not os.path.exists(video_path):
        print(f"❌ 错误：视频文件不存在: {video_path}")
        sys.exit(1)

    publish_douyu_video(video_path, title)
