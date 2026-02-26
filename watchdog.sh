#!/bin/bash
# 清潔服務監控腳本

PORT=5000
HOST="10.0.0.225"
LOG_FILE="/tmp/cleaning_watchdog.log"

check_service() {
    if curl -s --connect-timeout 2 http://$HOST:$PORT/api/stats > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

restart_service() {
    echo "$(date): Service down, restarting..." >> $LOG_FILE
    pkill -f "api.server.*CleaningAPI" 2>/dev/null
    sleep 1
    cd /home/nico/projects/cleaning_service
    nohup python3 -c "
import sys
sys.path.insert(0, '.')
from api.server import CleaningAPI, run_server
api = CleaningAPI('cleaning.db')
run_server(api, host='0.0.0.0', port=$PORT)
" >> $LOG_FILE 2>&1 &
    echo "$(date): Service restarted" >> $LOG_FILE
}

if ! check_service; then
    restart_service
fi
