#!/usr/bin/env ruby
# publish_all_platforms.rb - 统一发布脚本（修复 stdin 问题 + 实时日志）

require 'json'
require 'open3'
require 'shellwords'
require 'fileutils'

def run_script(script_path, *args)
  puts "🚀 正在执行: #{script_path} #{args.map { |a| Shellwords.escape(a) }.join(' ')}"

  cmd = "python -u #{Shellwords.escape(script_path)} #{args.map { |a| Shellwords.escape(a) }.join(' ')}"

  stdin, stdout, stderr, wait_thr = Open3.popen3(cmd)

  stdin.sync = true

  output = ""
  error = ""

  # 异步读取输出
  out_thread = Thread.new do
    begin
      while line = stdout.gets
        puts line
        output += line
      end
    rescue IOError
    end
  end

  err_thread = Thread.new do
    begin
      while line = stderr.gets
        puts line
        error += line
      end
    rescue IOError
    end
  end

  # ✅ 只保留 Ctrl+C 信号转发：收到中断时，杀掉子进程
  trap("INT") do
    puts "\n⚠️ 收到中断信号，正在终止子进程（PID: #{wait_thr.pid}）..."
    begin
      Process.kill("TERM", wait_thr.pid)
      sleep(1)
      Process.kill("KILL", wait_thr.pid)
    rescue Errno::ESRCH
      # 进程已不存在
    end
    puts "✅ 子进程已终止。"
    # 不退出，继续执行后续任务
  end

  # ✅ 移除超时！让子进程自由运行
  begin
    status = wait_thr.value  # 无限等待，直到子进程结束
  rescue Interrupt
    # 这个不会触发，因为 trap 已捕获 INT
    # 但为了安全，保留
    puts "❌ 子进程中断（由用户触发）"
    return false
  end

  # 等待输出线程结束
  out_thread.join
  err_thread.join

  stdin.close
  stdout.close
  stderr.close

  if status.success?
    puts "✅ #{script_path} 执行成功"
    return true
  else
    puts "❌ #{script_path} 执行失败: #{error}"
    return false
  end
end

# 新增：加载 Twitter 凭据（兼容环境变量 + ~/.blindbox/twitter.json）
def load_twitter_credentials
  # 1. 尝试从环境变量加载
  creds = {
    "consumer_key" => ENV["TWITTER_CONSUMER_KEY"],
    "consumer_secret" => ENV["TWITTER_CONSUMER_SECRET"],
    "access_token" => ENV["TWITTER_ACCESS_TOKEN"],
    "access_token_secret" => ENV["TWITTER_ACCESS_TOKEN_SECRET"]
  }

  if creds.values.all? { |v| !v.nil? && !v.empty? }
    puts "🔑 Twitter 凭据已从环境变量加载"
    return creds
  end

  # 2. 回退到配置文件 ~/.blindbox/twitter.json
  config_path = File.expand_path("~/.blindbox/twitter.json")
  if File.exist?(config_path)
    begin
      file_creds = JSON.parse(File.read(config_path))
      creds_from_file = {
        "consumer_key" => file_creds["consumer_key"] || file_creds["api_key"],
        "consumer_secret" => file_creds["consumer_secret"] || file_creds["api_secret"],
        "access_token" => file_creds["access_token"],
        "access_token_secret" => file_creds["access_token_secret"]
      }

      if creds_from_file.values.all? { |v| !v.nil? && !v.empty? }
        puts "🔑 Twitter 凭据已从配置文件加载: #{config_path}"
        return creds_from_file
      else
        missing = creds_from_file.select { |k, v| v.nil? || v.empty? }.keys
        puts "⚠️ 配置文件 #{config_path} 缺少必要字段: #{missing.join(', ')}"
      end
    rescue => e
      puts "❌ 读取 Twitter 配置文件失败: #{e.message}"
    end
  else
    puts "⚠️ Twitter 配置文件不存在: #{config_path}"
  end

  puts "❌ 未找到完整的 Twitter API 凭据（环境变量或 ~/.blindbox/twitter.json）"
  return nil
end

# 获取参数
if ARGV.length < 1
  puts "用法: ruby publish_all_platforms.rb <output_video_path>"
  exit 1
end

output_video = ARGV[0]
output_info_path = File.join(File.dirname(output_video), "output_info.json")

# 读取元信息
begin
  output_info = JSON.parse(File.read(output_info_path))
  title = output_info["title"].strip
  description = output_info["description"].strip
  cover_image = output_info["cover_image"].strip
