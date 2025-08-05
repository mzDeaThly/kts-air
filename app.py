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
    TextMessage
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
TEAM_NAMES = {
    'TEAM_A': 'ทีม A (ระบุชื่อสมาชิก เช่น กี้)',
    'TEAM_B': 'ทีม B (ระบุชือสมาชิก เช่น บี)',
}

TEAM_COLORS = {
    'TEAM_A': '#28a745',
    'TEAM_B': '#007bff',
}


# --- Main Notification Function ---
def send_daily_schedules():
    """
    ส่งสรุปตารางงานประจำวันไปยัง "แชทกลุ่ม" ของแต่ละทีม
    """
    with app.app_context():
        print(f"[{datetime.now()}] Running daily schedule job for groups...")
        schedules = database.get_today_schedules()
        if not schedules:
            print("No schedules for today.")
            return "No schedules for today."

        team_tasks = defaultdict(list)
        for schedule in schedules:
            team_tasks[schedule['team_id']].append(schedule)

        api_client = ApiClient(configuration)
        line_bot_api = MessagingApi(api_client)

        for team_id, tasks in team_tasks.items():
            print(f"Processing tasks for team: {team_id}")

            env_key = f'LINE_GROUP_{team_id}'
            target_group_id = os.environ.get(env_key)

            if not target_group_id:
                print(f"No Group ID found for team {team_id} (env var {env_key} is empty or not set). Skipping.")
                continue

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

            try:
                line_bot_api.push_message(
                    to=target_group_id,
                    messages=[summary_message]
                )
                print(f"Successfully sent schedule summary to group for team {team_id} (Group ID: {target_group_id}).")
            except Exception as e:
                print(f"Error sending push message to group {target_group_id}: {e}")
        
        return "Notification job completed."

# --- Scheduler Setup ---
scheduler = BackgroundScheduler(timezone=timezone('Asia/Bangkok'))
scheduler.add_job(send_daily_schedules, 'cron', hour=7, minute=0)
scheduler.start()
print("APScheduler has started successfully.")


# --- Web Dashboard ---
@app.route('/')
def dashboard():
    """Renders the calendar management page."""
    target_ids_str = os.environ.get('LINE_TARGET_IDS', '')
    target_ids = [item.strip() for item in target_ids_str.split(',') if item.strip()]
    return render_template('dashboard.html', target_ids=target_ids, team_names=TEAM_NAMES, team_colors=TEAM_COLORS)


# --- API & Webhook Endpoints ---
# (ส่วนนี้เหมือนเดิม ยกเว้น handle_message ที่ถูกแก้ไข และ /test/send_now ที่ถูกลบ)

# --- LINE Webhook ---
@app.route("/callback", methods=['POST'])
def callback():
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
    """
    จัดการข้อความที่ส่งมายังบอท
    - ตอบกลับ ID เมื่อพิมพ์ "my id"
    - สั่งรันการแจ้งเตือนเมื่อแอดมินพิมพ์ "/send_now"
    """
    text = event.message.text.lower()
    user_id = event.source.user_id
    reply_token = event.reply_token
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        # คำสั่งขอ ID
        if text == "my id":
            group_id = event.source.group_id if event.source.type == 'group' else None
            reply_id = group_id if group_id else user_id
            line_bot_api.reply_message_with_http_info(
                reply_token,
                messages=[TextMessage(text=f"This chat's ID is: {reply_id}")]
            )

        # คำสั่งทดสอบการส่งข้อมูลทันที
        elif text == "/send_now":
            # 1. อ่านรายชื่อแอดมินจาก Environment Variable
            admin_users_str = os.environ.get('LINE_ADMIN_USERS', '')
            admin_users = [uid.strip() for uid in admin_users_str.split(',') if uid.strip()]

            # 2. ตรวจสอบว่าผู้ใช้เป็นแอดมินหรือไม่
            if user_id in admin_users:
                # 3. ถ้าเป็นแอดมิน ให้ตอบกลับและสั่งรันฟังก์ชัน
                line_bot_api.reply_message_with_http_info(
                    reply_token,
                    messages=[TextMessage(text="✅ รับทราบ! กำลังสั่งให้ระบบส่งสรุปงานของวันนี้ทันที...")]
                )
                send_daily_schedules() # สั่งรันฟังก์ชัน
            else:
                # 4. ถ้าไม่ใช่แอดมิน ให้ตอบกลับว่าไม่มีสิทธิ์
                line_bot_api.reply_message_with_http_info(
                    reply_token,
                    messages=[TextMessage(text="❌ ขออภัย คุณไม่มีสิทธิ์ใช้คำสั่งนี้")]
                )

@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == 'action=confirm_schedule':
        print(f"User {user_id} confirmed the schedule.")
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                event.reply_token,
                messages=[TextMessage(text="รับทราบครับ! ✅")]
            )

# (ส่วนที่เหลือที่ไม่เกี่ยวข้องถูกลบไปเพื่อความกระชับ)
# ...
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
