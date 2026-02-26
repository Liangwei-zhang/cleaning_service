"""Cleaner Service Database Models"""
import sqlite3
from datetime import datetime
from typing import Optional, List

class Database:
    def __init__(self, db_path: str = "cleaning.db"):
        self.db_path = db_path
        self._init_db()
    
    def _get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Properties table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT NOT NULL,
                bedrooms INTEGER DEFAULT 1,
                bathrooms INTEGER DEFAULT 1,
                cleaning_time_minutes INTEGER DEFAULT 120,
                cleaning_checklist TEXT,
                notes TEXT,
                status VARCHAR(20) DEFAULT 'active',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Cleaners table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cleaners (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                phone TEXT,
                email TEXT,
                status VARCHAR(20) DEFAULT 'available',
                rating REAL DEFAULT 5.0,
                total_jobs INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                code TEXT
            )
        """)
        
        # Orders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_id INTEGER NOT NULL,
                cleaner_id INTEGER,
                host_name TEXT,
                host_phone TEXT,
                checkout_time TEXT NOT NULL,
                price REAL DEFAULT 100,
                status VARCHAR(20) DEFAULT 'open',
                assigned_cleaner_id INTEGER,
                assigned_at TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (property_id) REFERENCES properties(id)
            )
        """)
        
        conn.commit()
        conn.close()


class Property:
    def __init__(self, id=None, name="", address="", bedrooms=1, bathrooms=1, 
                 cleaning_time_minutes=120, cleaning_checklist="", notes="", status="active", created_at=None):
        self.id = id
        self.name = name
        self.address = address
        self.bedrooms = bedrooms
        self.bathrooms = bathrooms
        self.cleaning_time_minutes = cleaning_time_minutes
        self.cleaning_checklist = cleaning_checklist
        self.notes = notes
        self.status = status
        self.created_at = created_at


class Cleaner:
    def __init__(self, id=None, name="", phone="", email="", status="available", rating=5.0, total_jobs=0, created_at=None, code=None):
        self.id = id
        self.name = name
        self.phone = phone
        self.email = email
        self.status = status
        self.rating = rating
        self.total_jobs = total_jobs
        self.created_at = created_at
        self.code = code


class Job:
    def __init__(self, id=None, property_id=None, cleaner_id=None, 
                 checkin_time=None, checkout_time="", status="pending",
                 assigned_at=None, started_at=None, completed_at=None,
                 checklist="", photos="", notes="", rating=None):
        self.id = id
        self.property_id = property_id
        self.cleaner_id = cleaner_id
        self.checkin_time = checkin_time
        self.checkout_time = checkout_time
        self.status = status
        self.assigned_at = assigned_at
        self.started_at = started_at
        self.completed_at = completed_at
        self.checklist = checklist
        self.photos = photos
        self.notes = notes
        self.rating = rating


class CleaningRepository:
    def __init__(self, db: Database):
        self.db = db
    
    # Properties
    def add_property(self, prop: Property) -> int:
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO properties (name, address, bedrooms, bathrooms, cleaning_time_minutes, cleaning_checklist, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (prop.name, prop.address, prop.bedrooms, prop.bathrooms, 
              prop.cleaning_time_minutes, prop.cleaning_checklist, prop.notes))
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return job_id
    
    def get_properties(self, status="active") -> List[Property]:
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM properties WHERE status = ? ORDER BY name", (status,))
        rows = cursor.fetchall()
        conn.close()
        return [Property(**dict(row)) for row in rows]
    
    def get_property(self, prop_id: int) -> Optional[Property]:
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM properties WHERE id = ?", (prop_id,))
        row = cursor.fetchone()
        conn.close()
        return Property(**dict(row)) if row else None
    
    # Cleaners
    def add_cleaner(self, cleaner: Cleaner) -> int:
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO cleaners (name, phone, email)
            VALUES (?, ?, ?)
        """, (cleaner.name, cleaner.phone, cleaner.email))
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return job_id
    
    def get_cleaners(self, status="available") -> List[Cleaner]:
        conn = self.db._get_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cleaners WHERE status = ? ORDER BY rating DESC", (status,))
        rows = cursor.fetchall()
        conn.close()
        return [Cleaner(**dict(row)) for row in rows]
    
    def update_cleaner_status(self, cleaner_id: int, status: str):
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE cleaners SET status = ? WHERE id = ?", (status, cleaner_id))
        conn.commit()
        conn.close()
    
    # Orders
    def create_order(self, order) -> int:
        conn = self.db._get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO orders (property_id, checkout_time, price, status, host_name, host_phone)
            VALUES (?, ?, ?, 'open', ?, ?)
        """, (order.property_id, order.checkout_time, order.price, order.host_name, order.host_phone))
        job_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return job_id
    
    def get_orders(self, status=None) -> List[dict]:
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
        
        query += " ORDER BY o.checkout_time DESC"
        
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        return [dict(row) for row in rows]
    
    def get_stats(self) -> dict:
        conn = self.db._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM properties WHERE status = 'active'")
        properties = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM cleaners WHERE status = 'available'")
        available_cleaners = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'open'")
        pending_jobs = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'completed' AND DATE(created_at) = DATE('now')")
        completed_today = cursor.fetchone()[0]
        
        conn.close()
        return {
            "properties": properties,
            "available_cleaners": available_cleaners,
            "pending_jobs": pending_jobs,
            "completed_today": completed_today
        }
