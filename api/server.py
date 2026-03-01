"""
清潔服務系統 API - 增強版
- 防止重複提交
- 後台驗證
- 查詢緩存
- 高並發搶單保護
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import sqlite3
import random
import ssl
import time
import hashlib
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any, Optional

from models.cleaning import Database, Property, Cleaner, Job, CleaningRepository


# ========== 緩存機制 ==========
class Cache:
    """簡單的內存緩存"""
    def __init__(self, ttl: int = 30):  # 默認30秒TTL
        self._cache: Dict[str, tuple] = {}
        self.ttl = ttl
    
    def get(self, key: str) -> Optional[Any]:
        if key in self._cache:
            value, timestamp = self._cache[key]
            if time.time() - timestamp < self.ttl:
                return value
            del self._cache[key]
        return None
    
    def set(self, key: str, value: Any):
        self._cache[key] = (value, time.time())
    
    def invalidate(self, key: str):
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        self._cache.clear()


# ========== 驗證工具 ==========
class Validator:
    """數據驗證工具"""
    
    @staticmethod
    def validate_property(data: dict) -> tuple:
        """驗證房源數據"""
        if not data.get("name"):
            return False, "房源名稱不能為空"
        if not data.get("address"):
            return False, "房源地址不能為空"
        return True, None
    
    @staticmethod
    def validate_order(data: dict) -> tuple:
        """驗證訂單數據"""
        if not data.get("property_id"):
            return False, "房源ID不能為空"
        if not data.get("checkout_time"):
            return False, "退房時間不能為空"
        price = data.get("price", 0)
        try:
            price = float(price)
            if price <= 0:
                return False, "價格必須大於0"
        except (ValueError, TypeError):
            return False, "價格格式錯誤"
        return True, None
    
    @staticmethod
    def validate_cleaner(data: dict) -> tuple:
        """驗證清潔工數據"""
        if not data.get("name"):
            return False, "姓名不能為空"
        if not data.get("phone"):
            return False, "電話不能為空"
        return True, None


# ========== Idempotency ==========
class IdempotencyChecker:
    """防止重複提交"""
    def __init__(self):
        self._keys: Dict[str, float] = {}
        self._window = 60  # 60秒內不重複處理
    
    def check(self, key: str) -> bool:
        """檢查是否已處理過"""
        now = time.time()
        if key in self._keys:
            if now - self._keys[key] < self._window:
                return False  # 已經處理過
        self._keys[key] = now
        return True
    
    def cleanup(self):
        """清理過期的key"""
        now = time.time()
        self._keys = {k: v for k, v in self._keys.items() if now - v < self._window}


class CleaningAPI:
    def __init__(self, db_path: str = "/home/nico/projects/cleaning_service/cleaning.db"):
        self.db = Database(db_path)
        self.repo = CleaningRepository(self.db)
        # 緩存實例
        self.cache = Cache(ttl=30)
        self.idempotency = IdempotencyChecker()
        self.validator = Validator()
    
    def handle_request(self, method: str, path: str, body: str = "") -> Dict[str, Any]:
        parsed = urlparse(path)
        path = parsed.path
        query = parse_qs(parsed.query)
        
        # 首頁
        if path == "/" or path == "/index.html":
            return {"static": "index.html"}
        
        # 静态页面
        if path in ["/host.html", "/cleaner.html", "/admin.html"]:
            return {"static": path.lstrip("/")}
        
        # CSS 文件
        if path.startswith("/css/"):
            return {"static": path.lstrip("/")}
        
        # ========== 統計 (帶緩存) ==========
        if path == "/api/stats":
            cache_key = "stats"
            cached = self.cache.get(cache_key)
            if cached:
                return cached
            stats = self.repo.get_stats()
            self.cache.set(cache_key, stats)
            return stats
        
        # Cleaner stats
        if path == "/api/cleaner/stats":
            if method == "GET":
                cleaner_id = query.get("cleaner_id", [None])[0]
                if cleaner_id:
                    return self.repo.get_cleaner_stats(int(cleaner_id))
            return {"error": "Missing cleaner_id"}
        
        # ========== 地址 geocoding ==========
        if path == "/api/geocode":
            if method == "GET":
                address = query.get("address", [""])[0]
                if address:
                    return self._geocode_address(address)
                return {"error": "Missing address"}
        
        # ========== 房源 ==========
        if path == "/api/properties":
            if method == "GET":
                status = query.get("status", ["active"])[0]
                return {"data": [self._property_to_dict(p) for p in self.repo.get_properties(status)]}
            elif method == "POST":
                return self._add_property(json.loads(body) if body else {})
        
        if path.startswith("/api/properties/"):
            try:
                prop_id = int(path.split("/")[-1])
            except ValueError:
                return {"error": "Invalid property ID", "code": 400}
            if method == "GET":
                prop = self.repo.get_property(prop_id)
                return {"data": self._property_to_dict(prop)} if prop else {"error": "Not found", "code": 404}
        
        # ========== 清點工 ==========
        if path == "/api/cleaners":
            if method == "GET":
                status = query.get("status", ["available"])[0]
                return {"data": [self._cleaner_to_dict(c) for c in self.repo.get_cleaners(status)]}
            elif method == "POST":
                return self._add_cleaner(json.loads(body) if body else {})
        
        # ========== 清點工 CRUD ==========
        if path.startswith("/api/cleaners/") and method == "GET":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    cleaner_id = int(parts[3])
                    return self._get_cleaner(cleaner_id)
                except ValueError:
                    return {"error": "Invalid cleaner ID", "code": 400}
        
        # ========== 房東 CRUD ==========
        if path == "/api/hosts/login":
            if method == "POST":
                return self._host_login(json.loads(body) if body else {})
        
        # 房東驗證碼登錄
        if path.startswith("/api/hosts/code/") and method == "GET":
            code = path.split("/")[-1]
            return self._host_login_by_code(code)
        
        if path == "/api/hosts":
            if method == "GET":
                return self._get_hosts()
            elif method == "POST":
                return self._add_host(json.loads(body) if body else {})
        
        if path.startswith("/api/hosts/") and method == "GET":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    host_id = int(parts[3])
                    return self._get_host(host_id)
                except ValueError:
                    return {"error": "Invalid host ID", "code": 400}
        
        if path.startswith("/api/hosts/") and method == "PUT":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    host_id = int(parts[3])
                    return self._update_host(host_id, json.loads(body) if body else {})
                except ValueError:
                    return {"error": "Invalid host ID", "code": 400}
        
        # ========== 房源 CRUD ==========
        if path == "/api/properties" and method == "POST":
            return self._add_property(json.loads(body) if body else {})
        
        if path.startswith("/api/properties/") and method == "PUT":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    prop_id = int(parts[3])
                    return self._update_property(prop_id, json.loads(body) if body else {})
                except ValueError:
                    return {"error": "Invalid property ID", "code": 400}
        
        if path.startswith("/api/properties/") and method == "DELETE":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    prop_id = int(parts[3])
                    return self._delete_property(prop_id)
                except ValueError:
                    return {"error": "Invalid property ID", "code": 400}
        
        if path.startswith("/api/hosts/") and method == "DELETE":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    host_id = int(parts[3])
                    return self._delete_host(host_id)
                except ValueError:
                    return {"error": "Invalid host ID", "code": 400}
        
        if path.startswith("/api/cleaners/") and method == "PUT":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    cleaner_id = int(parts[3])
                    return self._update_cleaner(cleaner_id, json.loads(body) if body else {})
                except ValueError:
                    return {"error": "Invalid cleaner ID", "code": 400}
        
        if path.startswith("/api/cleaners/") and method == "DELETE":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    cleaner_id = int(parts[3])
                    return self._delete_cleaner(cleaner_id)
                except ValueError:
                    return {"error": "Invalid cleaner ID", "code": 400}
        
        # ========== 訂單 ==========
        if path == "/api/orders":
            if method == "GET":
                status = query.get("status", [None])[0]
                return self._get_orders(status)
            elif method == "POST":
                return self._create_order(json.loads(body) if body else {})
        
        # 獲取單個訂單
        if path.startswith("/api/orders/") and not any(x in path for x in ["/verify-accept", "/complete", "/cancel"]):
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    order_id = int(parts[3])
                    if method == "GET":
                        conn = self.db._get_connection()
                        conn.row_factory = sqlite3.Row
                        cursor = conn.cursor()
                        cursor.execute("""
                            SELECT o.*, p.name as property_name, p.address as property_address,
                                   p.province as property_province, p.city as property_city,
                                   p.street as property_street, p.house_number as property_house_number
                            FROM orders o
                            LEFT JOIN properties p ON o.property_id = p.id
                            WHERE o.id = ?
                        """, (order_id,))
                        row = cursor.fetchone()
                        conn.close()
                        if row:
                            return {"data": dict(row)}
                        else:
                            return {"error": "Order not found", "code": 404}
                except:
                    pass
        
        # 驗證接單 code
        if path.startswith("/api/orders/") and path.endswith("/verify-accept"):
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    order_id = int(parts[3])
                    return self._verify_accept_order(order_id, json.loads(body) if body else {})
                except:
                    pass
        
        # 訂單 PUT/DELETE
        if path.startswith("/api/orders/") and method == "PUT":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    order_id = int(parts[3])
                    data = json.loads(body) if body else {}
                    print(f"PUT /orders/{order_id}, body keys: {list(data.keys())}")
                    return self._update_order(order_id, data)
                except Exception as e:
                    print(f"Error in PUT: {e}")
                    pass
        
        if path.startswith("/api/orders/") and method == "DELETE":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    order_id = int(parts[3])
                    return self._delete_order(order_id)
                except:
                    pass
        
        if path.startswith("/api/orders/"):
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    order_id = int(parts[3])
                    if method == "POST":
                        action = query.get("action", [None])[0]
                        if action == "complete":
                            return self._complete_order(order_id)
                        elif action == "cancel":
                            return self._cancel_order(order_id)
                except:
                    pass
        
        return {"error": "Not Found", "code": 404}
    
    def _geocode_address(self, address: str) -> Dict[str, Any]:
        """使用 Nominatim (OpenStreetMap) 進行地址解析"""
        import urllib.request
        import urllib.parse
        
        try:
            # 編碼地址
            encoded_addr = urllib.parse.quote(address)
            url = f"https://nominatim.openstreetmap.org/search?format=json&q={encoded_addr}&addressdetails=1"
            
            req = urllib.request.Request(url, headers={
                'User-Agent': 'CleaningService/1.0'
            })
            
            with urllib.request.urlopen(req, timeout=10) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            if not data:
                return {"error": "無法找到該地址", "code": 404}
            
            result = data[0]
            address_parts = result.get('address', {})
            
            # 解析地址組件
            province = address_parts.get('state', address_parts.get('province', ''))
            city = address_parts.get('city', address_parts.get('town', address_parts.get('village', '')))
            street = address_parts.get('road', '')
            house_number = address_parts.get('house_number', '')
            postcode = address_parts.get('postcode', '')
            
            return {
                "success": True,
                "formatted": result.get('display_name', ''),
                "province": province,
                "city": city,
                "street": street,
                "house_number": house_number,
                "postcode": postcode,
                "lat": result.get('lat', ''),
                "lon": result.get('lon', '')
            }
        except Exception as e:
            return {"error": str(e), "code": 500}
    
    def _property_to_dict(self, prop):
        if not prop:
            return {}
        return {
            "id": prop.id, "name": prop.name, "address": prop.address,
            "postal_code": getattr(prop, 'postal_code', ''),
            "bedrooms": prop.bedrooms, "bathrooms": prop.bathrooms,
            "floor": getattr(prop, 'floor', 0),
            "area": getattr(prop, 'area', 0),
            "province": getattr(prop, 'province', ''),
            "city": getattr(prop, 'city', ''),
            "street": getattr(prop, 'street', ''),
            "house_number": getattr(prop, 'house_number', ''),
            "host_phone": getattr(prop, 'host_phone', ''),
            "cleaning_time_minutes": prop.cleaning_time_minutes
        }
    
    def _cleaner_to_dict(self, cleaner):
        if not cleaner:
            return {}
        return {
            "id": cleaner.id, "name": cleaner.name, "phone": cleaner.phone,
            "status": cleaner.status, "rating": cleaner.rating, "total_jobs": cleaner.total_jobs,
            "code": getattr(cleaner, 'code', None)
        }
    
    def _add_cleaner(self, data):
        if not data.get("name"):
            return {"error": "name required", "code": 400}
        
        phone = data.get("phone", "")
        # 檢查電話是否已存在
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM cleaners WHERE phone = ?", (phone,))
        if cursor.fetchone():
            conn.close()
            return {"error": "電話號碼已存在", "code": 400}
        cursor.execute("SELECT id FROM hosts WHERE phone = ?", (phone,))
        if cursor.fetchone():
            conn.close()
            return {"error": "電話號碼已被房東使用", "code": 400}
        
        # 生成唯一驗證碼
        while True:
            code = str(random.randint(100000, 999999))
            cursor.execute("SELECT id FROM cleaners WHERE code = ?", (code,))
            if not cursor.fetchone():
                cursor.execute("SELECT id FROM hosts WHERE code = ?", (code,))
                if not cursor.fetchone():
                    break
        
        cleaner = Cleaner(name=data["name"], phone=phone, email=data.get("email", ""))
        cleaner_id = self.repo.add_cleaner(cleaner)
        
        # 更新 code
        cursor.execute("UPDATE cleaners SET code = ? WHERE id = ?", (code, cleaner_id))
        conn.commit()
        conn.close()
        
        return {"data": {"id": cleaner_id, "code": code}, "message": "Cleaner added with code"}
    
    def _get_cleaner(self, cleaner_id):
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cleaners WHERE id = ?", (cleaner_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"data": dict(row)}
        return {"error": "Not found", "code": 404}
    
    def _update_cleaner(self, cleaner_id, data):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        updates = []
        params = []
        if data.get("name"):
            updates.append("name = ?")
            params.append(data["name"])
        if data.get("phone"):
            updates.append("phone = ?")
            params.append(data["phone"])
        if data.get("status"):
            updates.append("status = ?")
            params.append(data["status"])
        
        if updates:
            params.append(cleaner_id)
            cursor.execute(f"UPDATE cleaners SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        conn.close()
        return {"message": "Cleaner updated"}
    
    def _delete_cleaner(self, cleaner_id):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cleaners WHERE id = ?", (cleaner_id,))
        conn.commit()
        conn.close()
        return {"message": "Cleaner deleted"}
    
    # ========== 房東 ==========
    def _get_hosts(self):
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hosts ORDER BY id")
        rows = cursor.fetchall()
        conn.close()
        return {"data": [dict(r) for r in rows]}
    
    def _host_login(self, data):
        phone = data.get("phone")
        if not phone:
            return {"error": "phone required", "code": 400}
        
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hosts WHERE phone = ?", (phone,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {"data": {"id": row["id"], "name": row["name"], "phone": row["phone"], "code": row["code"]}, "message": "Login success"}
        
        # 自动注册
        code = str(random.randint(100000, 999999))
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO hosts (name, phone, code) VALUES (?, ?, ?)", 
                       (data.get("name", "房東"), phone, code))
        host_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {"data": {"id": host_id, "code": code}, "message": "Registered"}
    
    def _host_login_by_code(self, code):
        if not code:
            return {"error": "code required", "code": 400}
        
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hosts WHERE code = ?", (code,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {"data": {"id": row["id"], "name": row["name"], "phone": row["phone"], "code": row["code"]}, "message": "Login success"}
        
        return {"error": "Invalid code", "code": 404}
    
    def _add_host(self, data):
        if not data.get("name") or not data.get("phone"):
            return {"error": "name and phone required", "code": 400}
        
        phone = data.get("phone")
        # 檢查電話是否已存在
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM hosts WHERE phone = ?", (phone,))
        if cursor.fetchone():
            conn.close()
            return {"error": "電話號碼已存在", "code": 400}
        cursor.execute("SELECT id FROM cleaners WHERE phone = ?", (phone,))
        if cursor.fetchone():
            conn.close()
            return {"error": "電話號碼已被清潔夥伴使用", "code": 400}
        
        # 生成唯一驗證碼
        while True:
            code = str(random.randint(100000, 999999))
            cursor.execute("SELECT id FROM cleaners WHERE code = ?", (code,))
            if not cursor.fetchone():
                cursor.execute("SELECT id FROM hosts WHERE code = ?", (code,))
                if not cursor.fetchone():
                    break
        
        cursor.execute("INSERT INTO hosts (name, phone, code) VALUES (?, ?, ?)", 
                     (data["name"], phone, code))
        host_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return {"data": {"id": host_id, "code": code}, "message": "Host added"}
    
    def _get_host(self, host_id):
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM hosts WHERE id = ?", (host_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            return {"data": dict(row)}
        return {"error": "Not found", "code": 404}
    
    def _update_host(self, host_id, data):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        updates = []
        params = []
        if data.get("name"):
            updates.append("name = ?")
            params.append(data["name"])
        if data.get("phone"):
            updates.append("phone = ?")
            params.append(data["phone"])
        
        if updates:
            params.append(host_id)
            cursor.execute(f"UPDATE hosts SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        conn.close()
        return {"message": "Host updated"}
    
    def _delete_host(self, host_id):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM hosts WHERE id = ?", (host_id,))
        conn.commit()
        conn.close()
        return {"message": "Host deleted"}
    
    # ========== 房源管理 ==========
    def _add_property(self, data):
        if not data.get("name") or not data.get("address"):
            return {"error": "name and address required", "code": 400}
        
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO properties (name, address, postal_code, bedrooms, bathrooms, floor, area, province, city, street, house_number, host_phone, cleaning_time_minutes, cleaning_checklist, notes)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (data.get("name"), data.get("address"), 
                      data.get("postal_code", ""),
                      data.get("bedrooms", 1), data.get("bathrooms", 1),
                      data.get("floor", 0), data.get("area", 0),
                      data.get("province", ""), data.get("city", ""),
                      data.get("street", ""), data.get("house_number", ""),
                      data.get("host_phone", ""),
                      data.get("cleaning_time_minutes", 120), 
                      data.get("cleaning_checklist", ""), data.get("notes", "")))
        prop_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {"data": {"id": prop_id}, "message": "Property added"}
    
    def _update_property(self, prop_id, data):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        updates = []
        params = []
        
        for field in ["name", "address", "postal_code", "bedrooms", "bathrooms", "floor", "area", 
                      "province", "city", "street", "house_number", "host_phone",
                      "cleaning_time_minutes", "cleaning_checklist", "notes"]:
            if data.get(field) is not None:
                updates.append(f"{field} = ?")
                params.append(data[field])
        
        if updates:
            params.append(prop_id)
            cursor.execute(f"UPDATE properties SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
        conn.close()
        return {"message": "Property updated"}
    
    def _delete_property(self, prop_id):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM properties WHERE id = ?", (prop_id,))
        conn.commit()
        conn.close()
        return {"message": "Property deleted"}
    
    def _get_orders(self, status=None):
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        query = """
            SELECT o.*, p.name as property_name, p.address as property_address,
                   p.province as property_province, p.city as property_city,
                   p.street as property_street, p.house_number as property_house_number,
                   c.name as cleaner_name
            FROM orders o
            LEFT JOIN properties p ON o.property_id = p.id
            LEFT JOIN cleaners c ON o.assigned_cleaner_id = c.id
            WHERE 1=1
        """
        params = []
        if status:
            query += " AND o.status = ?"
            params.append(status)
        
        query += " ORDER BY o.checkout_time ASC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return {"data": [dict(row) for row in rows]}
    
    def _create_order(self, data):
        # 驗證請求數據
        valid, error = self.validator.validate_order(data)
        if not valid:
            return {"error": error, "code": 400}
        
        # Idempotency key (可選)
        idempotency_key = data.get("_idempotency_key")
        if idempotency_key:
            if not self.idempotency.check(idempotency_key):
                return {"error": "Duplicate request", "code": 409}
        
        # 驗證房源存在
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM properties WHERE id = ?", (data.get("property_id"),))
        if not cursor.fetchone():
            conn.close()
            return {"error": "Property not found", "code": 404}
        
        
        cursor.execute("""
            INSERT INTO orders (property_id, host_name, host_phone, checkout_time, price, status, voice_url, text_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (data.get("property_id"), data.get("host_name", ""), data.get("host_phone", ""),
              data.get("checkout_time"), data.get("price", 100), "open", 
              data.get("voice_url"), data.get("text_notes")))
        
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # 清除緩存
        self.cache.clear()
        
        return {"data": {"id": order_id}, "message": "Order created"}
    
    def _verify_accept_order(self, order_id, data):
        """搶單邏輯 - 高並發保護"""
        cleaner_id = data.get("cleaner_id")
        code = data.get("code")
        
        # 參數驗證
        if not cleaner_id or not code:
            return {"error": "cleaner_id and code required", "code": 400}
        
        try:
            cleaner_id = int(cleaner_id)
        except ValueError:
            return {"error": "Invalid cleaner_id", "code": 400}
        
        # 驗證清潔工
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT code FROM cleaners WHERE id = ?", (cleaner_id,))
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return {"error": "Cleaner not found", "code": 404}
        
        if str(row["code"]) != str(code):
            return {"error": "Invalid code", "code": 400}
        
        # 高並發保護：使用鎖表實現互斥
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        # 嘗試獲取鎖（原子操作）
        cursor.execute("INSERT OR IGNORE INTO order_locks (order_id) VALUES (?)", (order_id,))
        if cursor.rowcount == 0:
            # 已經被鎖定
            conn.close()
            return {"error": "Order already being processed", "code": 409}
        
        try:
            # 檢查訂單狀態
            cursor.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
            row = cursor.fetchone()
            if not row:
                conn.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))
                conn.commit()
                conn.close()
                return {"error": "Order not found", "code": 404}
            
            if row[0] != 'open':
                conn.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))
                conn.commit()
                conn.close()
                return {"error": f"Order already taken (status: {row[0]})", "code": 409}
            
            # 執行搶單
            cursor.execute("""
                UPDATE orders 
                SET assigned_cleaner_id = ?, status = 'accepted', assigned_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'open'
            """, (cleaner_id, order_id))
            
            # 確認更新成功
            cursor.execute("SELECT status, assigned_cleaner_id FROM orders WHERE id = ?", (order_id,))
            result = cursor.fetchone()
            
            if result and result[0] == 'accepted' and result[1] == cleaner_id:
                conn.commit()
            else:
                conn.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))
                conn.commit()
                conn.close()
                return {"error": "Failed to grab order", "code": 409}
            
            # 釋放鎖
            conn.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))
            conn.commit()
        except Exception as e:
            conn.rollback()
            try:
                conn.execute("DELETE FROM order_locks WHERE order_id = ?", (order_id,))
                conn.commit()
            except:
                pass
            conn.close()
            return {"error": str(e), "code": 500}
        
        conn.close()
        
        # 清除緩存
        self.cache.clear()
        
        return {"message": "Order accepted", "verified": True}
    
    def _complete_order(self, order_id):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        return {"message": "Order completed"}
    
    def _update_order(self, order_id, data):
        
        # 驗證 status 值
        valid_statuses = ["open", "accepted", "arrived", "completed", "cancelled"]
        if data.get("status") and data["status"] not in valid_statuses:
            return {"error": f"Invalid status. Must be one of: {', '.join(valid_statuses)}", "code": 400}
        
        # 驗證 price
        if data.get("price"):
            try:
                price = float(data["price"])
                if price <= 0:
                    return {"error": "Price must be greater than 0", "code": 400}
            except (ValueError, TypeError):
                return {"error": "Invalid price", "code": 400}
        
        conn = self.db._get_connection()
        cursor = conn.cursor()
        updates = []
        params = []
        
        if data.get("property_id"):
            updates.append("property_id = ?")
            params.append(data["property_id"])
        
        if data.get("checkout_time"):
            updates.append("checkout_time = ?")
            params.append(data["checkout_time"])
        
        if data.get("price"):
            updates.append("price = ?")
            params.append(data["price"])
        
        if data.get("status"):
            updates.append("status = ?")
            params.append(data["status"])
        
        if data.get("cleaner_id"):
            updates.append("assigned_cleaner_id = ?")
            params.append(data["cleaner_id"])
        
        # voice_url 支持更新和刪除
        if "voice_url" in data:
            if data["voice_url"] is None:
                updates.append("voice_url = ?")
                params.append(None)
            elif data["voice_url"]:
                updates.append("voice_url = ?")
                params.append(data["voice_url"])
        
        # text_notes 支持更新
        if "text_notes" in data:
            updates.append("text_notes = ?")
            params.append(data["text_notes"])
        
        # completion_photos 支持更新
        if "completion_photos" in data:
            photos_str = data["completion_photos"]
            updates.append("completion_photos = ?")
            params.append(photos_str)
        
        # accepted_by_host 支持更新
        if "accepted_by_host" in data:
            updates.append("accepted_by_host = ?")
            params.append(data["accepted_by_host"])
        
        
        if updates:
            params.append(order_id)
            cursor.execute(f"UPDATE orders SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
            # 清除緩存
            self.cache.clear()
        
        conn.close()
        return {"message": "Order updated"}
    
    def _delete_order(self, order_id):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM orders WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        return {"message": "Order deleted"}
    
    def _cancel_order(self, order_id):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'cancelled' WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        return {"message": "Order cancelled"}


class APIHandler(BaseHTTPRequestHandler):
    api: CleaningAPI = None
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def do_GET(self):
        self._handle_request("GET")
    
    def do_POST(self):
        self._handle_request("POST")
    
    def do_PUT(self):
        self._handle_request("PUT")
    
    def do_DELETE(self):
        self._handle_request("DELETE")
    
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
    
    def _handle_request(self, method):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""
        
        result = self.api.handle_request(method, self.path, body)
        
        # 靜態文件
        if "static" in result:
            try:
                static_file = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    result["static"]
                )
                with open(static_file, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # MIME 類型檢測
                content_type = "text/html; charset=utf-8"
                if static_file.endswith(".css"):
                    content_type = "text/css; charset=utf-8"
                elif static_file.endswith(".js"):
                    content_type = "application/javascript; charset=utf-8"
                elif static_file.endswith(".json"):
                    content_type = "application/json; charset=utf-8"
                elif static_file.endswith(".png"):
                    content_type = "image/png"
                elif static_file.endswith(".jpg") or static_file.endswith(".jpeg"):
                    content_type = "image/jpeg"
                elif static_file.endswith(".svg"):
                    content_type = "image/svg+xml"
                
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.end_headers()
                self.wfile.write(content.encode("utf-8"))
                return
            except:
                pass
        
        self.send_response(200 if "error" not in result else result.get("code", 500))
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(result).encode("utf-8"))
    
    def log_message(self, format, *args):
        print(f"[API] {args[0]}")


def run_server(api, host="0.0.0.0", port=80):
    APIHandler.api = api
    server = HTTPServer((host, port), APIHandler)
    print(f"Running on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    api = CleaningAPI()
    run_server(api)
