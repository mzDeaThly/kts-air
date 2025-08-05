import os
import psycopg2
import psycopg2.extras
from datetime import date

# ดึง URL สำหรับเชื่อมต่อฐานข้อมูลจาก Environment Variable
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """สร้างการเชื่อมต่อกับฐานข้อมูล PostgreSQL"""
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    """สร้างตาราง schedules หากยังไม่มี"""
    conn = get_db_connection()
    # ใช้ DictCursor เพื่อให้ผลลัพธ์เป็น Dictionary เหมือนเดิม
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute('''
            CREATE TABLE IF NOT EXISTS schedules (
                id SERIAL PRIMARY KEY,
                team_id TEXT NOT NULL,
                task_details TEXT NOT NULL,
                work_date DATE NOT NULL,
                start_time TIME NOT NULL,
                end_time TIME NOT NULL,
                location TEXT,
                contact_phone TEXT
            )
        ''')
    conn.commit()
    conn.close()
    print("PostgreSQL Database initialized successfully.")

def add_schedule(team_id, task_details, work_date, start_time, end_time, location, contact_phone):
    """เพิ่มตารางงานใหม่ลงในฐานข้อมูล"""
    conn = get_db_connection()
    with conn.cursor() as cur:
        cur.execute(
            # ใน psycopg2 เราใช้ %s เป็น placeholder แทน ?
            "INSERT INTO schedules (team_id, task_details, work_date, start_time, end_time, location, contact_phone) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (team_id, task_details, work_date, start_time, end_time, location, contact_phone)
        )
    conn.commit()
    conn.close()

def get_today_schedules():
    """ดึงตารางงานทั้งหมดของวันนี้"""
    today_str = date.today().strftime('%Y-%m-%d')
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM schedules WHERE work_date = %s", (today_str,))
        rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows

def get_all_schedules():
    """ดึงตารางงานทั้งหมด"""
    conn = get_db_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.execute("SELECT * FROM schedules ORDER BY work_date, start_time")
        rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows

if __name__ == '__main__':
    init_db()
