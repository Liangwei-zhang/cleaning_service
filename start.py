#!/usr/bin/env python3
"""短租清潔服務啟動腳本"""

import os
import signal
import subprocess
import sys
import time

def kill_old_process():
    """殺掉舊進程"""
    try:
        result = subprocess.run(['pkill', '-f', 'api/server.py'], 
                              capture_output=True, text=True)
    except:
        pass

def start_server():
    """啟動服務器"""
    os.chdir('/home/nico/projects/cleaning_service')
    
    # 添加路徑
    sys.path.insert(0, '.')
    
    from api.server import CleaningAPI, run_server
    
    print("🚀 啟動清潔服務系統...")
    api = CleaningAPI('cleaning.db')
    run_server(api, host='0.0.0.0', port=80)

if __name__ == '__main__':
    kill_old_process()
    time.sleep(1)
    start_server()
