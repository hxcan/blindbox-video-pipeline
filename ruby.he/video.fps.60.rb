#!/usr/bin/env ruby

require 'json'
require 'pathname'

# 获取当前脚本文件的绝对路径
script_path = Pathname.new(__FILE__).realpath
# 获取Ruby脚本所在的目录
ruby_script_dir = script_path.dirname
# 共同的上层目录是Ruby脚本所在目录的父目录
common_parent_dir = ruby_script_dir.dirname

# 检查参数：输入文件 + 标题
if ARGV.length < 2
    puts "Usage: #{$0} <input_video_file> <title>"
    puts "Example: #{$0} /path/to/input.mp4 '日本传统色'"
    exit 1
end

input_file = ARGV[0]
title = ARGV[1]  # 直接使用命令行传入的标题

# 检查文件是否存在
unless File.exist?(input_file)
    puts "Input file does not exist: #{input_file}"
    exit 1
end

# 生成输出文件名：使用传入的标题
base_dir = File.dirname(input_file)
output_filename = "#{title}.60.mp4"
output_file = File.join(base_dir, output_filename)

output_video_only = output_file.gsub(/\.mp4$/, '.video-only.mp4')

# 转换命令（带音频）
conversion_command = "ffmpeg -y -err_detect ignore_err -fflags +discardcorrupt -i \"#{input_file}\" -vf \"fps=fps=60\" -c:v libx264 -crf 18 -preset veryfast -c:a aac -b:a 192k -strict experimental -bsf:a aac_adtstoasc -map 0:v:0 -map 0:a:0? -async 1 -vsync 2 \"#{output_file}\""
ret = system(conversion_command)

# 如果失败，尝试无音频转换
if !ret
    puts "First conversion attempt failed, attempting video-only conversion..."
    conversion_command = "ffmpeg -y -i \"#{input_file}\" -vf \"fps=fps=60\" -c:v libx264 -crf 18 -preset veryfast -an \"#{output_video_only}\""
    ret = system(conversion_command)

    if !ret
        puts "Video-only conversion also failed."
        exit 1
    else
        puts "Video-only conversion succeeded."
        output_file = output_video_only
    end
else
    puts "Conversion with robust parameters succeeded."
end

# ========== 更新原有的 output_info.json，追加 title 字段 ==========
info_hash = {
    input_file: input_file,
    output_file: output_file,
    title: title,
    conversion_status: ret ? "success" : "failure",
    timestamp: Time.now.to_s
}

File.open("output_info.json", "w") do |f|
    f.write(JSON.pretty_generate(info_hash))
end

puts "Output file is: #{output_file}"
puts "Metadata (including title) saved to output_info.json"

# 在转换成功后调用Python脚本
if ret
    python_script_path = common_parent_dir.join('Python.91', 'remove.static.frames.api.py').to_s
    fixed_param = '0.08'
    system("python3 #{python_script_path} \"#{output_file}\" #{fixed_param}")
    puts "Called Python script with arguments: #{output_file} and #{fixed_param}"
end
