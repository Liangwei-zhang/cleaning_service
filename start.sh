#!/bin/bash
# 清潔服務系統啟動腳本

cd "$(dirname "$0")"

# 殺掉舊進程
pkill -f "cleaning_service" 2>/dev/null
sleep 1

# 啟動服務
echo "🚀 啟動清潔服務系統..."
python3 -c "
import sys
sys.path.insert(0, '.')
from api.server import CleaningAPI, run_server

api = CleaningAPI('cleaning.db')
run_server(api, host='0.0.0.0', port=5000)
" &

sleep 2

# 檢查
if curl -s http://127.0.0.1:5000/api/stats > /dev/null 2>&1; then
    echo "✅ 服務啟動成功！"
    echo "   訪問地址: http://10.0.0.225:5000"
else
    echo "❌ 服務啟動失敗"
fi
