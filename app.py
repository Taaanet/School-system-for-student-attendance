from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_cors import CORS
from flask_mail import Mail, Message
from datetime import datetime, timedelta
import os
import json
import pandas as pd
from functools import wraps
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
CORS(app)

# ============== إعدادات Google Sheets ==============
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
SHEET_NAME = "نظام حضور الطلاب"

def get_google_client():
    """الحصول على عميل Google Sheets"""
    try:
        creds_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        if creds_json:
            creds_dict = json.loads(creds_json)
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
            return gspread.authorize(creds)
        else:
            print("⚠️ لم يتم العثور على GOOGLE_CREDENTIALS_JSON في متغيرات البيئة")
            return None
    except Exception as e:
        print(f"خطأ في الاتصال بـ Google Sheets: {e}")
        return None

def get_or_create_sheet():
    """الحصول على ورقة العمل أو إنشاؤها"""
    client = get_google_client()
    if not client:
        return None, None
    
    try:
        sheet = client.open(SHEET_NAME)
    except:
        sheet = client.create(SHEET_NAME)
        print(f"✅ تم إنشاء ورقة جديدة: {SHEET_NAME}")
    
    # ورقة الطلاب
    try:
        students_ws = sheet.worksheet("الطلاب")
    except:
        students_ws = sheet.add_worksheet(title="الطلاب", rows="1000", cols="20")
        headers = ['student_id', 'name', 'grade', 'class', 'phone', 'parent_phone', 'notes']
        students_ws.append_row(headers)
    
    # ورقة الحضور
    try:
        attendance_ws = sheet.worksheet("الحضور")
    except:
        attendance_ws = sheet.add_worksheet(title="الحضور", rows="10000", cols="20")
        headers = ['student_id', 'student_name', 'grade', 'class', 'date', 'time', 'status', 'timestamp']
        attendance_ws.append_row(headers)
    
    return students_ws, attendance_ws

def load_students():
    """تحميل الطلاب من Google Sheets"""
    try:
        students_ws, _ = get_or_create_sheet()
        if not students_ws:
            return []
        records = students_ws.get_all_records()
        return records
    except Exception as e:
        print(f"خطأ في تحميل الطلاب: {e}")
        return []

def load_attendance():
    """تحميل سجلات الحضور من Google Sheets"""
    try:
        _, attendance_ws = get_or_create_sheet()
        if not attendance_ws:
            return []
        records = attendance_ws.get_all_records()
        for record in records:
            record['student_id'] = str(record.get('student_id', ''))
            record['student_name'] = record.get('student_name', '')
            record['grade'] = record.get('grade', '')
            record['class'] = record.get('class', '')
            record['date'] = record.get('date', '')
            record['time'] = record.get('time', '')
            record['status'] = record.get('status', '')
        return records
    except Exception as e:
        print(f"خطأ في تحميل الحضور: {e}")
        return []

def save_attendance(record):
    """حفظ سجل حضور جديد في Google Sheets"""
    try:
        _, attendance_ws = get_or_create_sheet()
        if not attendance_ws:
            return False
        
        attendance_ws.append_row([
            record['student_id'],
            record['student_name'],
            record['grade'],
            record['class'],
            record['date'],
            record['time'],
            record['status'],
            record['timestamp']
        ])
        return True
    except Exception as e:
        print(f"خطأ في حفظ الحضور: {e}")
        return False

def migrate_existing_attendance():
    """ترحيل سجلات الحضور القديمة من ملف JSON إلى Google Sheets"""
    try:
        if os.path.exists('attendance.json'):
            with open('attendance.json', 'r', encoding='utf-8') as f:
                old_records = json.load(f)
            count = 0
            for record in old_records:
                if save_attendance(record):
                    count += 1
            return count
        return 0
    except Exception as e:
        print(f"خطأ في الترحيل: {e}")
        return 0

