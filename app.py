from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file
from flask_cors import CORS
from datetime import datetime, timedelta
import os
import json
import pandas as pd
from functools import wraps
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
CORS(app)

# ============== إعدادات النظام ==============
ATTENDANCE_START = "07:00:00"
ATTENDANCE_DEADLINE = "07:30:00"
STUDENTS_FILE = 'students.xlsx'
ATTENDANCE_FILE = 'attendance.json'
USERS_FILE = 'users.json'

# ============== إعدادات Google Drive ==============
SCOPES = ['https://www.googleapis.com/auth/drive.file']
CREDENTIALS_FILE = 'credentials.json'
TOKEN_FILE = 'token.pickle'

def get_google_drive_service():
    """الحصول على خدمة Google Drive"""
    creds = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                print("⚠️ ملف credentials.json غير موجود")
                return None
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        
        with open(TOKEN_FILE, 'wb') as token:
            pickle.dump(creds, token)
    
    return build('drive', 'v3', credentials=creds)

def upload_to_google_drive(file_path, folder_name="Attendance Reports"):
    """رفع ملف إلى Google Drive"""
    try:
        service = get_google_drive_service()
        if not service:
            return None
        
        # البحث عن مجلد التقارير
        results = service.files().list(q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false", fields="files(id, name)").execute()
        folders = results.get('files', [])
        
        if folders:
            folder_id = folders[0]['id']
        else:
            file_metadata = {
                'name': folder_name,
                'mimeType': 'application/vnd.google-apps.folder'
            }
            folder = service.files().create(body=file_metadata, fields='id').execute()
            folder_id = folder.get('id')
        
        file_metadata = {
            'name': os.path.basename(file_path),
            'parents': [folder_id]
        }
        media = MediaFileUpload(file_path, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        
        return file.get('webViewLink')
    except Exception as e:
        print(f"خطأ في الرفع: {e}")
        return None

# ============== بيانات المستخدمين ==============
def load_users():
    """تحميل بيانات المستخدمين من ملف JSON"""
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except:
        pass
    
    default_users = {
        'taha_mohamad': {
            'password': 'Het@onet0hros',
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
    """حفظ بيانات المستخدمين"""
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ في حفظ المستخدمين: {e}")

def can_login(username):
    """التحقق من إمكانية تسجيل الدخول"""
    users = load_users()
    if username not in users:
        return False, "اسم المستخدم غير موجود"
    
    user = users[username]
    
    if user['role'] == 'admin':
        return True, None
    
    if user['max_logins'] is not None and user['login_count'] >= user['max_logins']:
        return False, f"لقد تجاوزت الحد المسموح به ({user['max_logins']} مرات). الرجاء التواصل مع المدير."
    
    return True, None

def increment_login_count(username):
    """زيادة عدد مرات الدخول"""
    users = load_users()
    if username in users and users[username]['role'] != 'admin':
        users[username]['login_count'] = users[username].get('login_count', 0) + 1
        save_users(users)

def reset_login_count(username):
    """إعادة تعيين عدد مرات الدخول"""
    users = load_users()
    if username in users:
        users[username]['login_count'] = 0
        save_users(users)
        return True
    return False

def get_remaining_logins(username):
    """الحصول على عدد المحاولات المتبقية"""
    users = load_users()
    if username not in users:
        return 0
    user = users[username]
    if user['role'] == 'admin':
        return "غير محدود"
    max_logins = user.get('max_logins', 5)
    used = user.get('login_count', 0)
    return max(max_logins - used, 0)

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
    """تحميل سجلات الحضور"""
    try:
        if os.path.exists(ATTENDANCE_FILE):
            with open(ATTENDANCE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except:
        return []

def save_attendance(records):
    """حفظ سجلات الحضور"""
    try:
        with open(ATTENDANCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"خطأ في حفظ الحضور: {e}")
        return False

def get_attendance_status():
    """تحديد حالة الحضور"""
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    if current_time <= ATTENDANCE_DEADLINE:
        return "حاضر", current_time
    else:
        return "متأخر", current_time

# تحميل البيانات
students = load_students()
attendance_records = load_attendance()

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
    
    if reset_login_count(username):
        return jsonify({"success": True, "message": f"تم إعادة تعيين عدد محاولات {username}"})
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
    today = datetime.now().strftime("%Y-%m-%d")
    total = len(students)
    
    today_records = [r for r in attendance_records if r['date'] == today]
    present = len([r for r in today_records if r['status'] == 'حاضر'])
    late = len([r for r in today_records if r['status'] == 'متأخر'])
    percentage = round(((present + late) / total) * 100, 1) if total > 0 else 0
    
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

# ============== APIs التصدير إلى Excel و Google Drive ==============
@app.route("/api/export_today_excel")
@login_required
def export_today_excel():
    """تصدير تقرير اليوم إلى Excel"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        filename = f"attendance_report_{today}.xlsx"
        
        result = []
        for student in students:
            record = None
            for r in attendance_records:
                if r['student_id'] == student['student_id'] and r['date'] == today:
                    record = r
                    break
            
            result.append({
                'رقم الطالب': student['student_id'],
                'اسم الطالب': student['name'],
                'الصف': student['grade'],
                'الشعبة': student['class'],
                'وقت التسجيل': record['time'] if record else '-',
                'الحالة': record['status'] if record else 'غائب'
            })
        
        df = pd.DataFrame(result)
        df.to_excel(filename, index=False, engine='openpyxl')
        
        return send_file(filename, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_monthly_excel")
@login_required
def export_monthly_excel():
    """تصدير تقرير شهري إلى Excel"""
    try:
        year = request.args.get('year', datetime.now().year)
        month = request.args.get('month', datetime.now().month)
        
        filename = f"monthly_report_{year}_{month}.xlsx"
        
        monthly_stats = []
        for student in students:
            student_records = [r for r in attendance_records if r['student_id'] == student['student_id']]
            present = len([r for r in student_records if r['status'] == 'حاضر'])
            late = len([r for r in student_records if r['status'] == 'متأخر'])
            
            monthly_stats.append({
                'رقم الطالب': student['student_id'],
                'اسم الطالب': student['name'],
                'الصف': student['grade'],
                'الشعبة': student['class'],
                'عدد أيام الحضور': present,
                'عدد أيام التأخير': late,
                'الغياب': len(student_records) - (present + late),
                'نسبة الحضور': round((present + late) / len(student_records) * 100, 1) if len(student_records) > 0 else 0
            })
        
        df = pd.DataFrame(monthly_stats)
        df.to_excel(filename, index=False, engine='openpyxl')
        
        return send_file(filename, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_student_excel/<student_id>")
@login_required
def export_student_excel(student_id):
    """تصدير تقرير طالب فردي إلى Excel"""
    try:
        student = None
        for s in students:
            if s['student_id'] == student_id:
                student = s
                break
        
        if not student:
            return jsonify({"success": False, "error": "الطالب غير موجود"})
        
        filename = f"student_{student_id}_report.xlsx"
        
        records = [r for r in attendance_records if r['student_id'] == student_id]
        records.sort(key=lambda x: x['date'], reverse=True)
        
        df = pd.DataFrame(records)
        df.to_excel(filename, index=False, engine='openpyxl')
        
        return send_file(filename, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/upload_to_drive/<report_type>")
@login_required
def upload_to_drive(report_type):
    """رفع تقرير إلى Google Drive"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        if report_type == 'today':
            filename = f"attendance_report_{today}.xlsx"
            
            result = []
            for student in students:
                record = None
                for r in attendance_records:
                    if r['student_id'] == student['student_id'] and r['date'] == today:
                        record = r
                        break
                
                result.append({
                    'رقم الطالب': student['student_id'],
                    'اسم الطالب': student['name'],
                    'الصف': student['grade'],
                    'الشعبة': student['class'],
                    'وقت التسجيل': record['time'] if record else '-',
                    'الحالة': record['status'] if record else 'غائب'
                })
            
            df = pd.DataFrame(result)
            df.to_excel(filename, index=False, engine='openpyxl')
            
            drive_link = upload_to_google_drive(filename)
            
            if drive_link:
                return jsonify({"success": True, "drive_link": drive_link, "message": "تم الرفع إلى Google Drive"})
            else:
                return jsonify({"success": False, "message": "فشل الرفع إلى Google Drive"})
        else:
            return jsonify({"success": False, "message": "نوع التقرير غير معروف"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_attendance/<date>")
@login_required
def export_attendance(date):
    """تصدير تقرير بتاريخ محدد"""
    try:
        filename = f"attendance_{date}.xlsx"
        
        result = []
        for student in students:
            record = None
            for r in attendance_records:
                if r['student_id'] == student['student_id'] and r['date'] == date:
                    record = r
                    break
            
            result.append({
                'رقم الطالب': student['student_id'],
                'اسم الطالب': student['name'],
                'الصف': student['grade'],
                'الشعبة': student['class'],
                'وقت التسجيل': record['time'] if record else '-',
                'الحالة': record['status'] if record else 'غائب'
            })
        
        df = pd.DataFrame(result)
        df.to_excel(filename, index=False, engine='openpyxl')
        
        return send_file(filename, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

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
    print("🚀 نظام الحضور يعمل الآن!")
    print(f"📚 تم تحميل {len(students)} طالب")
    print(f"📋 لدينا {len(attendance_records)} سجل حضور")
    print("=" * 50)
    print("👥 المستخدمون:")
    users = load_users()
    for username, data in users.items():
        max_logins = "غير محدود" if data['role'] == 'admin' else data.get('max_logins', 5)
        print(f"   - {username} (الدور: {data['role']}, الحد الأقصى: {max_logins})")
    print("=" * 50)
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)