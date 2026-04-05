#!/usr/bin/env python3

import os
import sys
from PIL import Image

def crop_center(img, desired_ratio):
    width, height = img.size
    actual_ratio = width / height
    if actual_ratio > desired_ratio:
        # 基于宽度裁剪
        new_width = int(height * desired_ratio)
        offset = (width - new_width) // 2
        crop_dimensions = (offset, 0, offset + new_width, height)
    else:
        # 基于高度裁剪
        new_height = int(width / desired_ratio)
        offset = (height - new_height) // 2
        crop_dimensions = (0, offset, width, offset + new_height)
    return img.crop(crop_dimensions)

def get_output_path(input_path, output_filename):
    # 获取输入文件所在的目录
    directory = os.path.dirname(input_path)
    # 构建输出文件的完整路径
    return os.path.join(directory, output_filename)

def main():
    # 预设的文件名
    default_filename = 'ger.a.png'
    
    # 检查是否有命令行参数
    if len(sys.argv) > 1:
        filename = sys.argv[1]
    else:
        filename = default_filename
    
    try:
        img = Image.open(filename)
        
        # 裁剪图片
        img_16_9 = crop_center(img, 16/9)
        img_5_7 = crop_center(img, 5/7)
        
        # 保存裁剪后的图片
        output_path_16_9 = get_output_path(filename, 'cropped_16_9.jpg')
        output_path_5_7 = get_output_path(filename, 'cropped_5_7.jpg')
        
        img_16_9.save(output_path_16_9)
        img_5_7.save(output_path_5_7)
        
        print(f"Cropped images saved to:\n{output_path_16_9}\n{output_path_5_7}")
    except FileNotFoundError:
        print(f"Error: The file {filename} does not exist.")
    except IOError:
        print(f"Error: Could not open the file {filename}.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
