# app.py
# ... (imports) ...

# --- ส่วนของ Scheduler (ปรับปรุงการส่งข้อความ) ---
def send_daily_schedules():
    with app.app_context():
        # ... (ส่วนต้นของฟังก์ชันเหมือนเดิม) ...
        schedules = database.get_today_schedules()
        # ... (การจัดกลุ่ม team_tasks เหมือนเดิม) ...

        for team_id, tasks in team_tasks.items():
            try:
                tasks_details_list = []
                for task in tasks: # แก้ไขการวนลูปเพื่อเข้าถึง dictionary ของ task
                    task_detail_str = (
                        f"📄 งาน: {task['task_details']}\n"
                        f"⏰ เวลา: {task['start_time']} - {task['end_time']}\n"
                        f"📍 สถานที่: {task.get('location', '-')}\n" # ใช้ .get เผื่อข้อมูลเก่าไม่มี
                        f"📞 ติดต่อ: {task.get('contact_phone', '-')}"
                    )
                    tasks_details_list.append(task_detail_str)

                tasks_string = "\n--------------------\n".join(tasks_details_list)
                
                message_text = (
                    f"📢 สรุปตารางงานทั้งหมดสำหรับวันนี้!\n"
                    f"--------------------\n"
                    f"{tasks_string}"
                )
                # ... (การสร้างและส่ง TemplateMessage เหมือนเดิม) ...
            except Exception as e:
                print(f"Error sending to {team_id}: {e}")

# ... (Route '/' สำหรับ dashboard เหมือนเดิม) ...


# --- API Endpoints สำหรับ Calendar (ปรับปรุง) ---

@app.route('/api/schedules', methods=['GET'])
def api_get_schedules():
    schedules = database.get_all_schedules()
    events = []
    for schedule in schedules:
        events.append({
            'title': schedule['task_details'], # ทำให้หัวข้อสั้นลง
            'start': f"{schedule['work_date']}T{schedule['start_time']}",
            'end': f"{schedule['work_date']}T{schedule['end_time']}",
            # ใช้ extendedProps เพื่อเก็บข้อมูลเพิ่มเติมอย่างเป็นระบบ
            'extendedProps': {
                'team_id': schedule['team_id'],
                'details': schedule['task_details'],
                'location': schedule.get('location', '-'),
                'contact_phone': schedule.get('contact_phone', '-')
            }
        })
    return jsonify(events)

@app.route('/api/schedules', methods=['POST'])
def api_add_schedule():
    data = request.get_json()
    try:
        # ดึงข้อมูลใหม่จาก request
        team_id = data['team_id']
        task_details = data['task_details']
        work_date = data['work_date']
        start_time = data['start_time']
        end_time = data['end_time']
        location = data['location']
        contact_phone = data['contact_phone']

        # ส่งข้อมูลใหม่ไปยัง database function
        database.add_schedule(team_id, task_details, work_date, start_time, end_time, location, contact_phone)
        return jsonify({'status': 'success', 'message': 'Schedule added successfully'})
    # ... (ส่วน error handling เหมือนเดิม) ...