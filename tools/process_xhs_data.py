import os
import json
import glob
from datetime import datetime, timedelta
import requests
import time

def process_mediacrawler_data(mediacrawler_dir, output_base_dir):
    # MediaCrawler 默认的数据保存路径 (jsonl 格式)
    jsonl_dir = os.path.join(mediacrawler_dir, "data", "xhs", "jsonl")
    
    if not os.path.exists(jsonl_dir):
        print(f"未找到数据目录: {jsonl_dir}，请确保 MediaCrawler 已成功运行并保存了 jsonl 数据。")
        return

    # 获取所有的 jsonl 文件
    jsonl_files = glob.glob(os.path.join(jsonl_dir, "*.jsonl"))
    if not jsonl_files:
        print("未找到任何 jsonl 数据文件。")
        return

    # 创建输出基础文件夹
    if not os.path.exists(output_base_dir):
        os.makedirs(output_base_dir)

    # 设定期限：近三个月 (90天)
    three_months_ago = datetime.now() - timedelta(days=90)
    
    # 获取所有的帖子记录
    records = []
    for f_path in jsonl_files:
        with open(f_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        record = json.loads(line)
                        records.append(record)
                    except json.JSONDecodeError as e:
                        print(f"解析 JSON 出错: {e}")

    print(f"共读取到 {len(records)} 条原始记录。")

    processed_count = 0
    for record in records:
        note_id = record.get("note_id", "")
        # 如果是视频且没有图片，可以跳过；但为了以防万一，都处理
        # 时间解析 (获取毫秒级时间戳或直接是字符串时间)
        timestamp = record.get("time", 0)
        
        note_time_str = ""
        note_date_obj = None
        
        try:
            # 可能是时间戳 (毫秒或秒)
            if isinstance(timestamp, (int, float)):
                if timestamp > 1e11: # 毫秒
                    timestamp = timestamp / 1000.0
                note_date_obj = datetime.fromtimestamp(timestamp)
            # 或直接是时间字符串
            elif isinstance(timestamp, str):
                # 尝试解析格式，有时长这样：2023-01-01 12:00:00，或者只是时间戳字符串
                if timestamp.isdigit():
                    ts = float(timestamp)
                    if ts > 1e11: ts /= 1000.0
                    note_date_obj = datetime.fromtimestamp(ts)
                else:
                    note_date_obj = datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"时间解析失败 [{note_id}]: {timestamp}, {e}")
            continue

        if not note_date_obj:
            continue

        # 过滤近 3 个月的帖子
        if note_date_obj < three_months_ago:
            continue
            
        note_time_str = note_date_obj.strftime("%Y-%m-%d %H:%M:%S")

        # 提取字段
        title = record.get("title", "")
        desc = record.get("desc", "")
        likes = record.get("liked_count", "0")
        collections = record.get("collected_count", "0")
        views = record.get("view_count", "未知")  # 小红书可能没有直接的浏览量
        
        # 准备创建文件夹
        # 处理非法字符
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()[:20]
        if not safe_title:
            safe_title = "笔记"
        post_folder_name = f"{note_date_obj.strftime('%Y%m%d')}_{safe_title}_{note_id}"
        post_folder_path = os.path.join(output_base_dir, post_folder_name)
        
        if not os.path.exists(post_folder_path):
            os.makedirs(post_folder_path)

        # 1. 写入 txt 文本信息
        txt_path = os.path.join(post_folder_path, "info.txt")
        info_content = f"笔记ID: {note_id}\n"
        info_content += f"发帖时间: {note_time_str}\n"
        info_content += f"点赞量: {likes}\n"
        info_content += f"收藏量: {collections}\n"
        info_content += f"浏览量: {views}\n"
        info_content += f"标题: {title}\n"
        info_content += f"文案:\n{desc}\n"

        with open(txt_path, 'w', encoding='utf-8') as tf:
            tf.write(info_content)

        # 2. 下载图片
        images = record.get("image_list", [])
        if isinstance(images, str):
            # 有时被存为逗号分隔的字符串
            images = [img for img in images.split(",") if img]

        print(f"正在处理: {post_folder_name} | 图片数量: {len(images)}")
        
        for idx, img_url in enumerate(images):
            try:
                # 去除非法或无用的前后缀
                img_url = img_url.strip()
                if not img_url.startswith("http"):
                    img_url = "https:" + img_url if img_url.startswith("//") else "https://" + img_url

                res = requests.get(img_url, timeout=10)
                if res.status_code == 200:
                    img_path = os.path.join(post_folder_path, f"img_{idx + 1}.jpg")
                    with open(img_path, 'wb') as img_f:
                        img_f.write(res.content)
            except Exception as e:
                print(f"  -> 图片下载失败 [{img_url}]: {e}")
        
        processed_count += 1
        time.sleep(0.5) # 防止过于频繁请求

    print(f"处理完成！符合近3个月条件的有效帖子共 {processed_count} 篇。数据保存在: {output_base_dir}")

if __name__ == "__main__":
    # 配置你的路径
    # MediaCrawler 所在的根目录
    MC_DIR = r"E:\workspace\kakaa\MediaCrawler-main"
    # 你想保存到的基础结构数据文件夹
    OUTPUT_DIR = r"E:\workspace\kakaa\Fashion_Dataset"
    
    process_mediacrawler_data(MC_DIR, OUTPUT_DIR)
