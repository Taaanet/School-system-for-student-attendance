from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import json
import pandas as pd
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
CORS(app)

# ============== إعدادات النظام ==============
ATTENDANCE_START = "07:00:00"
ATTENDANCE_DEADLINE = "07:30:00"
STUDENTS_FILE = 'students.xlsx'
ATTENDANCE_FILE = 'attendance.json'

# ============== بيانات المستخدمين ==============
USERS = {
    'admin': 'admin123',
    'teacher': 'teacher123'
}

# ============== دوال المصادقة ==============
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============== دوال مساعدة ==============
def load_students():
    """تحميل الطلاب من ملف Excel"""
    try:
        if not os.path.exists(STUDENTS_FILE):
            test_data = pd.DataFrame({
                'student_id': ['1150436838', '1152217368', '1152327969', '1152502371', '1153472889'],
                'name': ['عبدالله فيصل شندي', 'أحمد محمد علي', 'سارة خالد', 'محمد إبراهيم', 'نورة سعيد'],
                'grade': ['الأول الثانوي', 'الأول الثانوي', 'الثاني الثانوي', 'الثاني الثانوي', 'الثالث الثانوي'],
                'class': ['أ', 'ب', 'أ', 'ج', 'أ'],
                'phone': ['', '', '', '', ''],
                'parent_phone': ['', '', '', '', '']
            })
            test_data.to_excel(STUDENTS_FILE, index=False)
        
        df = pd.read_excel(STUDENTS_FILE)
        df['student_id'] = df['student_id'].astype(str).str.strip()
        return df.to_dict('records')
    except Exception as e:
        print(f"خطأ في تحميل الطلاب: {e}")
        return []

