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

# --- Team Colors Configuration ---
# กำหนดสีสำหรับแต่ละ Team ID ที่นี่
# คุณสามารถเพิ่ม ID และรหัสสี Hex ของคุณเองได้
TEAM_COLORS = {
    'C02c7a5214713a69111c1d1a641771960': '#28a745',  # สีเขียว
    'C11111111111111111111111111111111': '#007bff',  # สีน้ำเงิน
    'C22222222222222222222222222222222': '#dc3545',  # สีแดง
    'C33333333333333333333333333333333': '#ffc107', # สีเหลือง
    'C44444444444444444444444444444444': '#17a2b8', # สีฟ้าอมเขียว
}


# --- Scheduler for Automatic Notifications ---
def send_daily_schedules():
    """Function to be run daily at 7 AM to send schedule summaries."""
    with app.app_context():
        print(f"[{datetime.now()}] Running daily schedule job...")
        schedules = database.get_today_schedules()
        if not schedules:
            print("No schedules for today.")
            return

        team_tasks = defaultdict(list)
        for schedule in schedules:
            team_tasks[schedule['team_id']].append(schedule)

        api_client = ApiClient(configuration)
        line_bot_api = MessagingApi(api_client)

        for team_id, tasks in team_tasks.items():
            try:
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
                    f"📢 สรุปตารางงานทั้งหมดสำหรับวันนี้!\n"
                    f"--------------------\n"
                    f"{tasks_string}"
                )

                template_message = TemplateMessage(
                    alt_text='แจ้งเตือนตารางงาน',
                    template=ButtonsTemplate(
                        title='แจ้งเตือนตารางงาน',
                        text=message_text,
                        actions=[
                            PostbackAction(
                                label='โอเค 👍',
                                data='action=confirm_schedule'
                            )
                        ]
                    )
                )

                line_bot_api.push_message(team_id, messages=[template_message])
                print(f"Sent consolidated schedule to {team_id}")
            except Exception as e:
                print(f"Error sending to {team_id}: {e}")

scheduler = BackgroundScheduler(timezone=timezone('Asia/Bangkok'))
scheduler.add_job(send_daily_schedules, 'cron', hour=7, minute=0)
scheduler.start()


# --- Web Dashboard ---
@app.route('/')
def dashboard():
    """Renders the calendar management page."""
    target_ids_str = os.environ.get('LINE_TARGET_IDS', '')
    target_ids = [item.strip() for item in target_ids_str.split(',') if item.strip()]
    
    # ส่งลิสต์ของ ID และ Dictionary สี ไปยังเทมเพลต
    return render_template('dashboard.html', target_ids=target_ids, team_colors=TEAM_COLORS)


# --- API Endpoints for Calendar ---
@app.route('/api/schedules', methods=['GET'])
def api_get_schedules():
    """API for FullCalendar to fetch all events."""
    schedules = database.get_all_schedules()
    events = []
    for schedule in schedules:
        team_id = schedule['team_id']
        # ดึงสีจาก Dictionary ถ้าไม่เจอจะใช้สีเทาเป็นค่าเริ่มต้น
        color = TEAM_COLORS.get(team_id, '#6c757d') 
        
        events.append({
            'title': schedule['task_details'],
            'start': f"{schedule['work_date']}T{schedule['start_time']}",
            'end': f"{schedule['work_date']}T{schedule['end_time']}",
            'color': color,  # เพิ่ม Property สีสำหรับ FullCalendar
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
