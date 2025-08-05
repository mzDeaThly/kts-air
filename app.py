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
    ApiException  # <<< Import คลาสที่ถูกต้องจากที่นี่
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
    'TEAM_A': 'ช่างแอร์ ทีม A',
    'TEAM_B': 'ช่องแอร์ ทีม B',
}

TEAM_COLORS = {
    'TEAM_A': '#28a745',
    'TEAM_B': '#007bff',
}


# --- Main Notification Function ---
def send_daily_schedules():
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
            except ApiException as e:
                print(f"Error sending push message to group {target_group_id}: {e.body}")
        
        return "Notification job completed."

# --- Scheduler Setup ---
scheduler = BackgroundScheduler(timezone=timezone('Asia/Bangkok'))
scheduler.add_job(send_daily_schedules, 'cron', hour=7, minute=0)
scheduler.start()
print("APScheduler has started successfully.")


# --- Web Dashboard ---
@app.route('/')
def dashboard():
    target_ids_str = os.environ.get('LINE_TARGET_IDS', '')
    target_ids = [item.strip() for item in target_ids_str.split(',') if item.strip()]
    return render_template('dashboard.html', target_ids=target_ids, team_names=TEAM_NAMES, team_colors=TEAM_COLORS)


# --- API & Webhook Endpoints ---
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
    text = event.message.text.lower()
    user_id = event.source.user_id
    reply_token = event.reply_token
    
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        try:
            if text == "my id":
                group_id = event.source.group_id if event.source.type == 'group' else None
                reply_id = group_id if group_id else user_id
                line_bot_api.reply_message_with_http_info(
                    reply_token,
                    messages=[TextMessage(text=f"This chat's ID is: {reply_id}")]
                )

            elif text == "send_now":
                admin_users_str = os.environ.get('LINE_ADMIN_USERS', '')
                admin_users = [uid.strip() for uid in admin_users_str.split(',') if uid.strip()]

                if user_id in admin_users:
                    line_bot_api.reply_message_with_http_info(
                        reply_token,
                        messages=[TextMessage(text="✅ รับทราบ! กำลังสั่งให้ระบบส่งสรุปงานของวันนี้ทันที...")]
                    )
                    send_daily_schedules()
                else:
                    line_bot_api.reply_message_with_http_info(
                        reply_token,
                        messages=[TextMessage(text="❌ ขออภัย คุณไม่มีสิทธิ์ใช้คำสั่งนี้")]
                    )
        except ApiException as e: # <<< แก้ไขการดักจับ Error ให้ถูกต้อง
            app.logger.error(f"Error replying to message: {e.body}")
            print(f"Could not reply to user {user_id}. The reply token might be invalid or expired.")


@handler.add(PostbackEvent)
def handle_postback(event):
    user_id = event.source.user_id
    if event.postback.data == 'action=confirm_schedule':
        print(f"User {user_id} confirmed the schedule.")
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            try:
                line_bot_api.reply_message_with_http_info(
                    event.reply_token,
                    messages=[TextMessage(text="รับทราบครับ! ✅")]
                )
            except ApiException as e: # <<< แก้ไขการดักจับ Error ให้ถูกต้อง
                app.logger.error(f"Error replying to postback: {e.body}")
                print(f"Could not reply to user {user_id} on postback. The reply token was likely expired.")


@app.route('/api/schedules', methods=['GET'])
def api_get_schedules():
    schedules = database.get_all_schedules()
    events = []
    for schedule in schedules:
        team_id = schedule['team_id']
        team_display_name = TEAM_NAMES.get(team_id, team_id)
        color = TEAM_COLORS.get(team_id, '#6c757d') 
        
        events.append({
            'title': f"({team_display_name}) {schedule['task_details']}",
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