# ============== إعدادات البريد الإلكتروني ==============
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'taaanet@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = 'taaanet@gmail.com'

mail = Mail(app)

# ============== إعدادات النظام ==============
ATTENDANCE_START = "07:00:00"
ATTENDANCE_DEADLINE = "07:30:00"

def get_attendance_status():
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    if current_time <= ATTENDANCE_DEADLINE:
        return "حاضر", current_time
    else:
        return "متأخر", current_time

# ============== دوال البريد الإلكتروني ==============
def send_report_email(recipient, subject, body, attachment_path=None):
    try:
        if not app.config['MAIL_PASSWORD']:
            return False, "كلمة مرور البريد الإلكتروني غير مضبوطة"
        
        msg = Message(subject, recipients=[recipient])
        msg.html = body
        
        if attachment_path and os.path.exists(attachment_path):
            with app.open_resource(attachment_path) as fp:
                msg.attach(
                    os.path.basename(attachment_path),
                    'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    fp.read()
                )
        
        mail.send(msg)
        return True, "تم الإرسال بنجاح"
    except Exception as e:
        return False, str(e)

# ============== بيانات المستخدمين ==============
USERS_FILE = 'users.json'

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    
    default_users = {
        'Taha_Mohamed': {
            'password': 'hetaonet0hros',
            'role': 'admin',
            'login_count': 0,
            'max_logins': None
        },
        'admin': {
            'password': 'admin123',
            'role': 'user',
            'login_count': 0,
            'max_logins': 5
        }
    }
    save_users(default_users)
    return default_users

def save_users(users):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ في حفظ المستخدمين: {e}")

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
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    
    users = load_users()
    users_data = []
    for username, data in users.items():
        users_data.append({
            'username': username,
            'role': data['role'],
            'login_count': data.get('login_count', 0),
            'max_logins': data.get('max_logins', 'غير محدود') if data['role'] == 'admin' else data.get('max_logins', 5),
            'remaining': get_remaining_logins(username)
        })
    
    return render_template('users_list.html', users=users_data)

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

@app.route("/reports")
@login_required
def reports():
    return render_template("reports.html")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

# ============== تحميل البيانات الأولية ==============
students = load_students()
attendance_records = load_attendance()

