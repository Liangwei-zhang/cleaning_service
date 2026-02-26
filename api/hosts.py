"""Host API endpoints"""
import sqlite3
import random

def add_host_routes(api):
    """Add host-related routes to the API"""
    pass

# Host registration/login
def register_host(name, phone):
    conn = sqlite3.connect('cleaning.db')
    c = conn.cursor()
    
    # Check if exists
    c.execute("SELECT id, code FROM hosts WHERE phone = ?", (phone,))
    row = c.fetchone()
    
    if row:
        conn.close()
        return {"id": row[0], "code": row[1], "exists": True}
    
    # Create new
    code = str(random.randint(100000, 999999))
    c.execute("INSERT INTO hosts (name, phone, code) VALUES (?, ?, ?)", (name, phone, code))
    host_id = c.lastrowid
    conn.commit()
    conn.close()
    
    return {"id": host_id, "code": code, "exists": False}

def verify_host(phone, code):
    conn = sqlite3.connect('cleaning.db')
    c = conn.cursor()
    c.execute("SELECT id, name, code FROM hosts WHERE phone = ?", (phone,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return None
    
    if str(row[2]) == str(code):
        return {"id": row[0], "name": row[1]}
    
    return None
"""Host API endpoints"""
import sqlite3
import random

def get_all_hosts():
    conn = sqlite3.connect('cleaning.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM hosts ORDER BY id")
    rows = c.fetchall()
    conn.close()
    return [{"id": r["id"], "name": r["name"], "phone": r["phone"], "code": r["code"]} for r in rows]

def add_host(name, phone):
    conn = sqlite3.connect('cleaning.db')
    c = conn.cursor()
    code = str(random.randint(100000, 999999))
    c.execute("INSERT INTO hosts (name, phone, code) VALUES (?, ?, ?)", (name, phone, code))
    host_id = c.lastrowid
    conn.commit()
    conn.close()
    return {"id": host_id, "code": code}

def update_host(host_id, data):
    conn = sqlite3.connect('cleaning.db')
    c = conn.cursor()
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
        c.execute(f"UPDATE hosts SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()
    conn.close()
    return {"message": "Host updated"}

def delete_host(host_id):
    conn = sqlite3.connect('cleaning.db')
    c = conn.cursor()
    c.execute("DELETE FROM hosts WHERE id = ?", (host_id,))
    conn.commit()
    conn.close()
    return {"message": "Host deleted"}
