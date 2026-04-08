#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
优酷自动上传脚本（Playwright + 内置 Chromium）
✅ 使用 Playwright 内置 Chromium（无需系统 Chrome）
✅ 用户数据目录：~/.blindbox/youku
✅ 正确上传入口：https://mp.youku.com/new/upload_home
✅ 先勾选服务条款，再上传文件
✅ 监听上传进度，等 100% 后再点击发布
✅ 支持手动登录 + 自动上传发布
✅ 新增：精准识别 /new/video 页面并自动点击发布按钮
✅ 新增：日志带时间戳，便于追踪操作时间
✅ 新增：修复初次登录后页面跳转到 /new/video 未检测到的问题
"""

from playwright.sync_api import sync_playwright
import os
import argparse
import sys
import datetime

# ================== 配置 ==================
UPLOAD_URL = "https://mp.youku.com/new/upload_home"  # ✅ 正确上传起始页
AUTH_FILE = "youku_auth.json"

# ✅ 使用指定用户数据目录
USER_DATA_DIR = os.path.expanduser("~/.blindbox/youku")
PROFILE_DIR = "Default"  # Playwright 默认配置

# 确保目录存在
os.makedirs(USER_DATA_DIR, exist_ok=True)

# ================== 日志函数 ==================
def log_with_time(message):
    """带时间戳的日志输出"""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")

def ensure_logged_in(context):
    """确保已登录并进入上传页面"""
    page = context.pages[0]
    log_with_time("正在打开优酷上传页面...")
    page.goto(UPLOAD_URL, wait_until="networkidle")
    log_with_time(f"初始页面: {page.url}")

    # 情况1：已经进入上传页
    if "upload_home" in page.url and "login" not in page.url:
        log_with_time("✅ 已进入上传页")
        return page

    # 情况2：被重定向到登录页
    if "account.youku.com" in page.url:
        log_with_time("检测到需要登录，正在监控跳转...")
        log_with_time("请扫码登录")
        log_with_time("登录成功后，页面将自动跳转")

        for i in range(300):
            current_url = page.url
            # ✅ 修复：原代码中 log_with_time 不支持 end 参数，改为直接用 print 控制输出
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\r[{timestamp}] 等待登录成功... ({i+1}/300)", end="", flush=True)

            # ✅ 新增：检查是否跳转到 /new/video 页面
            if "new/video" in current_url and "login" not in current_url:
                print()  # 换行，结束 \r 覆盖
                log_with_time(f"\n🚨 检测到跳转到 /new/video 页面: {current_url}")
                log_with_time("正在尝试点击【发布视频】按钮...")

                try:
                    # 尝试通过链接定位
                    publish_link = page.locator('a[href="/new/upload_home"]')
                    if publish_link.is_visible():
                        log_with_time("✅ 通过 <a> 标签精准定位到【发布视频】按钮")
                        publish_link.click()
                        log_with_time("已点击【发布视频】按钮，正在跳转...")
                        # 等待跳转到 upload_home
                        page.wait_for_url("**/new/upload_home**", timeout=30000)
                        log_with_time(f"成功跳转到上传页: {page.url}")
                        context.storage_state(path=AUTH_FILE)
                        return page
                    else:
                        log_with_time("⚠️ <a> 标签定位失败，尝试通过文本定位...")
                        publish_button = page.locator('text=发布视频').first
                        if publish_button.is_visible():
                            log_with_time("✅ 通过文本定位到【发布视频】按钮")
                            publish_button.click()
                            log_with_time("已点击【发布视频】按钮，正在跳转...")
                            page.wait_for_url("**/new/upload_home**", timeout=30000)
                            log_with_time(f"成功跳转到上传页: {page.url}")
                            context.storage_state(path=AUTH_FILE)
                            return page
                        else:
                            log_with_time("❌ 两种方式均未找到【发布视频】按钮")
                            raise Exception("无法找到发布按钮")
                except Exception as e:
                    log_with_time(f"❌ 点击【发布视频】失败: {e}")
                    raise

            # ✅ 原来的逻辑：检查是否跳转到 upload_home
            if "upload_home" in current_url and "login" not in current_url:
                print()  # 换行，结束 \r 覆盖
                log_with_time(f"\n登录成功！已进入上传页: {current_url}")
                context.storage_state(path=AUTH_FILE)
                return page

            page.wait_for_timeout(1000)
        print()  # 最终换行
        raise Exception("❌ 登录超时：未在5分钟内进入上传页")

    # 情况3：在创作者中心（如 /new/upload_home 以外的 mp.youku.com 页面），点击【发布视频】
    if "mp.youku.com" in page.url and "upload_home" not in page.url:
        log_with_time(f"当前在创作者中心，URL: {page.url}，正在点击【发布视频】按钮...")
        try:
            # 尝试通过链接定位
            publish_link = page.locator('a[href="/new/upload_home"]')
            if publish_link.is_visible():
                log_with_time("✅ 通过链接定位到【发布视频】按钮")
                publish_link.click()
                log_with_time("已点击【发布视频】按钮，正在跳转...")
                # 等待跳转到 upload_home
                page.wait_for_url("**/new/upload_home**", timeout=30000)
                log_with_time(f"成功跳转到上传页: {page.url}")
                context.storage_state(path=AUTH_FILE)
                return page
            else:
                log_with_time("⚠️ 通过链接定位失败，尝试通过文本定位...")
                # 尝试通过文本定位
                publish_button = page.locator('text=发布视频').first
                if publish_button.is_visible():
                    log_with_time("✅ 通过文本定位到【发布视频】按钮")
                    publish_button.click()
                    log_with_time("已点击【发布视频】按钮，正在跳转...")
                    page.wait_for_url("**/new/upload_home**", timeout=30000)
                    log_with_time(f"成功跳转到上传页: {page.url}")
                    context.storage_state(path=AUTH_FILE)
                    return page
                else:
                    log_with_time("❌ 两种方式均未找到【发布视频】按钮")
                    raise Exception("无法找到发布按钮")
        except Exception as e:
            log_with_time(f"❌ 点击【发布视频】失败: {e}")
            raise

    # 情况4：在 /new/video 页面，需要点击【发布视频】按钮
    if "new/video" in page.url and "upload_home" not in page.url:
        log_with_time(f"🚨 重要：检测到页面为 /new/video，URL: {page.url}")
        log_with_time("正在尝试点击【发布视频】按钮...")

        # ✅ 优先使用精准的 <a> 标签定位
        try:
            publish_link = page.locator('a[href="/new/upload_home"]')
            if publish_link.is_visible():
                log_with_time("✅ 通过 <a> 标签精准定位到【发布视频】按钮")
                publish_link.click()
                log_with_time("已点击【发布视频】按钮，正在跳转...")
                # 等待跳转到 upload_home
                page.wait_for_url("**/new/upload_home**", timeout=30000)
                log_with_time(f"成功跳转到上传页: {page.url}")
                context.storage_state(path=AUTH_FILE)
                return page
            else:
                log_with_time("⚠️ <a> 标签定位失败，尝试通过文本定位...")
                publish_button = page.locator('text=发布视频').first
                if publish_button.is_visible():
                    log_with_time("✅ 通过文本定位到【发布视频】按钮")
                    publish_button.click()
                    log_with_time("已点击【发布视频】按钮，正在跳转...")
                    page.wait_for_url("**/new/upload_home**", timeout=30000)
                    log_with_time(f"成功跳转到上传页: {page.url}")
                    context.storage_state(path=AUTH_FILE)
                    return page
                else:
                    log_with_time("❌ 两种方式均未找到【发布视频】按钮")
                    raise Exception("无法找到发布按钮")
        except Exception as e:
            log_with_time(f"❌ 点击【发布视频】失败: {e}")
            raise

    # 情况5：在其他未知页面
    log_with_time(f"❌ 未知页面状态: {page.url}")
    raise Exception("无法进入上传页")


def upload_video(video_path, title="", description="", tags=[]):
    """上传视频到优酷"""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    with sync_playwright() as p:
        log_with_time("启动浏览器（使用 Playwright 内置 Chromium）...")

        try:
            context = p.chromium.launch_persistent_context(
                user_data_dir=USER_DATA_DIR,
                headless=False,
                args=[
                    f"--profile-directory={PROFILE_DIR}",
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-extensions",
                    "--disable-plugins-discovery",
                    "--disable-popup-blocking",
                    "--disable-translate",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--disable-ipc-flooding-protection",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-breakpad",
                    "--disable-component-update",
                    "--disable-domain-reliability",
                    "--disable-sync",
                    "--metrics-recording-only",
                    "--disable-default-apps",
                    "--mute-audio",
                    "--remote-debugging-port=9222",
                    "--disable-features=ImprovedCookieControls",
                    "--disable-features=TranslateUI",
                ],
                viewport={"width": 1280, "height": 800},
                ignore_https_errors=True,
            )
        except Exception as e:
            log_with_time(f"启动浏览器失败: {e}")
            log_with_time("请先运行: playwright install chromium")
            sys.exit(1)

        page = context.pages[0]

        # 隐藏 Playwright 自动化指纹
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false,
            });
            window.chrome = {
                runtime: {},
                loadTimes: () => {},
                csi: () => {}
            };
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5, 6],
            });
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en'],
            });
            window.navigator.permissions.query = (parameters) =>
                parameters.name === 'notifications'
                    ? Promise.resolve({ state: Notification.permission })
                    : originalQuery(parameters);
            const originalQuery = window.navigator.permissions.query;
        """)

        try:
            page = ensure_logged_in(context)

            # ================== 上传视频 ==================
            log_with_time("开始上传视频...")

            # --- 第一步：先勾选服务条款 ---
            log_with_time("正在勾选【同意优酷服务条款】...")
            try:
                agree_checkbox = page.locator('input.ant-checkbox-input[type="checkbox"]')
                page.wait_for_selector('input.ant-checkbox-input[type="checkbox"]', timeout=10000)

                # ✅ 使用 is_checked() 安全判断状态
                if not agree_checkbox.is_checked():
                    try:
                        agree_checkbox.click(force=True)
                        log_with_time("✅ 已点击服务条款复选框")
                    except Exception:
                        # ✅ 先获取元素句柄，再操作 DOM
                        element_handle = agree_checkbox.element_handle(timeout=5000)
                        if element_handle:
                            page.evaluate("el => el.checked = true", element_handle)
                            # 触发 change 事件，通知页面状态变更
                            page.evaluate("el => el.dispatchEvent(new Event('change'))", element_handle)
                            log_with_time("✅ 已强制勾选服务条款")
                        else:
                            raise Exception("无法获取复选框元素句柄")

                    # ✅ 修复：使用 is_checked() 而不是 page.evaluate 传 Locator
                    if agree_checkbox.is_checked():
                        log_with_time("服务条款已成功勾选")
                    else:
                        raise Exception("无法设置 checked 状态")
                else:
                    log_with_time("服务条款已勾选，跳过")
            except Exception as e:
                log_with_time(f"勾选服务条款失败: {e}")
                page.screenshot(path="failed_agree_terms.png")
                raise

            # --- 第二步：等待并上传文件 ---
            try:
                page.wait_for_selector('input#file[type="file"]', state="attached", timeout=30000)
                log_with_time("✅ 找到上传控件 <input id='file' type='file'>")
            except Exception:
                page.screenshot(path="missing_file_input.png")
                raise Exception("❌ 未找到上传控件")

            file_input = page.locator('input#file[type="file"]')
            file_input.set_input_files(video_path)
            log_with_time(f"已选择文件: {video_path}")
            log_with_time("⏳ 正在等待上传进度...")

            # --- 第三步：监听上传进度，等待 100% ---
            log_with_time("正在监控上传进度...")
            try:
                # 等待进度元素出现
                page.wait_for_selector('span.percent___2Stb0', timeout=60000)  # 10分钟

                # 轮询检查是否达到 100%
                for _ in range(600):  # 最多等待 10 分钟（600秒）
                    progress_text = page.eval_on_selector('span.percent___2Stb0', 'el => el.innerText').strip()
                    if progress_text == "100%":
                        log_with_time("✅ 上传进度: 100% - 上传完成！")
                        break
                    else:
                        log_with_time(f"上传进度: {progress_text}")
                    page.wait_for_timeout(1000)
                else:
                    raise Exception("❌ 上传超时：10分钟内未完成上传")
            except Exception as e:
                page.screenshot(path="upload_progress_timeout.png")
                raise Exception(f"❌ 上传进度监控失败: {e}")

            # ================== 发布 ==================
            log_with_time("正在等待【发布】按钮出现...")
            try:
                # 精准定位“发 布”按钮（中间有空格）
                publish_button = page.locator('button.ant-btn-primary:has(span:has-text("发 布"))').first

                # 等待按钮可见
                publish_button.wait_for(timeout=30000)
                log_with_time("✅ 【发布】按钮已出现")

                # 滚动到按钮位置
                publish_button.scroll_into_view_if_needed()
                page.wait_for_timeout(1000)

                # 点击发布
                publish_button.click(force=True)
                log_with_time("已点击【发布】按钮，正在提交...")

                # 等待“发布成功”提示
                page.wait_for_selector('text=发布成功', timeout=30000)
                log_with_time("视频发布成功！")

            except Exception as e:
                log_with_time(f"发布失败: {e}")
                page.screenshot(path="publish_failed.png")
                raise

            # 保存登录状态
            context.storage_state(path=AUTH_FILE)
            log_with_time("登录状态已保存")

        except Exception as e:
            log_with_time(f"操作失败: {e}")
            page.screenshot(path="final_error.png")
            raise

        finally:
            log_with_time("发布完成，2秒后自动退出...")
            page.wait_for_timeout(2000)  # 延迟2秒后自动关闭

        context.close()


# =============== 主程序入口 ===============
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自动上传视频到优酷创作者平台")
    parser.add_argument("video_path", help="视频文件的本地路径")
    parser.add_argument("--title", default="", help="视频标题（可选）")
    parser.add_argument("--description", default="", help="视频简介（可选）")
    parser.add_argument("--tags", nargs="*", default=[], help="标签列表（可选）")

    args = parser.parse_args()

    try:
        upload_video(
            video_path=args.video_path,
            title=args.title,
            description=args.description,
            tags=args.tags
        )
    except KeyboardInterrupt:
        log_with_time("\n用户中断")
        sys.exit(1)
    except Exception as e:
        log_with_time(f"脚本终止: {e}")
        sys.exit(1)
