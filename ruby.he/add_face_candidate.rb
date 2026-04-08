#!/usr/bin/env ruby
# encoding: utf-8

# add_face_candidate.rb
# 功能：将人脸照片文件名追加到候选列表 JSON 文件中
# 用法：ruby add_face_candidate.rb <文件路径>
# 示例：ruby add_face_candidate.rb "file:///Ibotex/.../cropped_photo.jpg"

require 'json'
require 'pathname'

# 获取脚本所在目录
SCRIPT_DIR = Pathname.new(__dir__).realpath

# 目标 JSON 文件的相对路径
JSON_FILE_PATH = SCRIPT_DIR.join('../Material/assets/face_templates.json')

# 从完整路径提取文件名
def extract_filename(file_path)
  # 处理 file:/// 协议前缀
  clean_path = file_path.sub(/^file:\/\//, '')
  
  # 处理 Windows 路径（如果有）
  clean_path = clean_path.sub(/^\//, '') if clean_path.match?(/^\/[A-Z]:/)
  
  # 提取文件名部分
  File.basename(clean_path)
end

# 读取 JSON 文件
def read_json_file(path)
  unless File.exist?(path)
    raise "错误：JSON 文件不存在 - #{path}"
  end
  
  content = File.read(path, encoding: 'utf-8')
  JSON.parse(content)
end

# 保存 JSON 文件
def write_json_file(path, data)
  json_content = JSON.pretty_generate(data)
  File.write(path, json_content, encoding: 'utf-8')
end

# 检查文件名是否已存在
def filename_exists?(data, filename)
  return false unless data['faces'] && data['faces'].is_a?(Array)
  data['faces'].any? { |face| face['filename'] == filename }
end

# 添加新文件名到列表
def add_face_candidate(data, filename)
  data['faces'] ||= []
  data['faces'] << { 'filename' => filename }
end

# 主函数
def main
  if ARGV.length < 1
    puts "用法：ruby add_face_candidate.rb <文件路径>"
    puts "示例：ruby add_face_candidate.rb \"file:///Ibotex/.../cropped_photo.jpg\""
    exit 1
  end
  
  file_path = ARGV[0]
  filename = extract_filename(file_path)
  
  puts "输入路径：#{file_path}"
  puts "提取文件名：#{filename}"
  puts "\n读取 JSON 文件：#{JSON_FILE_PATH}"
  
  data = read_json_file(JSON_FILE_PATH)
  
  if filename_exists?(data, filename)
    puts "\n⚠️  警告：文件名已存在于列表中，跳过添加。"
    puts "   当前列表共有 #{data['faces'].length} 个条目"
    exit 0
  end
  
  puts "\n添加新条目到列表..."
  add_face_candidate(data, filename)
  write_json_file(JSON_FILE_PATH, data)
  
  puts "\n✅ 成功！"
  puts "   已添加：#{filename}"
  puts "   当前列表共有 #{data['faces'].length} 个条目"
  puts "   文件已保存：#{JSON_FILE_PATH}"
end

main
