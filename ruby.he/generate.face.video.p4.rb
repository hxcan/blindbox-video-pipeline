#!/usr/bin/env ruby

require 'shellwords'
require 'json'
require 'fileutils'
require 'rest-client'

# 检查命令行参数
if ARGV.length < 1 || ARGV.length > 2
  puts "Usage: ruby script.rb <path_to_wav_file> [path_to_face_image]"
  exit(1)
end

input_file = ARGV[0]
face_image_path = ARGV.length == 2 ? ARGV[1] : nil

unless File.exist?(input_file)
  puts "Error: Audio file not found."
  exit(1)
end

if face_image_path && !File.exist?(face_image_path)
  puts "Error: Face image file not found. #{face_image_path}"
  exit(1)
end

puts "Face image: #{face_image_path}"

# 设置超时时间（单位：秒）
open_timeout = 50
read_timeout = 3600

CONTAINER_NAME = "sadtalker_service"

def start_docker_service
  system("docker rm -f #{CONTAINER_NAME}")
  system("docker run --name #{CONTAINER_NAME} -d -p 42531:5000 -e DISABLE_FACE_ENHANCER=true hxcan/sadtalker:2025.7.15")
  sleep(2)
end

def restart_docker_service
  sleep(2)
  system("docker stop #{CONTAINER_NAME}")
  system("docker rm -f #{CONTAINER_NAME}")
  start_docker_service
end

def make_request(url, payload, open_timeout, read_timeout)
  RestClient::Request.execute(
    method: :post,
    url: url,
    payload: payload,
    headers: { content_type: :multipart_form },
    open_timeout: open_timeout,
    read_timeout: read_timeout
  )
end

# 👇 读取本地配置文件：包含 url 和 stickToCloudService
def load_config
  config_file = File.expand_path("~/.blindbox/sadtalker.service.json")
  return nil unless File.exist?(config_file)

  begin
    config = JSON.parse(File.read(config_file))
    url = config["url"]&.chomp('/')
    stick_to_cloud = !!config["stickToCloudService"]  # 转为布尔值，默认 false
    return { url: url, stick_to_cloud: stick_to_cloud } if url && !url.empty?
  rescue JSON::ParserError => e
    puts "⚠️  Failed to parse ~/.blindbox/sadtalker.service.json: #{e.message}"
  end
  nil
end

# 构造请求体
def makePayload(input_file, face_image_path)
  driven_audio = File.new(input_file, 'rb')
  source_image = face_image_path ? File.new(face_image_path, 'rb') : nil

  payload = { driven_audio: driven_audio }
  payload[:source_image] = source_image if source_image

  payload
end

# ========================
#       主逻辑开始
# ========================
begin
  payload = makePayload(input_file, face_image_path)

  # 👉 加载配置
  config = load_config
  cloud_url = config ? config[:url] : nil
  stick_to_cloud = config ? config[:stick_to_cloud] : false

  response = nil

  if cloud_url
    if stick_to_cloud
      # 🔁 持续重试云端，直到成功
      puts "🔁 stickToCloudService=true: Will keep retrying cloud service until success."
      puts "🌐 Cloud URL: #{cloud_url}/animate"

      loop do
        begin
          puts "📤 Sending request to cloud..."
          response = make_request("#{cloud_url}/animate", payload, open_timeout, read_timeout)
          if response.code == 200
            puts "✅ Cloud request succeeded!"
            break  # 成功则跳出循环
          else
            puts "☁️  Cloud responded with status #{response.code}. Retrying in 5 seconds..."
            puts "📝 Response body: #{response.body}" if response.body
            sleep(5)
            payload = makePayload(input_file, face_image_path) # 重新构造 payload
          end
        rescue => e
          puts "☁️  Cloud request failed: #{e.message}."
          # ✅ 关键：尝试打印详细错误信息
          if e.respond_to?(:response) && e.response
            puts "📝 Detailed error from server:"
            puts e.response.body
          end
          puts "Retrying in 5 seconds..."
          sleep(5)
          payload = makePayload(input_file, face_image_path) # 重新构造
        end
      end

    else
      # ❌ 不 stick：尝试一次云端，失败则 fallback
      begin
        puts "📤 Sending request to cloud server: #{cloud_url}/animate"
        response = make_request("#{cloud_url}/animate", payload, open_timeout, read_timeout)
        if response.code == 200
          puts "✅ Cloud request succeeded."
        end
      rescue => e
        puts "☁️  Cloud request failed: #{e.message}."
        if e.respond_to?(:response) && e.response
          puts "📝 Server error details:"
          puts e.response.body
        end
        puts "Falling back to local service."
      end
    end
  else
    puts "⚠️ No cloud URL found in config."
  end

  # 👉 只有在不 stick 到云端的情况下，才 fallback 到本地
  unless response&.code == 200
    unless stick_to_cloud
      begin
        payload = makePayload(input_file, face_image_path) # 重新构造
        response = make_request("http://localhost:42531/animate", payload, open_timeout, read_timeout)
      rescue RestClient::InternalServerError, RestClient::Exceptions::ReadTimeout,
             RestClient::ServerBrokeConnection, RestClient::Exceptions::OpenTimeout,
             Errno::EADDRNOTAVAIL, Errno::ECONNREFUSED, Errno::ECONNRESET, Errno::ENETUNREACH, IOError => e
        puts "💻 Local server error: #{e.message}"
        puts "🔄 Starting Docker service..."
        start_docker_service
        retry
      end
    else
      # 理论上不会走到这里，因为上面的 loop 会一直重试
      puts "❌ Cloud service is required but failed to respond. Exiting."
      exit(1)
    end
  end

