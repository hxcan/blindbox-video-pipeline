#!/usr/bin/env ruby

require 'json'
require 'pathname'

# 获取当前脚本文件的绝对路径
script_path = Pathname.new(__FILE__).realpath
# 获取Ruby脚本所在的目录
ruby_script_dir = script_path.dirname
# 共同的上层目录是Ruby脚本所在目录的父目录
common_parent_dir = ruby_script_dir.dirname

# 检查是否提供了输入文件和JSON状态文件参数
if ARGV.length < 1
    puts "Usage: #{$0} <input_video_file> [json_status_file]"
    exit 1
end

# 获取输入文件路径
input_file = ARGV[0]
json_status_file = ARGV[1] || "processed_video_output.json"  # 默认JSON文件名

# 检查输入文件是否存在
unless File.exist?(input_file)
    puts "Input file does not exist: #{input_file}"
    exit 1
end

# 生成输出文件名：input.mp4 → input_30fps.mp4
output_file = input_file.gsub(/\.mp4$/, '_30fps.mp4')

# 使用 ffmpeg 将帧率固定为 30fps，保持音频，自动覆盖
conversion_command = "ffmpeg -y -i \"#{input_file}\" -r 30 -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 192k \"#{output_file}\""

puts "🎬 正在将视频转为30fps: #{input_file}"
ret = system(conversion_command)

if ret
    puts "✅ 转换成功: #{output_file}"

    # 更新 JSON 文件中的 output_video_path
    begin
        if File.exist?(json_status_file)
            # 读取现有 JSON
            json_data = JSON.parse(File.read(json_status_file))

            # 👇 判断是 Hash 还是 Array，并分别处理
            if json_data.is_a?(Hash)
                # 格式1: { "output_video_path": "..." }
                json_data["output_video_path"] = output_file
            elsif json_data.is_a?(Array) && !json_data.empty?
                # 格式2: [ ..., { "output_video_path": "..." } ] ← 更新最后一个对象
                last_item = json_data.last  # 👈 只改这里：从 [0] 变成 .last
                if last_item.is_a?(Hash)
                    last_item["output_video_path"] = output_file
                end
            else
                puts "⚠️ 无法识别的 JSON 格式，跳过更新"
                exit 1
            end

            # 写回文件
            File.open(json_status_file, "w") do |f|
                f.write(JSON.pretty_generate(json_data))
            end
            puts "💾 已更新 JSON 文件: #{json_status_file}"
        else
            puts "⚠️  JSON 文件不存在: #{json_status_file}，跳过更新"
        end
    rescue => e
        puts "❌ 更新 JSON 时出错: #{e.message}"
        exit 1
    end

    # 🔥 调用下一个 Python 脚本：screenshot.random.frame.py
    # 路径结构：common_parent_dir / Python.91 / screenshot.random.frame.py
    python_script_dir = common_parent_dir.join('Python.91')
    python_script_path = python_script_dir.join('screenshot.random.frame.py').to_s

    if File.exist?(python_script_path)
        puts "🚀 调用截图脚本: #{python_script_path}"
        system("python3 #{python_script_path} \"#{json_status_file}\"")
        if $?.success?
            puts "✅ 截图脚本执行成功"
        else
            puts "❌ 截图脚本执行失败"
        end
    else
        puts "❌ 错误：未找到截图脚本: #{python_script_path}"
        exit 1
    end

else
    puts "❌ ffmpeg 转换失败，请检查输入文件或命令"
    exit 1
end
