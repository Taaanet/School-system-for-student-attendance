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

# ============== دوال قراءة البيانات من Supabase ==============
def get_live_students():
    """قراءة الطلاب من Supabase"""
    try:
        print("🟢 جلب الطلاب من Supabase...")
        response = supabase.table("students").select("*").execute()
        print(f"🟢 تم جلب {len(response.data)} طالب")
        return response.data or []
    except Exception as e:
        print(f"❌ خطأ Supabase: {e}")
        return []

def get_live_attendance():
    """قراءة سجلات الحضور من Supabase"""
    try:
        print("🟢 جلب سجلات الحضور من Supabase...")
        result = supabase.table("attendance").select("*").execute()
        print(f"🟢 تم جلب {len(result.data)} سجل")
        return result.data or []
    except Exception as e:
        print(f"❌ خطأ قراءة الحضور: {e}")
        return []

def save_attendance(record):
    """حفظ سجل حضور في Supabase"""
    try:
        result = supabase.table("attendance").insert(record).execute()
        return True
    except Exception as e:
        print(f"❌ خطأ حفظ الحضور: {e}")
        return False

# ============== التوقيت السعودي ==============
def get_saudi_time():
    return datetime.utcnow() + timedelta(hours=3)

def is_weekend(date):
    """التحقق من أيام العطلات (الجمعة والسبت) - لم يتم تعديلها"""
    return date.weekday() == 4 or date.weekday() == 5

def is_within_daily_hours(current_time):
    """تم تعديلها: تسمح بالتسجيل 24 ساعة"""
    return True  # يمكن التسجيل في أي وقت 24 ساعة

def can_register_attendance():
    """التحقق من إمكانية التسجيل (أيام العطلات فقط محظورة)"""
    now = get_saudi_time()
    if is_weekend(now.date()):
        return False, "لا يمكن تسجيل الحضور في أيام العطلات (الجمعة والسبت)"
    return True, None  # باقي الأيام متاح التسجيل 24 ساعة

def get_attendance_status():
    """تحديد حالة الحضور حسب الوقت"""
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
        
        # التحقق من عدم التكرار مباشرة من قاعدة البيانات
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

# ============== API التقارير ==============
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

@app.route("/api/monthly_report")
@login_required
def monthly_report():
    year = int(request.args.get('year', get_saudi_time().year))
    month = int(request.args.get('month', get_saudi_time().month))
    students = get_live_students()
    attendance = get_live_attendance()
    
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    days = (next_month - datetime(year, month, 1)).days
    
    stats = []
    for day in range(1, days + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        day_records = [r for r in attendance if r.get('date') == date_str]
        stats.append({
            'day': day,
            'present': len([r for r in day_records if r.get('status') == 'حاضر في الوقت']),
            'late': len([r for r in day_records if r.get('status') == 'متأخر']),
            'absent': len(students) - len(day_records)
        })
    response = make_response(jsonify({"success": True, "daily_stats": stats}))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

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
        # محاولة قراءة CSV أولاً (أفضل للغة العربية)
        if os.path.exists("students.csv"):
            print("📖 جاري قراءة ملف students.csv...")
            df = pd.read_csv("students.csv", encoding='utf-8-sig')
        elif os.path.exists("students.xlsx"):
            print("📖 جاري قراءة ملف students.xlsx...")
            df = pd.read_excel("students.xlsx")
        else:
            return jsonify({
                "success": False,
                "message": "لا يوجد ملف students.csv أو students.xlsx"
            })

        print(f"📊 عدد الطلاب في الملف: {len(df)}")
        print(f"📋 الأعمدة الموجودة: {df.columns.tolist()}")

        # تنظيف البيانات
        df = df.fillna("")
        
        # تحويل جميع الأعمدة إلى نص
        for col in df.columns:
            df[col] = df[col].astype(str)
        
        # تنظيف أرقام الطلاب (إزالة .0)
        df['student_id'] = df['student_id'].str.replace('.0', '', regex=False).str.strip()
        
        # تنظيف أرقام الهواتف
        if 'phone' in df.columns:
            df['phone'] = df['phone'].str.replace('.0', '', regex=False).str.strip()
        if 'parent_phone' in df.columns:
            df['parent_phone'] = df['parent_phone'].str.replace('.0', '', regex=False).str.strip()
        
        records = df.to_dict("records")
        print(f"📊 تم تجهيز {len(records)} طالب للرفع")

        # حذف البيانات القديمة
        print("🗑️ جاري حذف البيانات القديمة...")
        supabase.table("students").delete().neq("student_id", "").execute()

        # إدخال البيانات الجديدة على دفعات (50 طالب لكل دفعة)
        print("📤 جاري رفع الطلاب إلى Supabase...")
        batch_size = 50
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            supabase.table("students").insert(batch).execute()
            print(f"  ✅ تم رفع {min(i+batch_size, len(records))}/{len(records)}")

        print(f"✅ تم رفع {len(records)} طالب بنجاح")
        return jsonify({
            "success": True,
            "message": f"تم رفع {len(records)} طالب إلى Supabase"
        })

    except Exception as e:
        print(f"❌ خطأ في الرفع: {e}")
        return jsonify({
            "success": False,
            "message": str(e)
        })

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
        return jsonify({
            "success": True,
            "total_rows": len(result.data),
            "sample_data": result.data
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        })

@app.route("/api/clear_attendance")
@login_required
def clear_attendance():
    try:
        supabase.table("attendance").delete().neq("student_id", "").execute()
        return jsonify({
            "success": True,
            "message": "تم مسح جميع سجلات الحضور"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e)
        })

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

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print("=" * 50)
    print("🚀 نظام الحضور يعمل الآن!")
    print("📊 قاعدة البيانات: Supabase")
    print("⏰ ساعات التسجيل: 24 ساعة (طوال اليوم)")
    print("📅 أيام العطلات: الجمعة والسبت فقط (لا يمكن التسجيل)")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=True)