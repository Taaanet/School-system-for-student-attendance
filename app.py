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
    """التحقق من أيام العطلات (الجمعة والسبت)"""
    return date.weekday() == 4 or date.weekday() == 5

def is_within_daily_hours(current_time):
    """تم تعديلها: تسمح بالتسجيل 24 ساعة"""
    return True

def can_register_attendance():
    """التحقق من إمكانية التسجيل (أيام العطلات فقط محظورة)"""
    now = get_saudi_time()
    if is_weekend(now.date()):
        return False, "لا يمكن تسجيل الحضور في أيام العطلات (الجمعة والسبت)"
    return True, None

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

# ============== صفحة التقارير الشهرية المؤقتة ==============
@app.route("/monthly_reports")
@login_required
def monthly_reports():
    return '''
    <!DOCTYPE html>
    <html dir="rtl" lang="ar">
    <head>
        <meta charset="UTF-8">
        <title>التقارير الشهرية - نظام حضور الطلاب</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container { max-width: 1200px; margin: 0 auto; }
            .header {
                background: white;
                border-radius: 20px;
                padding: 25px 30px;
                margin-bottom: 25px;
                box-shadow: 0 10px 40px rgba(0,0,0,0.1);
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
                gap: 15px;
            }
            .header h1 { color: #2d3748; font-size: 28px; }
            .back-btn {
                background: #667eea;
                color: white;
                padding: 10px 20px;
                border-radius: 10px;
                text-decoration: none;
                transition: 0.3s;
            }
            .back-btn:hover { background: #5a67d8; transform: translateY(-2px); }
            .controls {
                background: white;
                border-radius: 20px;
                padding: 20px 25px;
                margin-bottom: 25px;
                display: flex;
                gap: 15px;
                flex-wrap: wrap;
                align-items: flex-end;
            }
            .control-group { display: flex; flex-direction: column; gap: 5px; }
            .control-group label { font-size: 12px; color: #718096; font-weight: bold; }
            .control-group select, .control-group input {
                padding: 10px 15px;
                border: 2px solid #e2e8f0;
                border-radius: 10px;
                font-size: 14px;
            }
            .btn {
                padding: 10px 25px;
                border: none;
                border-radius: 10px;
                font-size: 14px;
                font-weight: bold;
                cursor: pointer;
                color: white;
            }
            .btn-primary { background: linear-gradient(135deg, #667eea, #764ba2); }
            .btn-success { background: linear-gradient(135deg, #48bb78, #38a169); }
            .summary-cards {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            .card {
                background: linear-gradient(135deg, #f8f9fa, #e9ecef);
                padding: 20px;
                border-radius: 15px;
                text-align: center;
            }
            .card h3 { color: #4a5568; font-size: 14px; margin-bottom: 10px; }
            .card .value { font-size: 32px; font-weight: bold; color: #667eea; }
            .card .small { font-size: 12px; color: #718096; margin-top: 8px; }
            .table-wrapper { overflow-x: auto; }
            table { width: 100%; border-collapse: collapse; background: white; border-radius: 15px; overflow: hidden; }
            th, td { padding: 12px 15px; text-align: center; border-bottom: 1px solid #e2e8f0; }
            th { background: linear-gradient(135deg, #667eea, #764ba2); color: white; }
            .present { color: #48bb78; font-weight: bold; }
            .late { color: #ed8936; font-weight: bold; }
            .absent { color: #fc8181; font-weight: bold; }
            .loading { text-align: center; padding: 50px; color: #718096; }
            @media (max-width: 768px) {
                .header { flex-direction: column; text-align: center; }
                .controls { flex-direction: column; }
                .control-group { width: 100%; }
                .btn { width: 100%; }
            }
        </style>
    </head>
    <body>
    <div class="container">
        <div class="header">
            <h1>📊 التقارير الشهرية المتقدمة</h1>
            <a href="/dashboard" class="back-btn">← العودة إلى لوحة التحكم</a>
        </div>

        <div class="controls">
            <div class="control-group">
                <label>📅 السنة</label>
                <select id="yearSelect">
                    <option value="2024">2024</option>
                    <option value="2025">2025</option>
                    <option value="2026" selected>2026</option>
                </select>
            </div>
            <div class="control-group">
                <label>📆 الشهر</label>
                <select id="monthSelect">
                    <option value="1">يناير</option>
                    <option value="2">فبراير</option>
                    <option value="3">مارس</option>
                    <option value="4">أبريل</option>
                    <option value="5">مايو</option>
                    <option value="6" selected>يونيو</option>
                    <option value="7">يوليو</option>
                    <option value="8">أغسطس</option>
                    <option value="9">سبتمبر</option>
                    <option value="10">أكتوبر</option>
                    <option value="11">نوفمبر</option>
                    <option value="12">ديسمبر</option>
                </select>
            </div>
            <button class="btn btn-primary" id="loadReport">📈 عرض التقرير</button>
            <button class="btn btn-success" id="exportExcel">📎 تصدير Excel</button>
        </div>

        <div id="summaryCards">
            <div class="loading">جاري تحميل البيانات...</div>
        </div>

        <div class="table-wrapper">
            <div id="dailyTable">
                <div class="loading">جاري تحميل البيانات...</div>
            </div>
        </div>
    </div>

    <script>
        async function loadReport() {
            const year = document.getElementById('yearSelect').value;
            const month = document.getElementById('monthSelect').value;
            
            document.getElementById('summaryCards').innerHTML = '<div class="loading">جاري تحميل البيانات...</div>';
            document.getElementById('dailyTable').innerHTML = '<div class="loading">جاري تحميل البيانات...</div>';
            
            try {
                const response = await fetch(`/api/monthly_report?year=${year}&month=${month}`);
                const data = await response.json();
                
                if (data.success) {
                    displaySummary(data);
                    displayTable(data);
                }
            } catch (error) {
                document.getElementById('summaryCards').innerHTML = '<div class="loading">❌ حدث خطأ</div>';
            }
        }

        function displaySummary(data) {
            const summary = data.summary;
            const totalAttendance = summary.total_present + summary.total_late;
            const html = `
                <div class="summary-cards">
                    <div class="card">
                        <h3>📊 إجمالي الحضور</h3>
                        <div class="value">${totalAttendance}</div>
                        <div class="small">حاضر: ${summary.total_present} | متأخر: ${summary.total_late}</div>
                    </div>
                    <div class="card">
                        <h3>📈 نسبة الحضور</h3>
                        <div class="value">${summary.avg_attendance_rate}%</div>
                        <div class="small">من أصل ${data.total_students} طالب</div>
                    </div>
                    <div class="card">
                        <h3>❌ إجمالي الغياب</h3>
                        <div class="value">${summary.total_absent}</div>
                        <div class="small">على مدار ${data.days_in_month} يوم</div>
                    </div>
                    <div class="card">
                        <h3>📅 أيام التسجيل</h3>
                        <div class="value">${summary.days_with_attendance}</div>
                        <div class="small">من أصل ${data.days_in_month} يوم</div>
                    </div>
                </div>
            `;
            document.getElementById('summaryCards').innerHTML = html;
        }

        function displayTable(data) {
            let html = `<table><thead><tr><th>#</th><th>التاريخ</th><th>✅ حاضر</th><th>⏰ متأخر</th><th>❌ غائب</th><th>📊 النسبة</th></tr></thead><tbody>`;
            
            for (const day of data.daily_stats) {
                html += `<tr>
                    <td>${day.day}</td>
                    <td>${day.date}</td>
                    <td class="present">${day.present}</td>
                    <td class="late">${day.late}</td>
                    <td class="absent">${day.absent}</td>
                    <td>${day.percentage}%</td>
                </tr>`;
            }
            html += '</tbody></table>';
            document.getElementById('dailyTable').innerHTML = html;
        }

        function exportExcel() {
            const year = document.getElementById('yearSelect').value;
            const month = document.getElementById('monthSelect').value;
            window.open(`/api/monthly_report?year=${year}&month=${month}&export=excel`, '_blank');
        }

        document.getElementById('loadReport').addEventListener('click', loadReport);
        document.getElementById('exportExcel').addEventListener('click', exportExcel);
        
        loadReport();
    </script>
    </body>
    </html>
    '''

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
        
        # التحقق من عدم التكرار
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