rescue => e
  puts "❌ Unexpected error during processing: #{e.message}"
  exit(1)
end

# ========================
#     处理成功响应
# ========================
if response&.code == 200
  output_dir = File.dirname(input_file)
  base_name = File.basename(input_file, File.extname(input_file))
  timestamp = Time.now.strftime("%Y%m%d-%H%M%S")
  output_mp4 = "#{output_dir}/#{base_name}.#{timestamp}_threshold_0.08.mp4.face.mp4"

  File.open(output_mp4, 'wb') { |f| f.write(response.body) }

  json_file = "#{output_dir}/output_files.json"
  output_info = { output_file: output_mp4 }
  all_outputs = if File.exist?(json_file) && !File.zero?(json_file)
                  JSON.parse(File.read(json_file))
                else
                  []
                end
  all_outputs << output_info
  File.open(json_file, 'w') { |f| f.write(JSON.pretty_generate(all_outputs)) }

  puts "✅ Processing completed. Output saved to #{output_mp4}"

  # 👇 新增：自动调用叠加脚本
  current_dir = Dir.pwd
  json_path = File.join(current_dir, 'processed_video_output.json')

  if File.exist?(json_path) && !File.zero?(json_path)
    begin
      json_data = JSON.parse(File.read(json_path))

      if json_data.is_a?(Array)
        videos = json_data
      elsif json_data.is_a?(Hash)
        videos = [json_data]
      else
        puts "⚠️ JSON 数据既不是数组也不是对象。"
        videos = []
      end

      if videos.any?
        overlay_base_name = videos.last["output_video_path"]
        overlay_video_path = File.join(current_dir, overlay_base_name)

        script_dir = File.dirname(__FILE__)
        python_script_path = File.join(script_dir, '..', 'Python.91', 'overlay.face.video.py')

        escaped_path = overlay_video_path.shellescape
        cmd = "python #{python_script_path} #{escaped_path} 1 100 100"
        puts "🎬 正在执行叠加操作：#{cmd}"
        system(cmd)

        if $?.success?
          puts "✅ 成功完成了视频叠加操作！🎉"
        else
          puts "⚠️ 视频叠加失败，请检查日志或路径问题。"
        end
      else
        puts "⚠️ JSON 文件为空或者格式错误。"
      end
    rescue => e
      puts "🚨 读取 JSON 文件出错：#{e.message}"
    end
  else
    puts "⚠️ 没有找到 processed_video_output.json 文件，跳过叠加步骤。"
  end

else
  puts "❌ Error processing file: HTTP Status Code #{response.code}" if response
  # ✅ 如果有响应体，也打印出来
  if response && response.respond_to?(:body)
    puts "📝 Response body: #{response.body}"
  end
end
