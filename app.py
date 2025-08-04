import os
from flask import Flask, request, abort, render_template, jsonify
from apscheduler.schedulers.background import BackgroundScheduler
from pytz import timezone
from datetime import datetime
from collections import defaultdict

from linebot.v3 import (
    WebhookHandler
)
from linebot.v3.exceptions import (
    InvalidSignatureError
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    TextMessage,
    TemplateMessage,
    ButtonsTemplate,
    PostbackAction
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    PostbackEvent
)

import database

# --- Basic Setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key_for_local_dev')

# --- Initialize Database ---
database.init_db()

# --- LINE Bot Setup ---
configuration = Configuration(access_token=os.environ.get('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.environ.get('LINE_CHANNEL_SECRET'))

# --- Configurations ---
# กำหนด ID และชื่อที่แสดงใน Dropdown
TEAM_NAMES = {
    'TEAM_A': 'ทีมช่างแอร์ 1',
    'TEAM_B': 'ทีมช่างแอร์ 2',
    'TEAM_C': 'ทีมช่างแอร์ 3',
}

# กำหนด ID และสีที่แสดงในปฏิทิน
TEAM_COLORS = {
    'TEAM_A': '#28a745',  # สีเขียว
    'TEAM_B': '#007bff',  # สีน้ำเงิน
    'TEAM_C': '#dc3545',  # สีแดง
}


# --- Scheduler for Automatic Notifications ---
def send_daily_schedules():
    """
    ส่งสรุปตารางงานประจำวันไปยังสมาชิกในแต่ละทีม
    โดยดึงรายชื่อผู้รับจาก Environment Variables
    """
    with app.app_context():
        print(f"[{datetime.now()}] Running daily schedule job...")
        schedules = database.get_today_schedules()
        if not schedules:
            print("No schedules for today.")
            return

        # 1. จัดกลุ่มงานตาม Team ID
        team_tasks = defaultdict(list)
        for schedule in schedules:
            team_tasks[schedule['team_id']].append(schedule)

        api_client = ApiClient(configuration)
        line_bot_api = MessagingApi(api_client)

        # 2. วนลูปส่งข้อความให้แต่ละทีม
        for team_id, tasks in team_tasks.items():
            print(f"Processing tasks for team: {team_id}")

            # 3. ดึงรายชื่อผู้รับ (User IDs) จาก Environment Variable
            env_key = f'LINE_USERS_{team_id}'
            recipients_str = os.environ.get(env_key, '')
            recipients = [uid.strip() for uid in recipients_str.split(',') if uid.strip()]

            if not recipients:
                print(f"No recipients found for team {team_id} (env var {env_key} is empty or not set). Skipping.")
                continue

            # 4. สร้างข้อความสรุปงานสำหรับทีมนั้นๆ
            team_display_name = TEAM_NAMES.get(team_id, team_id)
            tasks_details_list = []
            for task in tasks:
                task_detail_str = (
                    f"📄 งาน: {task['task_details']}\n"
                    f"⏰ เวลา: {task['start_time']} - {task['end_time']}\n"
                    f"📍 สถานที่: {task.get('location', '-')}\n"
                    f"📞 ติดต่อ: {task.get('contact_phone', '-')}"
                )
                tasks_details_list.append(task_detail_str)
            
            tasks_string = "\n--------------------\n".join(tasks_details_list)
            message_text = (
                f"📢 สรุปตารางงานสำหรับ {team_display_name} วันนี้!\n"
                f"--------------------\n"
                f"{tasks_string}"
            )

            summary_message = TextMessage(text=message_text)

            # 5. ส่งข้อความหาทุกคนในทีมด้วย multicast
            try:
                line_bot_api.multicast(
                    to=recipients,
                    messages=[summary_message]
                )
                print(f"Successfully sent schedule summary to {len(recipients)} members of team {team_id}.")
            except Exception as e:
                print(f"Error sending multicast to team {team_id}: {e}")


scheduler = BackgroundScheduler(timezone=timezone('Asia/Bangkok'))
scheduler.add_job(send_daily_schedules, 'cron', hour=7, minute=0)
scheduler.start()


# --- Web Dashboard ---
@app.route('/')
def dashboard():
    """Renders the calendar management page."""
    target_ids_str = os.environ.get('LINE_TARGET_IDS', '')
    target_ids = [item.strip() for item in target_ids_str.split(',') if item.strip()]
    
    # ส่ง Dictionary ทั้งหมดไปยังเทมเพลต
    return render_template('dashboard.html', target_ids=target_ids, team_names=TEAM_NAMES, team_colors=TEAM_COLORS)


# --- API Endpoints for Calendar ---
@app.route('/api/schedules', methods=['GET'])
def api_get_schedules():
    """API for FullCalendar to fetch all events."""
    schedules = database.get_all_schedules()
    events = []
    for schedule in schedules:
        team_id = schedule['team_id']
        team_display_name = TEAM_NAMES.get(team_id, team_id)
        color = TEAM_COLORS.get(team_id, '#6c757d') 
        
        events.append({
            'title': f"({team_display_name}) {schedule['task_details']}", # เพิ่มชื่อทีมในชื่องาน
            'start': f"{schedule['work_date']}T{schedule['start_time']}",
            'end': f"{schedule['work_date']}T{schedule['end_time']}",
            'color': color,
            'extendedProps': {
                'team_id': team_id,
                'details': schedule['task_details'],
                'location': schedule.get('location', '-'),
                'contact_phone': schedule.get('contact_phone', '-')
            }
        })
    return jsonify(events)

@app.route('/api/schedules', methods=['POST'])
def api_add_schedule():
    """API to save a new schedule from the calendar."""
    data = request.get_json()
    try:
        team_id = data['team_id']
        task_details = data['task_details']
        work_date = data['work_date']
        start_time = data['start_time']
        end_time = data['end_time']
        location = data.get('location', '')
        contact_phone = data.get('contact_phone', '')

        if not all([team_id, task_details, work_date, start_time, end_time]):
            return jsonify({'status': 'error', 'message': 'Missing required data'}), 400

        database.add_schedule(team_id, task_details, work_date, start_time, end_time, location, contact_phone)
        return jsonify({'status': 'success', 'message': 'Schedule added successfully'})
    except KeyError:
        return jsonify({'status': 'error', 'message': 'Invalid data format'}), 400
    except Exception as e:
        app.logger.error(f"Error adding schedule: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500


# --- LINE Webhook ---
@app.route("/callback", methods=['POST'])
def callback():
    """Endpoint where LINE sends data."""
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    """Handles messages sent to the bot."""
    user_id = event.source.user_id
    group_id = event.source.group_id if event.source.type == 'group' else None

    print(f"Received message from User ID: {user_id}")
    if group_id:
        print(f"Message is from Group ID: {group_id}")

    if event.message.text.lower() == "my id":
        reply_id = group_id if group_id else user_id
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                event.reply_token,
                messages=[TextMessage(text=f"This chat's ID is: {reply_id}")]
            )

@handler.add(PostbackEvent)
def handle_postback(event):
    """Handles postback events (e.g., button clicks)."""
    user_id = event.source.user_id
    if event.postback.data == 'action=confirm_schedule':
        print(f"User {user_id} confirmed the schedule.")
        reply_text = "รับทราบครับ! ✅"
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                event.reply_token,
                messages=[TextMessage(text=reply_text)]
            )


if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
