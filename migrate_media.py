#!/usr/bin/env python3
"""
媒體文件分離遷移腳本
將 SQLite 中的 Base64 數據導出為文件
"""
import sqlite3
import os
import base64
import json

DB_PATH = "cleaning.db"
UPLOAD_DIR = "uploads"

# 確保目錄存在
os.makedirs(os.path.join(UPLOAD_DIR, "images"), exist_ok=True)
os.makedirs(os.path.join(UPLOAD_DIR, "voice"), exist_ok=True)

def extract_completion_photos():
    """提取完工照片並保存為文件"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 獲取所有訂單
    cursor.execute("SELECT id, completion_photos FROM orders WHERE completion_photos IS NOT NULL AND completion_photos != ''")
    orders = cursor.fetchall()
    
    print(f"找到 {len(orders)} 個訂單需要處理照片...")
    
    for order_id, photos_json in orders:
        if not photos_json:
            continue
        
        try:
            photos = json.loads(photos_json)
            if not isinstance(photos, list):
                photos = [photos]
            
            saved_photos = []
            
            for i, photo_data in enumerate(photos):
                if not photo_data or not isinstance(photo_data, str):
                    continue
                
                # 去除 data:image/jpeg;base64, 前綴
                if "," in photo_data:
                    photo_data = photo_data.split(",")[1]
                
                # 解碼
                photo_bytes = base64.b64decode(photo_data)
                
                # 保存文件
                filename = f"order_{order_id}_{i}.jpg"
                filepath = os.path.join(UPLOAD_DIR, "images", filename)
                
                with open(filepath, "wb") as f:
                    f.write(photo_bytes)
                
                saved_photos.append(f"/uploads/images/{filename}")
                print(f"  訂單 {order_id}: 保存照片 {filename}")
            
            # 更新數據庫
            if saved_photos:
                cursor.execute(
                    "UPDATE orders SET completion_photos = ? WHERE id = ?",
                    (json.dumps(saved_photos), order_id)
                )
                
        except Exception as e:
            print(f"  訂單 {order_id} 處理失敗: {e}")
    
    conn.commit()
    conn.close()
    print("照片遷移完成！")


def extract_voice():
    """提取語音並保存為文件"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 獲取所有語音
    cursor.execute("SELECT id, voice_url FROM orders WHERE voice_url IS NOT NULL AND voice_url != ''")
    orders = cursor.fetchall()
    
    print(f"找到 {len(orders)} 個訂單需要處理語音...")
    
    for order_id, voice_data in orders:
        if not voice_data:
            continue
        
        # 跳過已經是文件路徑的
        if voice_data.startswith("/uploads/") or voice_data.startswith("http"):
            print(f"  訂單 {order_id}: 已是文件路徑，跳過")
            continue
        
        try:
            # 去除前綴
            voice_clean = voice_data
            if "," in voice_clean:
                voice_clean = voice_clean.split(",")[1]
            
            # 解碼
            voice_bytes = base64.b64decode(voice_clean)
            
            # 保存文件
            filename = f"order_{order_id}.webm"
            filepath = os.path.join(UPLOAD_DIR, "voice", filename)
            
            with open(filepath, "wb") as f:
                f.write(voice_bytes)
            
            # 更新數據庫
            cursor.execute(
                "UPDATE orders SET voice_url = ? WHERE id = ?",
                (f"/uploads/voice/{filename}", order_id)
            )
            print(f"  訂單 {order_id}: 保存語音 {filename}")
            
        except Exception as e:
            print(f"  訂單 {order_id} 處理失敗: {e}")
    
    conn.commit()
    conn.close()
    print("語音遷移完成！")


if __name__ == "__main__":
    print("=== 開始媒體文件遷移 ===\n")
    extract_completion_photos()
    print()
    extract_voice()
    print("\n=== 遷移完成 ===")
    print("\n文件已保存到:")
    print(f"  - {UPLOAD_DIR}/images/")
    print(f"  - {UPLOAD_DIR}/voice/")
    print("\nAPI 現在支持靜態文件訪問!")