rescue => e
  puts "⚠️ 未找到或无法解析 output_info.json (#{e.message})，使用默认参数"
  title = ""
  description = ""
  cover_image = ""
end

# 执行发布
success = true

# YouTube
youtube_script = File.join(File.dirname(__FILE__), '..', 'Python.91', 'upload.youtube.pg.py')
if File.exist?(youtube_script)
  args = [output_video, "--title", title]
  args += ["--description", description] unless description.empty?
  success &= run_script(youtube_script, *args)
else
  puts "⚠️ YouTube脚本未找到: #{youtube_script}"
end

# 虎牙
huya_script = File.join(File.dirname(__FILE__), '..', 'Python.91', 'publish_huya.py')
if File.exist?(huya_script)
  args = [output_video, "--desc", description]
  success &= run_script(huya_script, *args)
else
  puts "⚠️ 虎牙脚本未找到: #{huya_script}"
end

# 斗鱼
douyu_script = File.join(File.dirname(__FILE__), '..', 'Python.91', 'publish.douyu.pg.py')
if File.exist?(douyu_script) && !title.empty?
  args = [output_video, title]
  success &= run_script(douyu_script, *args)
else
  puts "⚠️ 斗鱼脚本未找到或缺少标题"
end

# 优酷
youku_script = File.join(File.dirname(__FILE__), '..', 'Python.91', 'auto_upload_youku.dt.py')
if File.exist?(youku_script) && !title.empty?
  args = [output_video, "--title", title]
  args += ["--description", description] unless description.empty?
  success &= run_script(youku_script, *args)
else
  puts "⚠️ 优酷脚本未找到或缺少标题"
end

# --- 微博 ---
weibo_script = File.join(File.dirname(__FILE__), '..', 'Python.91', 'auto_upload_weibo.py')
if File.exist?(weibo_script)
  args = [output_video, "--title", title]
  args += ["--description", description] unless description.empty?
  success &= run_script(weibo_script, *args)
else
  puts "⚠️ 微博脚本未找到: #{weibo_script}"
end

# --- 哔哩哔哩 ---
bilibili_script = File.join(File.dirname(__FILE__), '..', 'Python.91', 'auto_upload_bilibili.py')
if File.exist?(bilibili_script)
  args = [output_video, "--title", title]
  args += ["--description", description] unless description.empty?
  success &= run_script(bilibili_script, *args)
else
  puts "⚠️ 哔哩哔哩脚本未找到: #{bilibili_script}"
end

# 咪咕
migu_script = File.join(File.dirname(__FILE__), '..', 'Python.91', 'migu_publisher.ebp.py')
if File.exist?(migu_script) && !cover_image.empty? && File.exist?(cover_image)
  args = [output_video, "--title", title, "--description", description, "--cover", cover_image]
  success &= run_script(migu_script, *args)
else
  puts "⚠️ 咪咕脚本未找到或缺少封面（路径：#{cover_image}）"
end

# Twitter ✅ 修复：仅使用 139s 版本，不存在则回退到原始视频
twitter_script = File.join(File.dirname(__FILE__), '..', 'Python.91', 'publish_twitter_video.py')
if File.exist?(twitter_script)
  creds = load_twitter_credentials
  if creds && !title.empty?
    tweet_text = "#{title}\n\n#{description}".strip
    tweet_text = tweet_text[0..257] + "..." if tweet_text.length > 260

    # ✅ 仅使用 cut_video_139，不存在则回退到原始视频
    selected_video = nil
    if output_info["cut_video_139"] && File.exist?(output_info["cut_video_139"])
      selected_video = output_info["cut_video_139"]
      puts "📎 选择 139s 裁剪视频: #{selected_video}"
    else
      selected_video = output_video
      puts "📎 未找到 139s 裁剪视频，使用原始文件: #{selected_video}"
    end

    args = [
      "--consumer-key", creds["consumer_key"],
      "--consumer-secret", creds["consumer_secret"],
      "--access-token", creds["access_token"],
      "--access-token-secret", creds["access_token_secret"],
      "--video", selected_video,
      "--text", tweet_text
    ]
    success &= run_script(twitter_script, *args)
  else
    puts "⚠️ Twitter凭据缺失或缺少标题"
  end
else
  puts "⚠️ Twitter脚本未找到"
end

# 返回结果
exit success ? 0 : 1
