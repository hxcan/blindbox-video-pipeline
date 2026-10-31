# migu_publisher.ebp.py
# 咪咕视频自动发布脚本 | 支持 WebP 封面 | 抗闪屏上传 | 精准跳转检测 | 自动登录检测
# 作者：未来姐姐（带点小骚）
# 依赖：playwright, Pillow
# 安装命令：
#   pip install playwright Pillow
#   playwright install chromium

from playwright.sync_api import sync_playwright
import os
import argparse
import sys
import signal
import atexit
from PIL import Image
import tempfile
import time


# ==================== 配置 ====================
STORAGE_STATE_PATH = os.path.expanduser("~/.blindbox/migu/login_state.json")
os.makedirs(os.path.dirname(STORAGE_STATE_PATH), exist_ok=True)


# ==================== 退出时保存登录态 ====================
def save_login_state_on_exit(browser=None, context=None):
    """退出时保存登录态（支持 Ctrl+C 和正常退出）"""
    try:
        print("\n💾 正在保存登录态...")
        # 如果有 browser 和 context，保存登录态
        if browser is not None and context is not None:
            context.storage_state(path=STORAGE_STATE_PATH)
            print(f"✅ 登录态已保存至: {STORAGE_STATE_PATH}")
        elif os.path.exists(STORAGE_STATE_PATH):
            # 文件已存在，说明之前已保存
            print(f"✅ 登录态已存在: {STORAGE_STATE_PATH}")
    except Exception as e:
        print(f"⚠️ 保存登录态失败: {e}")


# 信号处理：Ctrl+C 中断时保存登录态
def signal_handler(signum, frame):
    print("\n🛑 收到中断信号，正在保存...")
    save_login_state_on_exit()
    sys.exit(0)


# 注册退出钩子（支持正常退出和 sys.exit()）
def register_exit_handler():
    atexit.register(save_login_state_on_exit)


# 注册信号处理
signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # kill 命令


def wait_for_login_completion(page):
    """
    自动检测登录是否完成：
    - 登录弹窗（.login-wrapper）消失即视为登录成功
    """
    print("🔐 正在自动检测登录状态...")
    try:
        # 等待登录弹窗消失（即已登录）
        page.wait_for_selector("div.login-wrapper", state="hidden", timeout=30000)
        print("✅ 登录检测成功：登录弹窗已消失，已登录。")
        return True
    except:
        print("⚠️ 登录弹窗未消失，可能未登录或网络异常。")
        return False