def load_attendance():
    """تحميل سجلات الحضور من ملف JSON"""
    try:
        if os.path.exists(ATTENDANCE_FILE):
            with open(ATTENDANCE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except:
        return []

def save_attendance(records):
    """حفظ سجلات الحضور إلى ملف JSON"""
    try:
        with open(ATTENDANCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"خطأ في حفظ الحضور: {e}")
        return False

def get_attendance_status():
    """تحديد حالة الحضور حسب الوقت"""
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    if current_time <= ATTENDANCE_DEADLINE:
        return "حاضر", current_time
    else:
        return "متأخر", current_time

def send_whatsapp_message(phone, message):
    """إرسال رسالة واتساب"""
    whatsapp_url = f"https://wa.me/{phone}?text={message.replace(' ', '%20')}"
    print(f"📱 واتساب إلى {phone}: {message}")
    return whatsapp_url

def send_sms(phone, message):
    """إرسال رسالة نصية SMS"""
    print(f"📱 SMS إلى {phone}: {message}")
    return True

# تحميل البيانات
students = load_students()
attendance_records = load_attendance()

# ============== صفحات المصادقة ==============
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username in USERS and USERS[username] == password:
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('home'))
        
        return render_template('login.html', error="بيانات الدخول غير صحيحة")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

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
            if s['student_id'] == student_id:
                student = s
                break
        
        if not student:
            return jsonify({"success": False, "message": f"الطالب {student_id} غير موجود"})
        
        status, current_time = get_attendance_status()
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        for record in attendance_records:
            if record['student_id'] == student_id and record['date'] == current_date:
                return jsonify({
                    "success": False,
                    "message": f"⚠️ {student['name']} مسجل مسبقاً اليوم",
                    "already_registered": True,
                    "student_name": student['name'],
                    "student_grade": student['grade'],
                    "student_class": student['class']
                })
        
        new_record = {
            'student_id': student_id,
            'student_name': student['name'],
            'grade': student['grade'],
            'class': student['class'],
            'date': current_date,
            'time': current_time,
            'status': status,
            'timestamp': datetime.now().isoformat()
        }
        
        attendance_records.append(new_record)
        save_attendance(attendance_records)
        
        # إرسال إشعارات
        if student.get('phone'):
            message = f"📚 تقرير حضور: تم تسجيل {student['name']} - {status} الساعة {current_time}"
            send_whatsapp_message(student['phone'], message)
        
        if student.get('parent_phone'):
            message = f"📚 تنبيه: تم تسجيل حضور {student['name']} بنجاح"
            send_sms(student['parent_phone'], message)
        
        return jsonify({
            "success": True,
            "message": f"✅ تم تسجيل حضور {student['name']} - {status} الساعة {current_time}",
            "student_name": student['name'],
            "student_grade": student['grade'],
            "student_class": student['class'],
            "time": current_time,
            "date": current_date,
            "status": status
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ============== API التقارير والإحصائيات ==============
@app.route("/api/students_list")
@login_required
def students_list():
    return jsonify({"success": True, "data": students})

@app.route("/api/attendance_summary")
@login_required
def attendance_summary():
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(students)
    
    today_records = [r for r in attendance_records if r['date'] == today]
    present = len([r for r in today_records if r['status'] == 'حاضر'])
    late = len([r for r in today_records if r['status'] == 'متأخر'])
    absent = total - (present + late)
    percentage = round(((present + late) / total) * 100, 1) if total > 0 else 0
    
    return jsonify({
        "success": True,
        "total_students": total,
        "present": present,
        "late": late,
        "absent": absent if absent > 0 else 0,
        "percentage": percentage,
        "date": today
    })

@app.route("/api/attendance_details/<date>")
@login_required
def attendance_details(date):
    result = []
    for student in students:
        record = None
        for r in attendance_records:
            if r['student_id'] == student['student_id'] and r['date'] == date:
                record = r
                break
        
        result.append({
            'student_id': student['student_id'],
            'student_name': student['name'],
            'grade': student['grade'],
            'class': student['class'],
            'status': record['status'] if record else 'غائب',
            'time': record['time'] if record else '-'
        })
    
    return jsonify({
        "success": True,
        "data": result,
        "present": len([s for s in result if s['status'] == 'حاضر']),
        "late": len([s for s in result if s['status'] == 'متأخر']),
        "absent": len([s for s in result if s['status'] == 'غائب'])
    })

@app.route("/api/absent_students_today")
@login_required
def absent_students_today():
    today = datetime.now().strftime("%Y-%m-%d")
    present_ids = set(r['student_id'] for r in attendance_records if r['date'] == today)
    absent = [s for s in students if s['student_id'] not in present_ids]
    return jsonify({"success": True, "data": absent})

@app.route("/api/top_students")
@login_required
def top_students():
    present_counts = {}
    for r in attendance_records:
        if r['status'] == 'حاضر':
            name = r['student_name']
            present_counts[name] = present_counts.get(name, 0) + 1
    
    sorted_students = sorted(present_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    result = [{"name": name, "count": count} for name, count in sorted_students]
    return jsonify({"success": True, "data": result})

@app.route("/api/student_report/<student_id>")
@login_required
def student_report(student_id):
    student = None
    for s in students:
        if s['student_id'] == student_id:
            student = s
            break
    
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})
    
    records = [r for r in attendance_records if r['student_id'] == student_id]
    records.sort(key=lambda x: x['date'], reverse=True)
    
    present = len([r for r in records if r['status'] == 'حاضر'])
    late = len([r for r in records if r['status'] == 'متأخر'])
    total = len(records)
    
    return jsonify({
        "success": True,
        "student_name": student['name'],
        "student_id": student_id,
        "grade": student['grade'],
        "class": student['class'],
        "total_days": total,
        "present": present,
        "late": late,
        "absent": total - (present + late),
        "attendance_rate": round((present + late) / total * 100, 1) if total > 0 else 0,
        "records": records
    })

@app.route("/api/monthly_report")
@login_required
def monthly_report():
    year = request.args.get('year', datetime.now().year)
    month = request.args.get('month', datetime.now().month)
    
    year = int(year)
    month = int(month)
    
    if month == 12:
        next_month = datetime(year + 1, 1, 1)
    else:
        next_month = datetime(year, month + 1, 1)
    
    days_in_month = (next_month - datetime(year, month, 1)).days
    
    daily_stats = []
    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        day_records = [r for r in attendance_records if r['date'] == date_str]
        
        daily_stats.append({
            'day': day,
            'present': len([r for r in day_records if r['status'] == 'حاضر']),
            'late': len([r for r in day_records if r['status'] == 'متأخر']),
            'absent': len(students) - len(day_records)
        })
    
    total_present = sum(d['present'] for d in daily_stats)
    total_late = sum(d['late'] for d in daily_stats)
    
    return jsonify({
        "success": True,
        "daily_stats": daily_stats,
        "total_present": total_present,
        "total_late": total_late,
        "days_in_month": days_in_month,
        "month": month,
        "year": year
    })

@app.route("/api/attendance_chart")
@login_required
def attendance_chart():
    """بيانات للرسوم البيانية"""
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(students)
    
    today_records = [r for r in attendance_records if r['date'] == today]
    present = len([r for r in today_records if r['status'] == 'حاضر'])
    late = len([r for r in today_records if r['status'] == 'متأخر'])
    absent = total - (present + late)
    
    return jsonify({
        "success": True,
        "labels": ["حاضر", "متأخر", "غائب"],
        "data": [present, late, absent],
        "colors": ["#28a745", "#fd7e14", "#dc3545"]
    })

@app.route("/api/dashboard_stats")
@login_required
def dashboard_stats():
    """إحصائيات لوحة التحكم"""
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(students)
    
    today_records = [r for r in attendance_records if r['date'] == today]
    present = len([r for r in today_records if r['status'] == 'حاضر'])
    late = len([r for r in today_records if r['status'] == 'متأخر'])
    percentage = round(((present + late) / total) * 100, 1) if total > 0 else 0
    
    # أفضل طالب
    present_counts = {}
    for r in attendance_records:
        if r['status'] == 'حاضر':
            name = r['student_name']
            present_counts[name] = present_counts.get(name, 0) + 1
    
    best_student = max(present_counts.items(), key=lambda x: x[1])[0] if present_counts else "لا يوجد"
    
    return jsonify({
        "success": True,
        "percentage": percentage,
        "present_today": present + late,
        "total_students": total,
        "best_student": best_student,
        "total_records": len(attendance_records)
    })

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
    save_attendance(attendance_records)
    return jsonify({"success": True, "message": "تم مسح جميع سجلات الحضور"})

@app.route("/api/stats")
@login_required
def stats():
    return jsonify({
        "success": True,
        "students_count": len(students),
        "attendance_count": len(attendance_records),
        "storage": "local_json"
    })

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    students = load_students()
    attendance_records = load_attendance()
    print("=" * 50)
    print(f"🚀 نظام الحضور يعمل الآن!")
    print(f"📚 تم تحميل {len(students)} طالب")
    print(f"📋 لدينا {len(attendance_records)} سجل حضور")
    print("=" * 50)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)