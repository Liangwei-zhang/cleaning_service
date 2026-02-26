"""
清潔服務系統 API
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import sqlite3
import random
import ssl
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any

from models.cleaning import Database, Property, Cleaner, Job, CleaningRepository


class CleaningAPI:
    def __init__(self, db_path: str = "cleaning.db"):
        self.db = Database(db_path)
        self.repo = CleaningRepository(self.db)
    
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
        
        # ========== 統計 ==========
        if path == "/api/stats":
            return self.repo.get_stats()
        
        # ========== 房源 ==========
        if path == "/api/properties":
            if method == "GET":
                status = query.get("status", ["active"])[0]
                return {"data": [self._property_to_dict(p) for p in self.repo.get_properties(status)]}
            elif method == "POST":
                return self._add_property(json.loads(body) if body else {})
        
        if path.startswith("/api/properties/"):
            prop_id = int(path.split("/")[-1])
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
                except:
                    pass
        
        # ========== 房東 CRUD ==========
        if path == "/api/hosts/login":
            if method == "POST":
                return self._host_login(json.loads(body) if body else {})
        
        # 房東驗證碼登錄
        if path.startswith("/api/hosts/code/") and method == "GET":
            code = path.split("/")[-1]
            return self._host_login_by_code(code)
        
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
                except:
                    pass
        
        if path.startswith("/api/hosts/") and method == "PUT":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    host_id = int(parts[3])
                    return self._update_host(host_id, json.loads(body) if body else {})
                except:
                    pass
        
        # ========== 房源 CRUD ==========
        if path == "/api/properties" and method == "POST":
            return self._add_property(json.loads(body) if body else {})
        
        if path.startswith("/api/properties/") and method == "PUT":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    prop_id = int(parts[3])
                    return self._update_property(prop_id, json.loads(body) if body else {})
                except:
                    pass
        
        if path.startswith("/api/properties/") and method == "DELETE":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    prop_id = int(parts[3])
                    return self._delete_property(prop_id)
                except:
                    pass
        
        if path.startswith("/api/hosts/") and method == "DELETE":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    host_id = int(parts[3])
                    return self._delete_host(host_id)
                except:
                    pass
        
        if path.startswith("/api/cleaners/") and method == "PUT":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    cleaner_id = int(parts[3])
                    return self._update_cleaner(cleaner_id, json.loads(body) if body else {})
                except:
                    pass
        
        if path.startswith("/api/cleaners/") and method == "DELETE":
            parts = path.split("/")
            if len(parts) >= 4:
                try:
                    cleaner_id = int(parts[3])
                    return self._delete_cleaner(cleaner_id)
                except:
                    pass
        
        # ========== 訂單 ==========
        if path == "/api/orders":
            if method == "GET":
                status = query.get("status", [None])[0]
                return self._get_orders(status)
            elif method == "POST":
                return self._create_order(json.loads(body) if body else {})
        
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
                    return self._update_order(order_id, json.loads(body) if body else {})
                except:
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
    
    def _property_to_dict(self, prop):
        if not prop:
            return {}
        return {
            "id": prop.id, "name": prop.name, "address": prop.address,
            "bedrooms": prop.bedrooms, "bathrooms": prop.bathrooms,
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
    
    def _add_property(self, data):
        if not data.get("name") or not data.get("address"):
            return {"error": "name and address required", "code": 400}
        prop = Property(name=data["name"], address=data["address"],
                       bedrooms=data.get("bedrooms", 1), bathrooms=data.get("bathrooms", 1),
                       cleaning_time_minutes=data.get("cleaning_time_minutes", 120))
        prop_id = self.repo.add_property(prop)
        return {"data": {"id": prop_id}, "message": "Property added"}
    
    def _add_cleaner(self, data):
        if not data.get("name"):
            return {"error": "name required", "code": 400}
        
        code = str(random.randint(100000, 999999))
        
        cleaner = Cleaner(name=data["name"], phone=data.get("phone", ""), email=data.get("email", ""))
        cleaner_id = self.repo.add_cleaner(cleaner)
        
        # 更新 code
        conn = self.db._get_connection()
        cursor = conn.cursor()
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
        
        code = str(random.randint(100000, 999999))
        
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO hosts (name, phone, code) VALUES (?, ?, ?)", 
                     (data["name"], data["phone"], code))
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
        cursor.execute("""INSERT INTO properties (name, address, bedrooms, bathrooms, floor, area, cleaning_time_minutes, cleaning_checklist, notes)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                     (data.get("name"), data.get("address"), 
                      data.get("bedrooms", 1), data.get("bathrooms", 1),
                      data.get("floor", 0), data.get("area", 0),
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
        
        for field in ["name", "address", "bedrooms", "bathrooms", "floor", "area", "cleaning_time_minutes", "cleaning_checklist", "notes"]:
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
        if not data.get("property_id") or not data.get("checkout_time"):
            return {"error": "property_id and checkout_time required", "code": 400}
        
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO orders (property_id, host_name, host_phone, checkout_time, price, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (data.get("property_id"), data.get("host_name", ""), data.get("host_phone", ""),
              data.get("checkout_time"), data.get("price", 100), "open"))
        
        order_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return {"data": {"id": order_id}, "message": "Order created"}
    
    def _verify_accept_order(self, order_id, data):
        cleaner_id = data.get("cleaner_id")
        code = data.get("code")
        
        if not cleaner_id or not code:
            return {"error": "cleaner_id and code required", "code": 400}
        
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
        
        # 接單
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders SET assigned_cleaner_id = ?, status = 'accepted', assigned_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (cleaner_id, order_id))
        conn.commit()
        conn.close()
        
        return {"message": "Order accepted", "verified": True}
    
    def _complete_order(self, order_id):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE orders SET status = 'completed' WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        return {"message": "Order completed"}
    
    def _update_order(self, order_id, data):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        updates = []
        params = []
        if data.get("price"):
            updates.append("price = ?")
            params.append(data["price"])
        
        if updates:
            params.append(order_id)
            cursor.execute(f"UPDATE orders SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()
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
                
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
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


def run_server(api, host="0.0.0.0", port=8080):
    APIHandler.api = api
    server = HTTPServer((host, port), APIHandler)
    print(f"Running on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    api = CleaningAPI()
    run_server(api)