def publish_to_migu(video_path: str, title: str, description: str = "", tags: list = None, cover_path: str = None, content_type: str = "original", source_url: str = "", content_declaration: str = "AI生成"):
    """
    自动发布视频到咪咕视频平台
    流程：
      1. 打开创作中心
      2. 自动检测登录状态（无需手动按回车）
      3. 点击发布视频
      4. 选择视频文件（不上传）
      5. 填写标题、分类、内容类型、内容声明
      6. 上传封面（支持 WebP → JPG 转换）
      7. 点击【发布】按钮
      8. 智能等待上传完成（抗闪屏！）
      9. 精准检测是否跳转到内容管理页
      10. 成功提示 + 延时自动退出
    """
    print("🚀 开始执行咪咕视频自动发布任务...")

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"视频文件未找到: {video_path}")

    if tags is None:
        tags = []

    # 注册退出处理（传入 browser 和 context）
    register_exit_handler()
    
    browser = None
    context = None
    
    with sync_playwright() as p:
        # 启动浏览器
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            storage_state=STORAGE_STATE_PATH if os.path.exists(STORAGE_STATE_PATH) else None,
        )
        page = context.new_page()

        try:
            # 1. 打开创作中心
            print("1️⃣ 正在打开创作中心...")
            page.goto("https://www.miguvideo.com/mgs/share/migucreator/prd/index.html#/upload/home", timeout=60000)
            page.wait_for_load_state("networkidle")

            # 2. 自动检测登录状态（关键修改点）
            if not wait_for_login_completion(page):
                # 如果未登录，尝试从本地状态恢复
                if os.path.exists(STORAGE_STATE_PATH):
                    print("🔄 正在尝试从本地存储恢复登录状态...")
                    context = browser.new_context(storage_state=STORAGE_STATE_PATH)
                    page = context.new_page()
                    page.goto("https://www.miguvideo.com/mgs/share/migucreator/prd/index.html#/upload/home", timeout=60000)
                    page.wait_for_load_state("networkidle")
                    if wait_for_login_completion(page):
                        print("✅ 登录状态恢复成功！")
                    else:
                        print("❌ 本地登录状态无效，需手动登录。")
                        input("👉 请手动登录后按回车键继续...")
                        context.storage_state(path=STORAGE_STATE_PATH)
                        print(f"✅ 登录状态已保存至: {STORAGE_STATE_PATH}")
                else:
                    print("❌ 未登录且无本地登录状态，需手动登录。")
                    input("👉 请手动登录后按回车键继续...")
                    context.storage_state(path=STORAGE_STATE_PATH)
                    print(f"✅ 登录状态已保存至: {STORAGE_STATE_PATH}")

            # 3. 点击发布视频
            print("2️⃣ 正在点击【发布视频】按钮...")
            publish_btn = page.locator("button.publish-video")
            publish_btn.wait_for(timeout=10000)
            publish_btn.click()
            page.wait_for_timeout(2000)

            # 4. 选择视频文件（不等待上传）
            print("3️⃣ 选择视频文件（仅选择，上传将在发布时进行）...")
            try:
                # 调试: 检查页面中的 input[type=file] 元素
                print("[DEBUG] 检查页面中的 input[type=file] 元素...")
                file_input_count = page.locator("input[type=file]").count()
                print(f"[DEBUG] 找到 {file_input_count} 个 input[type=file] 元素")
                
                # 修复: 先检查元素是否存在，避免 null.click() 报错
                if page.locator("input[type=file]").count() > 0:
                    page.locator("input[type=file]").first.set_input_files(video_path)
                    print(f"[DEBUG] 直接设置文件成功: {video_path}")
                else:
                    # 尝试 JS 点击方式
                    try:
                        page.evaluate("document.querySelector('input[type=file]')")
                        if page.evaluate("document.querySelector('input[type=file]') !== null"):
                            page.evaluate("document.querySelector('input[type=file]').click()")
                            print("[DEBUG] JS click 方式成功")
                        else:
                            print("[DEBUG] 页面上没有找到 input[type=file] 元素")
                    except Exception as e:
                        print(f"[DEBUG] 选择视频失败: {e}")
                with page.expect_file_chooser() as fc_info:
                    # 选择视频文件
                    if page.locator("text=选择视频").is_visible():
                        page.click("text=选择视频")
                    else:
                        page.evaluate("document.querySelector('input[type=file]').click()")
                file_chooser = fc_info.value
                file_chooser.set_files(video_path)
                print("📁 视频文件已选择，上传将在点击【发布】后开始")
            except Exception as e:
                print(f"⚠️ 选择视频文件时出错: {e}")
                page.screenshot(path="error_select_video.png")

            # --- 填写信息阶段 ---
            print("4️⃣ 开始填写视频信息...")

            # ======== 标题 ========
            print("📝 填写标题...")
            try:
                title_locator = page.locator("input.title[placeholder='清晰明了的标题会更受欢迎']")
                title_locator.wait_for(timeout=10000)
                page.wait_for_function("""
                    () => {
                        const el = document.querySelector('input.title[placeholder="清晰明了的标题会更受欢迎"]');
                        return el && !el.disabled && el.offsetParent !== null;
                    }
                """, timeout=15000)
                title_locator.fill(title)
                print(f"✅ 标题已填写: {title}")
                if title_locator.input_value() == title:
                    print("✅✅ 标题验证通过！")
                else:
                    print("❌❌ 标题未填入！")
                    page.screenshot(path="failed_to_fill_title.png")
            except Exception as e:
                print(f"❌ 标题填写失败: {e}")
                page.screenshot(path="error_title_failed.png")

            # ======== 分类：生活 → 生活小窍门 ========
            print("📁 选择分类: 生活 → 生活小窍门")
            try:
                category_input = page.locator("input[name='type'][placeholder='请选择分类']")
                category_input.wait_for(timeout=10000)
                category_input.click()
                print("✅ 已点击【选择分类】输入框，等待下拉面板...")

                # 一级分类：生活
                life_item = page.locator("div.list-container div.list:has-text('生活')")
                life_item.wait_for(timeout=5000)
                life_item.click()
                print("✅ 已选择【生活】")

                # 二级分类：生活小窍门
                list2_container = page.locator("div.list2-container:has-text('家居房产宠物时尚运动健身美女生活小窍门手工生活测评母婴育儿人文摄影美食生活日常情感VLOG手绘设计旅游')")
                list2_container.wait_for(state="visible", timeout=10000)
                tip_item = list2_container.locator("div.list:has-text('生活小窍门')")
                tip_item.wait_for(timeout=5000)
                tip_item.click()
                print("✅ 已选择【生活小窍门】")

                # 验证
                selected_value = category_input.input_value()
                if "生活" in selected_value and "生活小窍门" in selected_value:
                    print(f"✅✅ 分类已正确设置: {selected_value}")
                else:
                    print(f"⚠️ 分类显示未更新: {selected_value}")

            except Exception as e:
                print(f"❌ 分类选择失败: {e}")
                page.screenshot(path="error_category_failed.png")

            # ======== 内容类型：原创 / 转载（咪咕新必选项） ========
            print("🔄 设置内容类型:", content_type)
            try:
                content_type_input = page.locator("input[placeholder='请选择内容类型']")
                content_type_input.wait_for(timeout=10000)
                content_type_input.click()  # 弹出下拉
                page.wait_for_timeout(800)
                print("✅ 已点击【请选择内容类型】输入框，等待下拉...")

                if content_type == "original":
                    # 选择"原创"
                    page.locator("div.select-item:has-text('原创')").first.click()
                    print("✅ 内容类型: 原创")
                elif content_type == "reposted":
                    # 选择"转载"，并填写来源
                    page.locator("div.select-item:has-text('转载')").first.click()
                    page.wait_for_timeout(800)
                    print("✅ 内容类型: 转载")
                    if source_url:
                        try:
                            source_input = page.locator("input[placeholder='请输入转载来源']")
                            source_input.wait_for(timeout=5000)
                            source_input.fill(source_url)
                            print(f"✅ 转载来源已填: {source_url}")
                        except Exception as e:
                            print(f"⚠️ 转载来源填写失败: {e}")
                    else:
                        print("⚠️ 选择了转载但未提供 --source-url，请手动补充")
                else:
                    print(f"⚠️ 未知 content_type: {content_type}，默认尝试选原创")
                    page.locator("div.select-item:has-text('原创')").first.click()
            except Exception as e:
                print(f"⚠️ 内容类型选择失败: {e}")

            # ======== 内容声明：AI 生成 / 原创 / 娱乐 等（咪咕新必选项） ========
            # 声明文案映射：用户友好名 → 实际页面显示文本
            declaration_text_map = {
                "AI生成":     "内容由AI生成或合成",
                "AI辅助创作":  "内容由AI生成或合成",
                "AI":         "内容由AI生成或合成",
                "原创":       "内容无需标注",
                "娱乐":       "内容为剧情演绎，仅供娱乐",
                "个人观点":    "个人观点，仅供参考",
                "营销":       "内容含营销信息",
            }
            actual_decl_text = declaration_text_map.get(content_declaration, content_declaration)
            print("📝 设置内容声明:", content_declaration, "→", actual_decl_text)
            try:
                decl_input = page.locator("input[placeholder='请添加内容声明']")
                decl_input.wait_for(timeout=10000)
                decl_input.click()  # 弹出下拉
                page.wait_for_timeout(800)
                print("✅ 已点击【请添加内容声明】输入框，等待下拉...")

                decl_item = page.locator(f"div.select-item:has-text('{actual_decl_text}')").first
                if decl_item.is_visible(timeout=5000):
                    decl_item.click()
                    print(f"✅ 内容声明已选择: {actual_decl_text}")
                else:
                    print(f"⚠️ 找不到声明文案: {actual_decl_text}")
            except Exception as e:
                print(f"⚠️ 内容声明选择失败: {e}")


            # ======== 设置横封面 ========
            print("🖼️ 正在设置横封面...")
            try:
                # 直接在函数内处理封面查找和转换（与后续封面上传逻辑一致）
                heng_cover = None
                heng_converted = None
                
                # 优先使用 --cover 参数指定的封面
                if cover_path and os.path.exists(cover_path):
                    heng_cover = cover_path
                    print(f"✅ 使用指定封面: {heng_cover}")
                else:
                    # 自动查找同目录下的封面
                    base = video_path.rsplit(".", 1)[0]
                    candidates = [base + ".jpg", base + ".png", base + ".jpeg"]
                    for cand in candidates:
                        if os.path.exists(cand):
                            heng_cover = cand
                            print(f"✅ 自动找到封面: {heng_cover}")
                            break
                
                # 格式转换
                if heng_cover:
                    try:
                        img = Image.open(heng_cover)
                        temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                        heng_converted = temp_file.name
                        temp_file.close()
                        
                        if img.mode in ("RGBA", "LA"):
                            background = Image.new("RGB", img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[-1])
                            background.save(heng_converted, "JPEG", quality=95)
                        else:
                            img.convert("RGB").save(heng_converted, "JPEG", quality=95)
                        
                        print(f"🎨 封面已转换为 JPG: {heng_converted}")
                        heng_cover = heng_converted
                    except Exception as e:
                        print(f"⚠️ 封面转换失败: {e}")
                
                # 点击"设置横封面"按钮
                if heng_cover:
                    set_cover_btn = page.locator("span.editText:has-text('设置横封面')")
                    if set_cover_btn.is_visible(timeout=5000):
                        set_cover_btn.click()
                        page.wait_for_timeout(1500)
                        print("✅ 已点击设置横封面按钮")
                        
                        # 找到第一个 upload-location-img（横封面）
                        upload_dialogs = page.locator("div.upload-location-img")
                        count = upload_dialogs.count()
                        print(f"📊 找到 {count} 个上传对话框")
                        
                        if count > 0:
                            # 获取第一个对话框里的 input[type='file']
                            cover_input = upload_dialogs.first.locator("input[type='file']")
                            if cover_input.count() > 0:
                                cover_input.first.set_input_files(heng_cover)
                                print(f"✅ 横封面图片已设置: {heng_cover}")
                                
                                # 等待图片上传，然后点击"完成"按钮
                                page.wait_for_timeout(2000)
                                try:
                                    # 使用文本选择器找到"完成"按钮
                                    finish_btns = page.get_by_text("完成")
                                    print(f"📊 找到 {finish_btns.count()} 个'完成'按钮")
                                    
                                    # 遍历找到可见且可点击的
                                    for i in range(finish_btns.count()):
                                        btn = finish_btns.nth(i)
                                        if btn.is_visible() and btn.is_enabled():
                                            btn.click()
                                            print("✅ 横封面已确认，点击了完成按钮")
                                            page.wait_for_timeout(1000)
                                            break
                                    else:
                                        print("➡️ 未找到可见的完成按钮，跳过")
                                except Exception as e:
                                    print(f"⚠️ 点击完成按钮失败（可忽略）: {e}")
                            else:
                                print("⚠️ 未找到横封面 input[type='file']")
                        else:
                            print("⚠️ 未找到上传对话框")
                    else:
                        print("➡️ 未找到设置横封面按钮，跳过")
                else:
                    print("➡️ 无封面文件，跳过横封面设置")
            except Exception as e:
                print(f"⚠️ 设置横封面失败（可忽略）: {e}")

            # ======== 设置竖封面 ========
            print("🖼️ 正在设置竖封面...")
            try:
                # 直接在函数内处理封面查找和转换
                shu_cover = None
                shu_converted = None
                
                # 优先使用 --cover 参数指定的封面
                if cover_path and os.path.exists(cover_path):
                    shu_cover = cover_path
                    print(f"✅ 使用指定封面: {shu_cover}")
                else:
                    # 自动查找同目录下的封面
                    base = video_path.rsplit(".", 1)[0]
                    candidates = [base + ".jpg", base + ".png", base + ".jpeg"]
                    for cand in candidates:
                        if os.path.exists(cand):
                            shu_cover = cand
                            print(f"✅ 自动找到封面: {shu_cover}")
                            break
                
                # 格式转换
                if shu_cover:
                    try:
                        img = Image.open(shu_cover)
                        temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                        shu_converted = temp_file.name
                        temp_file.close()
                        
                        if img.mode in ("RGBA", "LA"):
                            background = Image.new("RGB", img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[-1])
                            background.save(shu_converted, "JPEG", quality=95)
                        else:
                            img.convert("RGB").save(shu_converted, "JPEG", quality=95)
                        
                        print(f"🎨 封面已转换为 JPG: {shu_converted}")
                        shu_cover = shu_converted
                    except Exception as e:
                        print(f"⚠️ 封面转换失败: {e}")
                
                # 点击"设置竖封面"按钮
                if shu_cover:
                    set_cover_btn = page.locator("span.editText:has-text('设置竖封面')")
                    if set_cover_btn.is_visible(timeout=5000):
                        set_cover_btn.click()
                        page.wait_for_timeout(1500)
                        print("✅ 已点击设置竖封面按钮")
                        
                        # 找到 upload-location-img（竖封面）
                        upload_dialogs = page.locator("div.upload-location-img")
                        count = upload_dialogs.count()
                        print(f"📊 找到 {count} 个上传对话框")
                        
                        if count > 1:
                            # 获取第二个对话框里的 input[type='file']（竖封面）
                            cover_input = upload_dialogs.nth(1).locator("input[type='file']")
                            if cover_input.count() > 0:
                                cover_input.first.set_input_files(shu_cover)
                                print(f"✅ 竖封面图片已设置: {shu_cover}")
                                
                                # 等待图片上传，然后点击"完成"按钮
                                page.wait_for_timeout(2000)
                                try:
                                    # 使用文本选择器找到"完成"按钮
                                    finish_btns = page.get_by_text("完成")
                                    print(f"📊 找到 {finish_btns.count()} 个'完成'按钮")
                                    
                                    # 遍历找到可见且可点击的
                                    for i in range(finish_btns.count()):
                                        btn = finish_btns.nth(i)
                                        if btn.is_visible() and btn.is_enabled():
                                            btn.click()
                                            print("✅ 竖封面已确认，点击了完成按钮")
                                            page.wait_for_timeout(1000)
                                            break
                                    else:
                                        print("➡️ 未找到可见的完成按钮，跳过")
                                except Exception as e:
                                    print(f"⚠️ 点击完成按钮失败（可忽略）: {e}")
                            else:
                                print("⚠️ 未找到竖封面 input[type='file']")
                        else:
                            print("⚠️ 未找到足够的对话框，可能只有横封面")
                    else:
                        print("➡️ 未找到设置竖封面按钮，跳过")
                else:
                    print("➡️ 无封面文件，跳过竖封面设置")
            except Exception as e:
                print(f"⚠️ 设置竖封面失败（可忽略）: {e}")



            # ======== 封面上传（WebP → JPG 自动转换）========
            print("🖼️ 开始处理封面上传...")
            final_cover = None
            converted_cover = None

            # --- 封面路径解析 ---
            if cover_path and os.path.exists(cover_path):
                final_cover = cover_path
                print(f"✅ 使用指定封面: {final_cover}")
            else:
                base = video_path.rsplit(".", 1)[0]
                candidates = [base + ".jpg", base + ".png", base + ".jpeg"]
                for cand in candidates:
                    if os.path.exists(cand):
                        final_cover = cand
                        print(f"✅ 自动找到封面: {final_cover}")
                        break
                if not final_cover:
                    print(f"⚠️ 未找到封面文件，支持格式: {candidates}")
                    print("💡 提示：可使用 --cover /path/to/cover.jpg 指定封面")

            # --- 格式转换：WebP → JPG ---
            if final_cover:
                try:
                    img = Image.open(final_cover)
                    temp_file = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
                    converted_cover = temp_file.name
                    temp_file.close()

                    if img.mode in ("RGBA", "LA"):
                        background = Image.new("RGB", img.size, (255, 255, 255))
                        background.paste(img, mask=img.split()[-1])
                        background.save(converted_cover, "JPEG", quality=95)
                    else:
                        img.convert("RGB").save(converted_cover, "JPEG", quality=95)

                    print(f"🎨 已将封面转换为 JPG: {converted_cover}")
                    final_cover = converted_cover
                except Exception as e:
                    print(f"⚠️ 封面格式转换失败，尝试直接上传原图: {e}")

            # --- 执行上传 ---
            if final_cover:
                try:
                    upload_text_btn = page.locator("div.up-btn:has-text('上传封面'):visible").first
                    upload_text_btn.wait_for(timeout=10000)
                    upload_text_btn.click()
                    print("✅ “上传封面”按钮已点击")
                    page.wait_for_timeout(1000)

                    all_inputs = page.locator("input.cover-btn[type='file']")
                    count = all_inputs.count()
                    print(f"📊 找到 {count} 个 input.cover-btn 元素")

                    cover_input = all_inputs.last
                    cover_input.wait_for(timeout=5000)
                    cover_input.set_input_files(final_cover)
                    print("✅ 封面文件（JPG）已注入")

                    # 跳过预览检测
                    print("🖼️ 封面已上传，跳过预览检测")

                    # ======== 自动点击【完成】裁剪 ========
                    print("✂️ 检查是否需要裁剪...")
                    try:
                        finish_btn = page.locator("div.btn.finish:has-text('完成')")
                        if finish_btn.is_visible(timeout=5000):
                            print("✅ 发现裁剪面板，正在点击【完成】...")
                            finish_btn.click()
                            page.wait_for_timeout(1500)
                            print("✅ 裁剪已完成")
                        else:
                            print("➡️ 无需裁剪或已自动完成")
                    except Exception as e:
                        print(f"⚠️ 裁剪点击失败（可忽略）: {e}")

                except Exception as e:
                    print(f"❌ 封面上传失败: {e}")
                    page.screenshot(path="error_cover_upload.png")
            else:
                print("❌ 跳过封面上传")

            # ======== 描述（自动截断到200字）========
            if description:
                try:
                    # 截断到200字
                    if len(description) > 200:
                        description = description[:200]
                        print("💬 描述内容已截断到200字")
                    
                    desc_box = page.locator("textarea, [contenteditable='true']").first
                    desc_box.wait_for(timeout=10000)
                    if desc_box.is_visible():
                        desc_box.fill(description)
                        print(f"💬 描述已填写（{len(description)}字）")
                except Exception as e:
                    print(f"❌ 填写描述失败: {e}")

            # ======== 标签 ========
            if tags:
                try:
                    tag_input = page.locator("input[placeholder='添加标签']").first
                    tag_input.wait_for(timeout=10000)
                    for tag in tags:
                        tag_input.fill(tag)
                        page.press("Enter")
                        page.wait_for_timeout(300)
                    print(f"🏷️ 已添加标签: {', '.join(tags)}")
                except Exception as e:
                    print(f"❌ 添加标签失败: {e}")

            # ======== 自动点击【发布】按钮 ========
            print("📤 正在等待并点击【发布】按钮...")
            try:
                publish_btn = page.locator("div.publish-btn.activeBtn:has-text('发布')")
                if publish_btn.is_visible(timeout=20000) and publish_btn.is_enabled():
                    print("✅✅【发布】按钮已激活，正在点击...")
                    publish_btn.click()
                    page.wait_for_timeout(1000)
                else:
                    print("❌【发布】按钮未激活，请检查页面是否填写完整")
                    page.screenshot(path="publish_btn_not_active.png")
                    input("⏸️ 请手动检查后按回车键退出...")
                    return
            except Exception as e:
                print(f"❌ 自动发布失败: {e}")
                page.screenshot(path="error_publish_failed.png")
                input("⏸️ 发布失败，请手动检查后按回车键退出...")
                return

            # ==================== 智能上传等待（抗闪屏版）====================
            print("⏳ 进入智能上传监控模式（抗闪屏、防误判）...")

            TARGET_URL = "https://www.miguvideo.com/mgs/share/migucreator/prd/index.html#/upload/contentManage"
            upload_started = False
            upload_completed = False
            total_wait = 0
            max_wait = 600  # 10分钟

            # 🔍 阶段1：确认上传真正开始（容忍闪屏）
            print("🔍 阶段1：等待上传启动（可能闪屏，请耐心...）")
            while total_wait < 60:
                if TARGET_URL in page.url:
                    print("✅ 奇怪！直接跳转了？视为成功。")
                    upload_completed = True
                    break

                # 检测上传面板是否出现
                has_upload_text = page.locator("div.load-text:has-text('正在上传中，请勿关闭窗口')").is_visible(timeout=1000)
                has_progress = page.locator("div.progress").is_visible(timeout=1000)

                if has_upload_text or has_progress:
                    print("✅ 上传已真正启动！进入阶段2：等待跳转。")
                    upload_started = True
                    break
                else:
                    print("⏸️ 上传尚未启动，继续等待...")
                    page.wait_for_timeout(2000)
                    total_wait += 2

            if not upload_started and not upload_completed:
                print("❌ 60秒内未检测到上传启动，可能发布未触发。")
                page.screenshot(path="upload_never_started.png")
            elif not upload_completed:
                # 📡 阶段2：上传进行中，只等跳转
                print("📡 阶段2：上传进行中，持续监控跳转状态...")
                total_wait = 0

                while total_wait < max_wait:
                    current_url = page.url

                    # ✅ 成功条件1：URL跳转
                    if TARGET_URL in current_url:
                        print(f"✅✅✅ 成功跳转！URL: {current_url}")
                        upload_completed = True
                        break

                    # ✅ 成功条件2：页面关键元素出现
                    try:
                        if page.locator("text=筛选").is_visible(timeout=2000):
                            print("🎉✅ 检测到内容管理页元素「筛选」，判定成功！")
                            upload_completed = True
                            break
                    except:
                        pass

                    # 📊 日志：打印当前进度
                    try:
                        progress_el = page.locator("div.progress")
                        if progress_el.is_visible(timeout=1000):
                            text = progress_el.inner_text()
                            print(f"📊 进度: {text}")
                    except:
                        pass

                    # 💤 继续等待
                    print("⏳ 上传进行中，尚未跳转，继续等待...")
                    page.wait_for_timeout(3000)
                    total_wait += 3

                if not upload_completed:
                    print("❌ 上传超时（10分钟），仍未跳转，请手动检查。")
                    page.screenshot(path="upload_timeout.png")

            # --- 最终结果 ---
            if upload_completed:
                print("🎉 视频发布流程圆满完成！")
                print(f"💃【叮咚！】您的视频「{title}」已成功发布！小美在平行宇宙向你招手啦～💫")
                time.sleep(3)
                context.close()
                browser.close()
            else:
                try:
                    if page.locator("div.el-message:has-text('发布成功')").is_visible(timeout=3000):
                        print("🟡 检测到「发布成功」提示，视为成功！")
                        print(f"💃【叮咚！】您的视频「{title}」已成功发布！小美在平行宇宙向你招手啦～💫")
                        time.sleep(3)
                        context.close()
                        browser.close()
                    else:
                        print("❌ 未能确认发布结果，请手动检查页面。")
                        page.screenshot(path="publish_result_unknown.png")
                        input("⏸️ 发布结果未知，请手动检查后按回车键退出...")
                except:
                    print("❌ 未能确认发布结果，请手动检查页面。")
                    page.screenshot(path="publish_result_unknown.png")
                    input("⏸️ 发布结果未知，请手动检查后按回车键退出...")

        except Exception as e:
            print(f"❌ 脚本执行出错: {e}")
            page.screenshot(path="error.png")
            input("⏸️ 发生异常，按回车键退出...")
        finally:
            # 先保存登录态，再关闭浏览器
            try:
                if context is not None and browser is not None:
                    # 检查 context 是否仍然有效
                    try:
                        context.storage_state(path=STORAGE_STATE_PATH)
                        print(f"✅ 登录态已保存至: {STORAGE_STATE_PATH}")
                    except Exception as save_err:
                        print(f"⚠️ 保存登录态时出错（可能浏览器已关闭）: {save_err}")
                        # 如果文件已存在，说明之前已保存
                        if os.path.exists(STORAGE_STATE_PATH):
                            print(f"✅ 登录态文件已存在: {STORAGE_STATE_PATH}")
            except Exception as e:
                print(f"⚠️ 保存登录态失败: {e}")
            
            # 再关闭浏览器
            try:
                if context:
                    context.close()
                if browser:
                    browser.close()
            except:
                pass