# ============== API التسجيل ==============
@app.route("/api/register", methods=["POST"])
@login_required
def register_attendance():
    global attendance_records
    
    try:
        data = request.get_json()
        student_id = str(data.get("student_id", "")).strip()
        
        if not student_id:
            return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب"})
        
        student = None
        for s in students:
            if s.get('student_id') == student_id:
                student = s
                break
        
        if not student:
            available_ids = [s.get('student_id') for s in students[:5]]
            return jsonify({"success": False, "message": f"الطالب {student_id} غير موجود. الأرقام المتاحة: {', '.join(available_ids)}"})
        
        status, current_time = get_attendance_status()
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        for record in attendance_records:
            if record.get('student_id') == student_id and record.get('date') == current_date:
                return jsonify({"success": False, "message": f"⚠️ {student.get('name')} مسجل مسبقاً اليوم"})
        
        new_record = {
            'student_id': student_id,
            'student_name': student.get('name'),
            'grade': student.get('grade'),
            'class': student.get('class'),
            'date': current_date,
            'time': current_time,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        
        if save_attendance(new_record):
            attendance_records.append(new_record)
            return jsonify({
                "success": True,
                "message": f"✅ تم تسجيل حضور {student.get('name')} - {status} الساعة {current_time}",
                "student_name": student.get('name'),
                "student_grade": student.get('grade'),
                "student_class": student.get('class'),
                "time": current_time,
                "date": current_date,
                "status": status
            })
        else:
            return jsonify({"success": False, "message": "فشل حفظ البيانات"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ============== API التقارير ==============
@app.route("/api/students_list")
@login_required
def students_list():
    return jsonify({"success": True, "data": students})

@app.route("/api/attendance_summary")
@login_required
def attendance_summary():
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(students)
    today_records = [r for r in attendance_records if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = total - (present + late)
    percentage = round((present + late) / total * 100, 1) if total > 0 else 0
    return jsonify({"success": True, "total_students": total, "present": present, "late": late, "absent": absent, "percentage": percentage, "date": today})

@app.route("/api/attendance_details/<date>")
@login_required
def attendance_details(date):
    result = []
    for student in students:
        record = None
        for r in attendance_records:
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
    return jsonify({"success": True, "data": result})

@app.route("/api/absent_students_today")
@login_required
def absent_students_today():
    today = datetime.now().strftime("%Y-%m-%d")
    present_ids = set(r.get('student_id') for r in attendance_records if r.get('date') == today)
    absent = [s for s in students if s.get('student_id') not in present_ids]
    return jsonify({"success": True, "data": absent})

@app.route("/api/top_students")
@login_required
def top_students():
    present_counts = {}
    for r in attendance_records:
        if r.get('status') == 'حاضر':
            name = r.get('student_name')
            present_counts[name] = present_counts.get(name, 0) + 1
    sorted_students = sorted(present_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    result = [{"name": name, "count": count} for name, count in sorted_students]
    return jsonify({"success": True, "data": result})

@app.route("/api/student_report/<student_id>")
@login_required
def student_report(student_id):
    student = None
    for s in students:
        if s.get('student_id') == student_id:
            student = s
            break
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})
    
    records = [r for r in attendance_records if r.get('student_id') == student_id]
    records.sort(key=lambda x: x.get('date', ''), reverse=True)
    present = len([r for r in records if r.get('status') == 'حاضر'])
    late = len([r for r in records if r.get('status') == 'متأخر'])
    total = len(records)
    return jsonify({
        "success": True, "student_name": student.get('name'), "student_id": student_id,
        "grade": student.get('grade'), "class": student.get('class'),
        "total_days": total, "present": present, "late": late, "absent": total - (present + late),
        "attendance_rate": round((present + late) / total * 100, 1) if total > 0 else 0,
        "records": records
    })

@app.route("/api/monthly_report")
@login_required
def monthly_report():
    year = int(request.args.get('year', datetime.now().year))
    month = int(request.args.get('month', datetime.now().month))
    
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    days_in_month = (next_month - datetime(year, month, 1)).days
    
    daily_stats = []
    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        day_records = [r for r in attendance_records if r.get('date') == date_str]
        daily_stats.append({
            'day': day, 'present': len([r for r in day_records if r.get('status') == 'حاضر']),
            'late': len([r for r in day_records if r.get('status') == 'متأخر']),
            'absent': len(students) - len(day_records)
        })
    return jsonify({"success": True, "daily_stats": daily_stats, "total_present": sum(d['present'] for d in daily_stats),
                   "total_late": sum(d['late'] for d in daily_stats), "days_in_month": days_in_month, "month": month, "year": year})

@app.route("/api/attendance_chart")
@login_required
def attendance_chart():
    today = datetime.now().strftime("%Y-%m-%d")
    today_records = [r for r in attendance_records if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = len(students) - (present + late)
    return jsonify({"success": True, "labels": ["حاضر", "متأخر", "غائب"], "data": [present, late, absent], "colors": ["#28a745", "#fd7e14", "#dc3545"]})

@app.route("/api/dashboard_stats")
@login_required
def dashboard_stats():
    today = datetime.now().strftime("%Y-%m-%d")
    today_records = [r for r in attendance_records if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    percentage = round((present + late) / len(students) * 100, 1) if len(students) > 0 else 0
    
    present_counts = {}
    for r in attendance_records:
        if r.get('status') == 'حاضر':
            name = r.get('student_name')
            present_counts[name] = present_counts.get(name, 0) + 1
    best_student = max(present_counts.items(), key=lambda x: x[1])[0] if present_counts else "لا يوجد"
    return jsonify({"success": True, "percentage": percentage, "present_today": present + late,
                   "total_students": len(students), "best_student": best_student, "total_records": len(attendance_records)})

# ============== APIs التصدير ==============
@app.route("/api/export_today_excel")
@login_required
def export_today_excel():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"attendance_report_{today}.xlsx"
        result = []
        for student in students:
            record = None
            for r in attendance_records:
                if r.get('student_id') == student.get('student_id') and r.get('date') == today:
                    record = r
                    break
            result.append({'رقم الطالب': student.get('student_id'), 'اسم الطالب': student.get('name'),
                          'الصف': student.get('grade'), 'الشعبة': student.get('class'),
                          'وقت التسجيل': record.get('time') if record else '-',
                          'الحالة': record.get('status') if record else 'غائب'})
        df = pd.DataFrame(result)
        df.to_excel(filename, index=False, engine='openpyxl')
        return send_file(filename, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_monthly_excel")
@login_required
def export_monthly_excel():
    try:
        year = request.args.get('year', datetime.now().year)
        month = request.args.get('month', datetime.now().month)
        filename = f"monthly_report_{year}_{month}.xlsx"
        monthly_stats = []
        for student in students:
            student_records = [r for r in attendance_records if r.get('student_id') == student.get('student_id')]
            present = len([r for r in student_records if r.get('status') == 'حاضر'])
            late = len([r for r in student_records if r.get('status') == 'متأخر'])
            monthly_stats.append({'رقم الطالب': student.get('student_id'), 'اسم الطالب': student.get('name'),
                                 'الصف': student.get('grade'), 'الشعبة': student.get('class'),
                                 'عدد أيام الحضور': present, 'عدد أيام التأخير': late,
                                 'الغياب': len(student_records) - (present + late),
                                 'نسبة الحضور': round((present + late) / len(student_records) * 100, 1) if len(student_records) > 0 else 0})
        df = pd.DataFrame(monthly_stats)
        df.to_excel(filename, index=False, engine='openpyxl')
        return send_file(filename, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_all_data")
@login_required
def export_all_data():
    try:
        if not attendance_records:
            return jsonify({"success": False, "message": "لا توجد بيانات"})
        filename = f"all_attendance_data_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"
        df = pd.DataFrame(attendance_records)
        df.to_excel(filename, index=False, engine='openpyxl')
        return send_file(filename, as_attachment=True)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ============== API إرسال البريد ==============
@app.route("/api/send_today_report_email")
@login_required
def send_today_report_email():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"attendance_report_{today}.xlsx"
        if not app.config['MAIL_PASSWORD']:
            return jsonify({"success": False, "message": "خدمة البريد الإلكتروني غير مضبوطة"})
        
        result = []
        for student in students:
            record = None
            for r in attendance_records:
                if r.get('student_id') == student.get('student_id') and r.get('date') == today:
                    record = r
                    break
            result.append({'رقم الطالب': student.get('student_id'), 'اسم الطالب': student.get('name'),
                          'الصف': student.get('grade'), 'الشعبة': student.get('class'),
                          'وقت التسجيل': record.get('time') if record else '-',
                          'الحالة': record.get('status') if record else 'غائب'})
        df = pd.DataFrame(result)
        df.to_excel(filename, index=False, engine='openpyxl')
        
        present_count = len([r for r in result if r['الحالة'] == 'حاضر'])
        late_count = len([r for r in result if r['الحالة'] == 'متأخر'])
        absent_count = len([r for r in result if r['الحالة'] == 'غائب'])
        
        html_body = f"""<html dir="rtl"><body><h2>📊 تقرير حضور الطلاب</h2><h3>التاريخ: {today}</h3><hr>
        <h3>📈 ملخص الحضور:</h3><ul><li>✅ الحاضرون: <strong>{present_count}</strong></li>
        <li>⏰ المتأخرون: <strong>{late_count}</strong></li><li>❌ الغائبون: <strong>{absent_count}</strong></li>
        <li>📚 إجمالي الطلاب: <strong>{len(result)}</strong></li></ul><hr><p>📎 المرفق: ملف Excel</p></body></html>"""
        
        success, msg = send_report_email('taaanet@gmail.com', f'تقرير حضور - {today}', html_body, filename)
        return jsonify({"success": success, "message": msg if not success else "✅ تم الإرسال"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ============== APIs إدارة البيانات ==============
@app.route("/api/upload_local_students")
@login_required
def upload_local_students():
    """رفع الطلاب من ملف Excel المحلي إلى Google Sheets"""
    try:
        if not os.path.exists('students.xlsx'):
            return jsonify({"success": False, "message": "ملف students.xlsx غير موجود"})
        
        df = pd.read_excel('students.xlsx')
        records = df.to_dict('records')
        
        students_ws, _ = get_or_create_sheet()
        if not students_ws:
            return jsonify({"success": False, "message": "فشل الاتصال بـ Google Sheets"})
        
        # مسح البيانات القديمة (مع ترك الصف الأول للعناوين)
        all_rows = students_ws.get_all_values()
        if len(all_rows) > 1:
            for i in range(len(all_rows) - 1, 0, -1):
                students_ws.delete_row(i + 1)
        
        # إضافة الطلاب الجدد
        count = 0
        for record in records:
            try:
                students_ws.append_row([
                    str(record.get('student_id', '')),
                    str(record.get('name', '')),
                    str(record.get('grade', '')),
                    str(record.get('class', '')),
                    str(record.get('phone', '')),
                    str(record.get('parent_phone', '')),
                    str(record.get('notes', ''))
                ])
                count += 1
            except Exception as e:
                print(f"خطأ في إضافة الطالب {record.get('student_id')}: {e}")
        
        global students
        students = load_students()
        
        return jsonify({"success": True, "message": f"✅ تم رفع {count} طالب بنجاح!", "total_students": len(students)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/migrate_to_gsheets")
@login_required
def migrate_to_gsheets():
    count = migrate_existing_attendance()
    global students, attendance_records
    students = load_students()
    attendance_records = load_attendance()
    return jsonify({"success": True, "message": f"تم ترحيل {count} سجل إلى Google Sheets"})

@app.route("/api/load_excel")
@login_required
def load_excel():
    global students
    students = load_students()
    return jsonify({"success": True, "message": f"تم تحميل {len(students)} طالب"})

@app.route("/api/clear_attendance")
@login_required
def clear_attendance():
    global attendance_records
    attendance_records = []
    return jsonify({"success": True, "message": "تم مسح سجلات الحضور"})

@app.route("/api/check_storage")
@login_required
def check_storage():
    return jsonify({
        "using_google_sheets": True,
        "attendance_count": len(attendance_records),
        "students_count": len(students),
        "sample_record": attendance_records[0] if attendance_records else None
    })

@app.route("/api/debug_students")
@login_required
def debug_students():
    return jsonify({"success": True, "count": len(students), "students": students[:10]})

@app.route("/api/stats")
@login_required
def stats():
    return jsonify({
        "success": True, 
        "students_count": len(students), 
        "attendance_count": len(attendance_records), 
        "storage": "google_sheets"
    })

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    print("🔄 جاري تحميل البيانات من Google Sheets...")
    students = load_students()
    attendance_records = load_attendance()
    print(f"📚 تم تحميل {len(students)} طالب و {len(attendance_records)} سجل حضور")
    
    if len(attendance_records) == 0:
        old_count = migrate_existing_attendance()
        if old_count > 0:
            attendance_records = load_attendance()
            print(f"✅ تم ترحيل {old_count} سجل قديم")
    
    print("=" * 50)
    print("🚀 نظام الحضور يعمل الآن مع Google Sheets!")
    print("=" * 50)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)