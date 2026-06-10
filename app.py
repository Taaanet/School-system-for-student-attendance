from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file, make_response
from flask_cors import CORS
from flask_mail import Mail, Message
from datetime import datetime, timedelta, time
import os
import json
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv
from functools import wraps
from calendar import monthrange
import qrcode
from io import BytesIO
import base64
import threading
import time as time_module

load_dotenv()

app = Flask(__name__)

# ============== إعداد JSON للغة العربية ==============
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# ============== إعداد Supabase ==============
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("SUPABASE_URL أو SUPABASE_KEY غير موجودين في ملف .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
CORS(app)

# ============== إعدادات واتساب (Twilio) ==============
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', '')

if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        from twilio.rest import Client
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        twilio_enabled = True
    except:
        twilio_enabled = False
else:
    twilio_enabled = False

# ============== دعم اللغة الإنجليزية ==============
def get_language():
    return session.get('language', 'ar')

def set_language(lang):
    session['language'] = lang

# ============== دوال قراءة البيانات من Supabase ==============
def get_live_students():
    try:
        response = supabase.table("students").select("*").execute()
        return response.data or []
    except Exception as e:
        print(f"❌ خطأ Supabase: {e}")
        return []

def get_live_attendance():
    try:
        result = supabase.table("attendance").select("*").execute()
        return result.data or []
    except Exception as e:
        print(f"❌ خطأ قراءة الحضور: {e}")
        return []

def save_attendance(record):
    try:
        result = supabase.table("attendance").insert(record).execute()
        return True
    except Exception as e:
        print(f"❌ خطأ حفظ الحضور: {e}")
        return False

# ============== إرسال رسائل واتساب ==============
def send_whatsapp_message(to_number, student_name, status, attendance_time):
    try:
        if not twilio_enabled:
            return False, "خدمة واتساب غير مفعلة"
        
        message_body = f"""
🎓 *نظام حضور الطلاب*

👤 *الطالب:* {student_name}
✅ *الحالة:* {status}
⏰ *الوقت:* {attendance_time}
📅 *التاريخ:* {datetime.now().strftime('%Y-%m-%d')}

تم تسجيل حضور الطالب بنجاح.
"""
        message = twilio_client.messages.create(
            body=message_body,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{to_number}"
        )
        return True, "تم الإرسال"
    except Exception as e:
        print(f"❌ خطأ واتساب: {e}")
        return False, str(e)

# ============== إنشاء كود QR ==============
def generate_qr_code(student_id, student_name):
    attendance_url = f"https://school-system-for-student-attendance.onrender.com/scan?student_id={student_id}"
    
    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(attendance_url)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()
    
    return f"data:image/png;base64,{img_str}"

# ============== النسخ الاحتياطي التلقائي ==============
def create_backup():
    try:
        backup_dir = "backups"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        students = get_live_students()
        students_df = pd.DataFrame(students)
        students_df.to_excel(f"{backup_dir}/students_backup_{timestamp}.xlsx", index=False)
        
        attendance = get_live_attendance()
        attendance_df = pd.DataFrame(attendance)
        attendance_df.to_excel(f"{backup_dir}/attendance_backup_{timestamp}.xlsx", index=False)
        
        print(f"✅ تم إنشاء نسخة احتياطية في {timestamp}")
        return True, f"تم إنشاء النسخة {timestamp}"
    except Exception as e:
        print(f"❌ خطأ في النسخ الاحتياطي: {e}")
        return False, str(e)

def scheduled_backup():
    while True:
        time_module.sleep(86400)
        create_backup()

# ============== التوقيت السعودي ==============
def get_saudi_time():
    return datetime.utcnow() + timedelta(hours=3)

def is_weekend(date):
    return date.weekday() == 4 or date.weekday() == 5

def can_register_attendance():
    now = get_saudi_time()
    if is_weekend(now.date()):
        return False, "لا يمكن تسجيل الحضور في أيام العطلات (الجمعة والسبت)"
    return True, None

def get_attendance_status():
    now = get_saudi_time()
    current_time = now.strftime("%H:%M:%S")
    return ("حاضر في الوقت", current_time) if current_time <= "07:30:00" else ("متأخر", current_time)

# ============== البريد الإلكتروني ==============
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'taaanet@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = 'taaanet@gmail.com'

mail = Mail(app)

def send_report_email(recipient, subject, body, attachment_path=None):
    try:
        if not app.config['MAIL_PASSWORD']:
            return False, "كلمة مرور البريد غير مضبوطة"
        msg = Message(subject, recipients=[recipient])
        msg.html = body
        if attachment_path and os.path.exists(attachment_path):
            with app.open_resource(attachment_path) as fp:
                msg.attach(os.path.basename(attachment_path), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', fp.read())
        mail.send(msg)
        return True, "تم الإرسال"
    except Exception as e:
        return False, str(e)

# ============== إدارة المستخدمين ==============
USERS_FILE = 'users.json'

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    
    default_users = {
        'Taha_Mohamed': {'password': 'hetaonet0hros', 'role': 'admin', 'login_count': 0, 'max_logins': None},
        'admin': {'password': 'admin123', 'role': 'user', 'login_count': 0, 'max_logins': 5}
    }
    save_users(default_users)
    return default_users

def save_users(users):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ: {e}")

def can_login(username):
    users = load_users()
    if username not in users:
        return False, "اسم المستخدم غير موجود"
    user = users[username]
    if user['role'] == 'admin':
        return True, None
    if user['max_logins'] is not None and user['login_count'] >= user['max_logins']:
        return False, f"لقد تجاوزت الحد المسموح به ({user['max_logins']} مرات)"
    return True, None

def increment_login_count(username):
    users = load_users()
    if username in users and users[username]['role'] != 'admin':
        users[username]['login_count'] = users[username].get('login_count', 0) + 1
        save_users(users)

def get_remaining_logins(username):
    users = load_users()
    if username not in users:
        return 0
    user = users[username]
    if user['role'] == 'admin':
        return "غير محدود"
    max_logins = user.get('max_logins', 5)
    used = user.get('login_count', 0)
    return max(max_logins - used, 0)

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============== صفحات المصادقة ==============
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        users = load_users()
        if username in users and users[username]['password'] == password:
            can_login_flag, message = can_login(username)
            if not can_login_flag:
                return render_template('login.html', error=message)
            increment_login_count(username)
            session['logged_in'] = True
            session['username'] = username
            session['role'] = users[username]['role']
            session['remaining_logins'] = get_remaining_logins(username)
            return redirect(url_for('home'))
        return render_template('login.html', error="اسم المستخدم أو كلمة المرور غير صحيحة")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/users_list')
@login_required
def users_list():
    try:
        if session.get('role') != 'admin':
            return redirect(url_for('home'))
        
        users = load_users()
        users_data = []
        
        for username, data in users.items():
            # التحقق من وجود البيانات المطلوبة
            role = data.get('role', 'user')
            login_count = data.get('login_count', 0)
            max_logins = data.get('max_logins', 5)
            
            # حساب المتبقي
            if role == 'admin':
                remaining = "غير محدود"
                max_logins_display = "غير محدود"
            else:
                remaining = get_remaining_logins(username)
                max_logins_display = max_logins
            
            users_data.append({
                'username': username,
                'role': role,
                'login_count': login_count,
                'max_logins': max_logins_display,
                'remaining': remaining
            })
        
        return render_template('users_list.html', users=users_data)
    
    except Exception as e:
        print(f"❌ خطأ في صفحة المستخدمين: {e}")
        return f"<h1>خطأ في النظام</h1><p>الرجاء المحاولة لاحقاً</p><p>التفاصيل: {str(e)}</p>", 500

@app.route('/reset_logins/<username>')
@login_required
def reset_logins(username):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    users = load_users()
    if username in users:
        users[username]['login_count'] = 0
        save_users(users)
        return jsonify({"success": True, "message": f"تم إعادة تعيين {username}"})
    return jsonify({"success": False, "message": "المستخدم غير موجود"})

# ============== الصفحات الرئيسية ==============
@app.route("/")
@login_required
def home():
    return render_template("index.html")

@app.route("/scan")
@login_required
def scan():
    return render_template("scan.html")

@app.route("/general_reports")
@login_required
def general_reports():
    """التقارير العامة (يومي - بتاريخ - طالب)"""
    return render_template("general_reports.html")

@app.route("/monthly_reports")
@login_required
def monthly_reports_page():
    """التقارير الشهرية المتقدمة"""
    return render_template("monthly_reports.html")

@app.route("/charts")
@login_required
def charts_page():
    """الرسوم البيانية المتقدمة"""
    return render_template("charts.html")

@app.route("/class_reports")
@login_required
def class_reports():
    """تقارير الصف والفصل"""
    return render_template("class_reports.html")

@app.route("/qr_codes")
@login_required
def qr_codes_page():
    """أكواد QR للطلاب"""
    return render_template("qr_codes.html")

@app.route("/backup")
@login_required
def backup_page():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    return render_template("backup.html")

# ============== إعادة توجيه الصفحات القديمة ==============
@app.route("/reports")
@login_required
def reports_redirect():
    return redirect(url_for('general_reports'))

@app.route("/dashboard")
@login_required
def dashboard_redirect():
    return redirect(url_for('charts'))

@app.route("/reports_dashboard")
@login_required
def reports_dashboard_redirect():
    return redirect(url_for('general_reports'))

# ============== تبديل اللغة ==============
@app.route("/api/set_language/<lang>")
@login_required
def set_language_route(lang):
    if lang in ['ar', 'en']:
        session['language'] = lang
    return redirect(request.referrer or url_for('home'))

# ============== API تسجيل الحضور ==============
@app.route("/api/register", methods=["POST"])
@login_required
def register_attendance():
    try:
        can_register, error_message = can_register_attendance()
        if not can_register:
            return jsonify({"success": False, "message": error_message})
        
        data = request.get_json()
        student_id = str(data.get("student_id", "")).strip()
        
        if not student_id:
            return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب"})
        
        students = get_live_students()
        student = None
        for s in students:
            if str(s.get('student_id', '')) == student_id:
                student = s
                break
        
        if not student:
            return jsonify({"success": False, "message": f"الطالب {student_id} غير موجود"})
        
        status, current_time = get_attendance_status()
        now = get_saudi_time()
        current_date = now.strftime("%Y-%m-%d")
        
        existing = supabase.table("attendance").select("*").eq("student_id", student_id).eq("date", current_date).execute()
        
        if existing.data:
            return jsonify({
                "success": False,
                "message": f"⚠️ {student.get('name')} مسجل مسبقاً اليوم"
            })
        
        new_record = {
            'student_id': student_id,
            'student_name': str(student.get('name', '')),
            'grade': str(student.get('grade', '')),
            'class': str(student.get('class', '')),
            'date': current_date,
            'time': current_time,
            'status': status,
            'timestamp': now.isoformat()
        }
        
        if save_attendance(new_record):
            parent_phone = student.get('parent_phone', '')
            if parent_phone and len(parent_phone) > 5 and twilio_enabled:
                send_whatsapp_message(parent_phone, student.get('name', ''), status, current_time)
            
            return jsonify({
                "success": True,
                "message": f"✅ تم تسجيل حضور {student.get('name')} - {status} الساعة {current_time}",
                "student_name": str(student.get('name', '')),
                "student_grade": str(student.get('grade', '')),
                "student_class": str(student.get('class', '')),
                "time": current_time,
                "date": current_date,
                "status": status
            })
        else:
            return jsonify({"success": False, "message": "فشل حفظ البيانات"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ============== API أكواد QR ==============
@app.route("/api/student_qr/<student_id>")
@login_required
def student_qr(student_id):
    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})
    
    qr_code = generate_qr_code(student_id, student.get('name', ''))
    
    return jsonify({
        "success": True,
        "student_id": student_id,
        "student_name": student.get('name'),
        "qr_code": qr_code
    })

@app.route("/api/all_students_qr")
@login_required
def all_students_qr():
    students = get_live_students()
    qr_codes = []
    
    for student in students:
        qr_code = generate_qr_code(student.get('student_id'), student.get('name', ''))
        qr_codes.append({
            'student_id': student.get('student_id'),
            'student_name': student.get('name'),
            'qr_code': qr_code
        })
    
    return jsonify({"success": True, "data": qr_codes})

# ============== API النسخ الاحتياطي ==============
@app.route("/api/create_backup")
@login_required
def manual_backup():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    
    success, message = create_backup()
    return jsonify({"success": success, "message": message})

@app.route("/api/list_backups")
@login_required
def list_backups():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    
    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        return jsonify({"success": True, "backups": []})
    
    files = []
    for file in os.listdir(backup_dir):
        if file.endswith('.xlsx'):
            stat = os.stat(os.path.join(backup_dir, file))
            files.append({
                'name': file,
                'size': stat.st_size,
                'size_kb': round(stat.st_size / 1024, 2),
                'date': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })
    
    files.sort(key=lambda x: x['date'], reverse=True)
    return jsonify({"success": True, "backups": files})

@app.route("/api/download_backup/<filename>")
@login_required
def download_backup(filename):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    
    backup_path = os.path.join("backups", filename)
    if os.path.exists(backup_path):
        return send_file(backup_path, as_attachment=True)
    return jsonify({"success": False, "message": "الملف غير موجود"})

# ============== API الرسوم البيانية ==============
@app.route("/api/attendance_trend")
@login_required
def attendance_trend():
    year = int(request.args.get('year', get_saudi_time().year))
    attendance = get_live_attendance()
    
    def get_month_name(month):
        months = {1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل', 5: 'مايو', 6: 'يونيو',
                  7: 'يوليو', 8: 'أغسطس', 9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'}
        return months.get(month, str(month))
    
    monthly_data = []
    for month in range(1, 13):
        month_records = [r for r in attendance if r.get('date', '').startswith(f"{year}-{month:02d}")]
        present = len([r for r in month_records if r.get('status') == 'حاضر في الوقت'])
        late = len([r for r in month_records if r.get('status') == 'متأخر'])
        
        monthly_data.append({
            'month': get_month_name(month),
            'present': present,
            'late': late,
            'total': present + late
        })
    
    return jsonify({
        "success": True,
        "year": year,
        "data": monthly_data
    })

@app.route("/api/weekly_attendance")
@login_required
def weekly_attendance():
    attendance = get_live_attendance()
    weekdays = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']
    day_stats = {day: {'present': 0, 'late': 0, 'total': 0} for day in weekdays}
    
    for record in attendance:
        try:
            record_date = datetime.strptime(record.get('date', ''), "%Y-%m-%d")
            weekday = record_date.weekday()
            if weekday in [4, 5]:
                continue
            day_name = weekdays[weekday]
            if record.get('status') == 'حاضر في الوقت':
                day_stats[day_name]['present'] += 1
            elif record.get('status') == 'متأخر':
                day_stats[day_name]['late'] += 1
            day_stats[day_name]['total'] += 1
        except:
            pass
    
    result = []
    for day in weekdays:
        total = day_stats[day]['total']
        result.append({
            'day': day,
            'attendance_rate': round((day_stats[day]['present'] + day_stats[day]['late']) / max(total, 1) * 100, 2) if total > 0 else 0,
            'present': day_stats[day]['present'],
            'late': day_stats[day]['late']
        })
    
    return jsonify({"success": True, "data": result})

# ============== API التقارير الأساسية ==============
@app.route("/api/students_list")
@login_required
def students_list():
    students = get_live_students()
    response = make_response(jsonify({"success": True, "data": students}))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/attendance_summary")
@login_required
def attendance_summary():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()
    
    total = len(students)
    today_records = [r for r in attendance if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = total - (present + late)
    percentage = round((present + late) / total * 100, 1) if total > 0 else 0
    
    response = make_response(jsonify({
        "success": True,
        "total_students": total,
        "present": present,
        "late": late,
        "absent": absent if absent > 0 else 0,
        "percentage": percentage,
        "date": today
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/attendance_details/<date>")
@login_required
def attendance_details(date):
    students = get_live_students()
    attendance = get_live_attendance()
    
    result = []
    for student in students:
        record = None
        for r in attendance:
            if r.get('student_id') == student.get('student_id') and r.get('date') == date:
                record = r
                break
        result.append({
            'student_id': student.get('student_id'),
            'student_name': student.get('name'),
            'grade': student.get('grade'),
            'class': student.get('class'),
            'status': record.get('status') if record else 'غائب',
            'time': record.get('time') if record else '-'
        })
    response = make_response(jsonify({"success": True, "data": result}))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/absent_students_today")
@login_required
def absent_students_today():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()
    
    present_ids = set(r.get('student_id') for r in attendance if r.get('date') == today)
    absent = [s for s in students if s.get('student_id') not in present_ids]
    response = make_response(jsonify({"success": True, "data": absent, "count": len(absent), "date": today}))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/top_students")
@login_required
def top_students():
    attendance = get_live_attendance()
    counts = {}
    for r in attendance:
        if r.get('status') in ['حاضر في الوقت', 'متأخر']:
            name = r.get('student_name')
            counts[name] = counts.get(name, 0) + 1
    sorted_students = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
    response = make_response(jsonify({"success": True, "data": [{"name": n, "count": c} for n, c in sorted_students]}))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/student_report/<student_id>")
@login_required
def student_report(student_id):
    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})
    
    attendance = get_live_attendance()
    records = [r for r in attendance if r.get('student_id') == student_id]
    records.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    response = make_response(jsonify({
        "success": True,
        "student_name": student.get('name'),
        "student_id": student_id,
        "grade": student.get('grade'),
        "class": student.get('class'),
        "records": records
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

# ============== التقارير الشهرية ==============
@app.route("/api/monthly_report")
@login_required
def monthly_report():
    year = int(request.args.get('year', get_saudi_time().year))
    month = int(request.args.get('month', get_saudi_time().month))
    students = get_live_students()
    attendance = get_live_attendance()
    
    days_in_month = monthrange(year, month)[1]
    
    daily_stats = []
    total_present = 0
    total_late = 0
    total_absent = 0
    total_days_with_attendance = 0
    
    def get_month_name(month):
        months = {1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل', 5: 'مايو', 6: 'يونيو',
                  7: 'يوليو', 8: 'أغسطس', 9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'}
        return months.get(month, str(month))
    
    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        day_records = [r for r in attendance if r.get('date') == date_str]
        present = len([r for r in day_records if r.get('status') == 'حاضر في الوقت'])
        late = len([r for r in day_records if r.get('status') == 'متأخر'])
        absent = len(students) - (present + late)
        
        total_present += present
        total_late += late
        total_absent += absent
        
        if present + late > 0:
            total_days_with_attendance += 1
        
        daily_stats.append({
            'day': day,
            'date': date_str,
            'present': present,
            'late': late,
            'absent': absent if absent > 0 else 0,
            'percentage': round((present + late) / len(students) * 100, 2) if len(students) > 0 else 0
        })
    
    avg_attendance = round((total_present + total_late) / (days_in_month * len(students)) * 100, 2) if len(students) > 0 else 0
    
    if request.args.get('export') == 'excel':
        df = pd.DataFrame(daily_stats)
        filename = f"monthly_report_{year}_{month}.xlsx"
        df.to_excel(filename, index=False, engine='openpyxl')
        return send_file(filename, as_attachment=True)
    
    response = make_response(jsonify({
        "success": True,
        "year": year,
        "month": month,
        "month_name": get_month_name(month),
        "days_in_month": days_in_month,
        "total_students": len(students),
        "summary": {
            "total_present": total_present,
            "total_late": total_late,
            "total_absent": total_absent,
            "avg_attendance_rate": avg_attendance,
            "days_with_attendance": total_days_with_attendance,
            "best_day": max(daily_stats, key=lambda x: x['present'] + x['late']) if daily_stats else None,
            "worst_day": min(daily_stats, key=lambda x: x['present'] + x['late']) if daily_stats else None
        },
        "daily_stats": daily_stats
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/student_monthly_report/<student_id>")
@login_required
def student_monthly_report(student_id):
    year = int(request.args.get('year', get_saudi_time().year))
    month = int(request.args.get('month', get_saudi_time().month))
    
    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})
    
    days_in_month = monthrange(year, month)[1]
    attendance = get_live_attendance()
    student_records = [r for r in attendance if r.get('student_id') == student_id]
    
    daily_status = []
    present_count = 0
    late_count = 0
    
    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        record = next((r for r in student_records if r.get('date') == date_str), None)
        
        if record:
            if record.get('status') == 'حاضر في الوقت':
                present_count += 1
            elif record.get('status') == 'متأخر':
                late_count += 1
        
        daily_status.append({
            'day': day,
            'date': date_str,
            'status': record.get('status') if record else 'غائب',
            'time': record.get('time') if record else '-'
        })
    
    absent_count = days_in_month - (present_count + late_count)
    attendance_rate = round((present_count + late_count) / days_in_month * 100, 2)
    
    if request.args.get('export') == 'excel':
        df = pd.DataFrame(daily_status)
        filename = f"student_{student_id}_{year}_{month}.xlsx"
        df.to_excel(filename, index=False, engine='openpyxl')
        return send_file(filename, as_attachment=True)
    
    response = make_response(jsonify({
        "success": True,
        "student_id": student_id,
        "student_name": student.get('name'),
        "grade": student.get('grade'),
        "class": student.get('class'),
        "year": year,
        "month": month,
        "month_name": get_month_name(month),
        "days_in_month": days_in_month,
        "summary": {
            "present": present_count,
            "late": late_count,
            "absent": absent_count,
            "attendance_rate": attendance_rate
        },
        "daily_status": daily_status
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/comparative_monthly_report")
@login_required
def comparative_monthly_report():
    year = int(request.args.get('year', get_saudi_time().year))
    months = request.args.get('months', '1,2,3,4,5,6,7,8,9,10,11,12')
    months = [int(m) for m in months.split(',')]
    
    students = get_live_students()
    attendance = get_live_attendance()
    
    def get_month_name(month):
        months = {1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل', 5: 'مايو', 6: 'يونيو',
                  7: 'يوليو', 8: 'أغسطس', 9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'}
        return months.get(month, str(month))
    
    monthly_summary = []
    for month in months:
        days_in_month = monthrange(year, month)[1]
        month_records = [r for r in attendance if r.get('date', '').startswith(f"{year}-{month:02d}")]
        
        present = len([r for r in month_records if r.get('status') == 'حاضر في الوقت'])
        late = len([r for r in month_records if r.get('status') == 'متأخر'])
        expected = days_in_month * len(students)
        
        monthly_summary.append({
            'month': month,
            'month_name': get_month_name(month),
            'present': present,
            'late': late,
            'total_attendance': present + late,
            'expected': expected,
            'attendance_rate': round((present + late) / expected * 100, 2) if expected > 0 else 0
        })
    
    response = make_response(jsonify({
        "success": True,
        "year": year,
        "total_students": len(students),
        "monthly_summary": monthly_summary
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

# ============== API التقارير الأخرى ==============
@app.route("/api/attendance_chart")
@login_required
def attendance_chart():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()
    
    today_records = [r for r in attendance if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = len(students) - (present + late)
    response = make_response(jsonify({
        "success": True,
        "labels": ["حاضر في الوقت", "متأخر", "غائب"],
        "data": [present, late, absent],
        "colors": ["#28a745", "#fd7e14", "#dc3545"]
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/dashboard_stats")
@login_required
def dashboard_stats():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()
    
    total = len(students)
    today_records = [r for r in attendance if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = total - (present + late)
    percentage = round((present + late) / total * 100, 1) if total > 0 else 0
    
    response = make_response(jsonify({
        "success": True,
        "percentage": percentage,
        "present_today": present + late,
        "present": present,
        "late": late,
        "absent": absent,
        "total_students": total,
        "total_records": len(attendance)
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

# ============== APIs التصدير ==============
@app.route("/api/export_today_excel")
@login_required
def export_today_excel():
    today = get_saudi_time().strftime("%Y-%m-%d")
    filename = f"attendance_{today}.xlsx"
    students = get_live_students()
    attendance = get_live_attendance()
    
    result = []
    for student in students:
        record = None
        for r in attendance:
            if r.get('student_id') == student.get('student_id') and r.get('date') == today:
                record = r
                break
        result.append({
            'رقم الطالب': student.get('student_id'),
            'اسم الطالب': student.get('name'),
            'الصف': student.get('grade'),
            'الشعبة': student.get('class'),
            'وقت التسجيل': record.get('time') if record else '-',
            'الحالة': record.get('status') if record else 'غائب'
        })
    df = pd.DataFrame(result)
    df.to_excel(filename, index=False, engine='openpyxl')
    return send_file(filename, as_attachment=True)

@app.route("/api/export_attendance/<date>")
@login_required
def export_attendance(date):
    filename = f"attendance_{date}.xlsx"
    students = get_live_students()
    attendance = get_live_attendance()
    
    result = []
    for student in students:
        record = None
        for r in attendance:
            if r.get('student_id') == student.get('student_id') and r.get('date') == date:
                record = r
                break
        result.append({
            'رقم الطالب': student.get('student_id'),
            'اسم الطالب': student.get('name'),
            'الصف': student.get('grade'),
            'الشعبة': student.get('class'),
            'وقت التسجيل': record.get('time') if record else '-',
            'الحالة': record.get('status') if record else 'غائب'
        })
    df = pd.DataFrame(result)
    df.to_excel(filename, index=False, engine='openpyxl')
    return send_file(filename, as_attachment=True)

@app.route("/api/export_student_excel/<student_id>")
@login_required
def export_student_excel(student_id):
    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})
    
    attendance = get_live_attendance()
    records = [r for r in attendance if r.get('student_id') == student_id]
    records.sort(key=lambda x: x.get('date', ''), reverse=True)
    
    filename = f"student_{student_id}_report.xlsx"
    df = pd.DataFrame(records)
    df.to_excel(filename, index=False, engine='openpyxl')
    return send_file(filename, as_attachment=True)

# ============== APIs إدارة البيانات ==============
@app.route("/api/upload_local_students")
@login_required
def upload_local_students():
    try:
        if os.path.exists("students.csv"):
            df = pd.read_csv("students.csv", encoding='utf-8-sig')
        elif os.path.exists("students.xlsx"):
            df = pd.read_excel("students.xlsx")
        else:
            return jsonify({"success": False, "message": "لا يوجد ملف students.csv أو students.xlsx"})

        df = df.fillna("")
        for col in df.columns:
            df[col] = df[col].astype(str)
        
        df['student_id'] = df['student_id'].str.replace('.0', '', regex=False).str.strip()
        records = df.to_dict("records")

        supabase.table("students").delete().neq("student_id", "").execute()

        batch_size = 50
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            supabase.table("students").insert(batch).execute()

        return jsonify({"success": True, "message": f"تم رفع {len(records)} طالب إلى Supabase"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/refresh_all")
@login_required
def refresh_all():
    students = get_live_students()
    attendance = get_live_attendance()
    return jsonify({
        "success": True,
        "students_count": len(students),
        "attendance_count": len(attendance)
    })

@app.route("/api/direct_test")
@login_required
def direct_test():
    try:
        result = supabase.table("attendance").select("*").limit(10).execute()
        return jsonify({"success": True, "total_rows": len(result.data), "sample_data": result.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/clear_attendance")
@login_required
def clear_attendance():
    try:
        supabase.table("attendance").delete().neq("student_id", "").execute()
        return jsonify({"success": True, "message": "تم مسح جميع سجلات الحضور"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/stats")
@login_required
def stats():
    students = get_live_students()
    attendance = get_live_attendance()
    return jsonify({
        "success": True,
        "students_count": len(students),
        "attendance_count": len(attendance),
        "storage": "supabase"
    })

@app.route("/api/saudi_time")
@login_required
def saudi_time():
    now = get_saudi_time()
    return jsonify({
        "success": True,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "is_weekend": is_weekend(now.date()),
        "can_register": can_register_attendance()[0]
    })

@app.route("/test_supabase")
def test_supabase():
    try:
        result = supabase.table("students").select("*").execute()
        return {"success": True, "rows": len(result.data)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route("/test_attendance")
def test_attendance():
    try:
        result = supabase.table("attendance").select("*").execute()
        return {"success": True, "rows": len(result.data), "sample": result.data[:3]}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route("/health")
def health():
    return {"status": "ok", "database": "supabase"}

# تشغيل النسخ الاحتياطي التلقائي في الخلفية
backup_thread = threading.Thread(target=scheduled_backup, daemon=True)
backup_thread.start()

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print("=" * 60)
    print("🚀 نظام الحضور يعمل الآن!")
    print("📊 قاعدة البيانات: Supabase")
    print("⏰ ساعات التسجيل: 24 ساعة (طوال اليوم)")
    print("📅 أيام العطلات: الجمعة والسبت فقط")
    print("")
    print("📱 الصفحات المتاحة:")
    print("   🏠 الرئيسية: /")
    print("   📱 تسجيل الحضور: /scan")
    print("   📊 التقارير العامة: /general_reports")
    print("   📅 التقارير الشهرية: /monthly_reports")
    print("   📈 الرسوم البيانية: /charts")
    print("   📋 تقارير الصف والفصل: /class_reports")
    print("   📱 أكواد QR: /qr_codes")
    print("   💾 النسخ الاحتياطي: /backup")
    print("   👥 المستخدمين: /users_list")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)