# ==================== 命令行入口 ====================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="咪咕视频自动发布工具（抗闪屏增强版）")
    parser.add_argument("video_path", help="视频文件的本地路径")
    parser.add_argument("--title", required=True, help="视频标题")
    parser.add_argument("--description", default="", help="视频描述")
    parser.add_argument("--tags", nargs="+", default=[], help="标签列表，用空格分隔")
    parser.add_argument("--cover", help="封面图片路径（支持 .webp，自动转为 .jpg）")
    parser.add_argument("--content-type", choices=["original", "reposted"], default="original", help="内容类型：original=原创，reposted=转载")
    parser.add_argument("--source-url", default="", help="转载来源（仅 --content-type reposted 时有效）")
    parser.add_argument("--declaration", default="AI生成", help="内容声明：AI生成 / 原创 / 娱乐 等（默认 AI生成）")

    args = parser.parse_args()

    try:
        publish_to_migu(
            video_path=args.video_path,
            title=args.title,
            description=args.description,
            tags=args.tags,
            cover_path=args.cover,
            content_type=args.content_type,
            source_url=args.source_url,
            content_declaration=args.declaration
        )
    except KeyboardInterrupt:
        print("\n👋 用户中断，正在保存登录态...")
        save_login_state_on_exit()
        sys.exit(0)
    except Exception as e:
        print(f"🔥 主程序异常: {e}")
        sys.exit(1)