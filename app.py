from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os
import json
import pandas as pd

app = Flask(__name__)
CORS(app)

# ============== إعدادات النظام ==============
ATTENDANCE_DEADLINE = "07:30:00"
STUDENTS_FILE = 'students.xlsx'
ATTENDANCE_FILE = 'attendance.json'

# ============== دوال مساعدة ==============

def load_students():
    """تحميل الطلاب من ملف Excel"""
    try:
        if not os.path.exists(STUDENTS_FILE):
            # إنشاء بيانات تجريبية
            test_data = pd.DataFrame({
                'student_id': ['1150436838', '1152217368', '1152327969', '1152502371', '1153472889'],
                'name': ['عبدالله فيصل شندي', 'أحمد محمد علي', 'سارة خالد', 'محمد إبراهيم', 'نورة سعيد'],
                'grade': ['الأول الثانوي', 'الأول الثانوي', 'الثاني الثانوي', 'الثاني الثانوي', 'الثالث الثانوي'],
                'class': ['أ', 'ب', 'أ', 'ج', 'أ']
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
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    if current_time <= ATTENDANCE_DEADLINE:
        return "حاضر", current_time
    else:
        return "متأخر", current_time

# تحميل البيانات
students = load_students()
attendance_records = load_attendance()

# ============== الصفحات ==============
@app.route("/")
def home():
    return render_template("index.html")

@app.route("/scan")
def scan():
    return render_template("scan.html")

@app.route("/reports")
def reports():
    return render_template("reports.html")

# ============== API التسجيل ==============
@app.route("/api/register", methods=["POST"])
def register_attendance():
    global attendance_records
    
    try:
        data = request.get_json()
        student_id = str(data.get("student_id", "")).strip()
        
        if not student_id:
            return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب"})
        
        # البحث عن الطالب
        student = None
        for s in students:
            if s['student_id'] == student_id:
                student = s
                break
        
        if not student:
            return jsonify({"success": False, "message": f"الطالب {student_id} غير موجود"})
        
        status, current_time = get_attendance_status()
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # التحقق من عدم التكرار
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
        
        # تسجيل الحضور
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
def students_list():
    return jsonify({"success": True, "data": students})

@app.route("/api/attendance_summary")
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
def absent_students_today():
    today = datetime.now().strftime("%Y-%m-%d")
    present_ids = set(r['student_id'] for r in attendance_records if r['date'] == today)
    absent = [s for s in students if s['student_id'] not in present_ids]
    return jsonify({"success": True, "data": absent})

@app.route("/api/top_students")
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

@app.route("/api/load_excel")
def load_excel():
    global students
    students = load_students()
    return jsonify({"success": True, "message": f"تم تحميل {len(students)} طالب"})

@app.route("/api/clear_attendance")
def clear_attendance():
    global attendance_records
    attendance_records = []
    save_attendance(attendance_records)
    return jsonify({"success": True, "message": "تم مسح جميع سجلات الحضور"})

@app.route("/api/stats")
def stats():
    return jsonify({
        "success": True,
        "students_count": len(students),
        "attendance_count": len(attendance_records),
        "storage": "local_json"
    })

if __name__ == "__main__":
    # تحميل البيانات عند بدء التشغيل
    students = load_students()
    attendance_records = load_attendance()
    print(f"📚 تم تحميل {len(students)} طالب")
    print(f"📋 لدينا {len(attendance_records)} سجل حضور")
    
    port = int(os.environ.get("PORT", 5000))
    print("🚀 النظام يعمل الآن!")
    app.run(host='0.0.0.0', port=port, debug=False)