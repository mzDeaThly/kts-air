# database.py
# ... (import statements) ...

# ... (DATA_DIR and DATABASE_NAME definitions) ...
import sqlite3 # <--- เพิ่มบรรทัดนี้
from datetime import date
import os
def init_db():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    # เพิ่ม 2 คอลัมน์ใหม่: location และ contact_phone
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id TEXT NOT NULL,
            task_details TEXT NOT NULL,
            work_date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            location TEXT,  -- เพิ่มคอลัมน์สถานที่
            contact_phone TEXT -- เพิ่มคอลัมน์เบอร์ติดต่อ
        )
    ''')
    conn.commit()
    conn.close()
    print("Database initialized successfully.")

# ปรับปรุงฟังก์ชัน add_schedule ให้รับพารามิเตอร์เพิ่ม
def add_schedule(team_id, task_details, work_date, start_time, end_time, location, contact_phone):
    """เพิ่มตารางงานใหม่ลงในฐานข้อมูล"""
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    # เพิ่ม field ใหม่ลงในคำสั่ง INSERT
    cursor.execute(
        "INSERT INTO schedules (team_id, task_details, work_date, start_time, end_time, location, contact_phone) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (team_id, task_details, work_date, start_time, end_time, location, contact_phone)
    )
    conn.commit()
    conn.close()

# ฟังก์ชัน get_today_schedules และ get_all_schedules ไม่ต้องแก้ไข
# เพราะใช้ SELECT * และ sqlite3.Row ซึ่งจะดึงคอลัมน์ใหม่มาให้เองอัตโนมัติ
# ... (ฟังก์ชันที่เหลือเหมือนเดิม) ...

if __name__ == '__main__':
    init_db()