# ============== التقارير الشهرية المتقدمة ==============
@app.route("/api/monthly_report")
@login_required
def monthly_report():
    """تقرير شهري مفصل مع إحصائيات"""
    year = int(request.args.get('year', get_saudi_time().year))
    month = int(request.args.get('month', get_saudi_time().month))
    students = get_live_students()
    attendance = get_live_attendance()
    
    # عدد أيام الشهر
    days_in_month = monthrange(year, month)[1]
    
    daily_stats = []
    total_present = 0
    total_late = 0
    total_absent = 0
    total_days_with_attendance = 0
    
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
    
    # حساب متوسط الحضور
    avg_attendance = round((total_present + total_late) / (days_in_month * len(students)) * 100, 2) if len(students) > 0 else 0
    
    # تصدير إلى Excel
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
    """تقرير شهري لطالب محدد"""
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
    
    # تصدير إلى Excel
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
    """تقرير مقارن بين عدة أشهر"""
    year = int(request.args.get('year', get_saudi_time().year))
    months = request.args.get('months', '1,2,3,4,5,6,7,8,9,10,11,12')
    months = [int(m) for m in months.split(',')]
    
    students = get_live_students()
    attendance = get_live_attendance()
    
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

def get_month_name(month):
    """تحويل رقم الشهر إلى اسم عربي"""
    months = {
        1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل',
        5: 'مايو', 6: 'يونيو', 7: 'يوليو', 8: 'أغسطس',
        9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'
    }
    return months.get(month, str(month))

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

        df = df.fillna("")
        for col in df.columns:
            df[col] = df[col].astype(str)
        
        df['student_id'] = df['student_id'].str.replace('.0', '', regex=False).str.strip()
        
        records = df.to_dict("records")

        print("🗑️ جاري حذف البيانات القديمة...")
        supabase.table("students").delete().neq("student_id", "").execute()

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
    print("📊 التقارير الشهرية: متاحة على /monthly_reports")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)