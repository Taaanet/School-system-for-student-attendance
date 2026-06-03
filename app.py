from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import numpy as np

app = Flask(__name__)
CORS(app)

# ============== إعدادات النظام ==============
ATTENDANCE_START = "07:00:00"
ATTENDANCE_DEADLINE = "07:30:00"
STUDENTS_FILE = 'students.xlsx'
ATTENDANCE_FILE = 'attendance.csv'

# ============== دوال مساعدة ==============

def load_students_data():
    """تحميل بيانات الطلاب من ملف Excel"""
    try:
        if not os.path.exists(STUDENTS_FILE):
            test_data = pd.DataFrame({
                'student_id': ['1150436838', '1152217368', '1152327969', '1152502371', '1153472889'],
                'name': ['عبدالله فيصل شندي', 'أحمد محمد علي', 'سارة خالد عبدالله', 'محمد إبراهيم', 'نورة سعيد'],
                'grade': ['الأول الثانوي', 'الأول الثانوي', 'الثاني الثانوي', 'الثاني الثانوي', 'الثالث الثانوي'],
                'class': ['أ', 'ب', 'أ', 'ج', 'أ'],
                'phone': ['', '', '', '', ''],
                'notes': ['', '', '', '', '']
            })
            test_data.to_excel(STUDENTS_FILE, index=False)
            print("✅ تم إنشاء ملف students.xlsx تجريبي")
        
        df = pd.read_excel(STUDENTS_FILE)
        df['student_id'] = df['student_id'].astype(str).str.strip()
        return df
    except Exception as e:
        print(f"خطأ في تحميل ملف Excel: {e}")
        return None

def find_student_flexible(students_df, student_id):
    """البحث عن الطالب بمرونة"""
    search_id = str(student_id).strip()
    
    student = students_df[students_df['student_id'] == search_id]
    if not student.empty:
        return student, search_id
    
    if search_id.startswith('0'):
        without_zeros = str(int(search_id))
        student = students_df[students_df['student_id'] == without_zeros]
        if not student.empty:
            return student, without_zeros
    
    return None, search_id

def get_attendance_status(current_time_str):
    """تحديد حالة الحضور حسب الوقت"""
    try:
        current = datetime.strptime(current_time_str, "%H:%M:%S").time()
        start = datetime.strptime(ATTENDANCE_START, "%H:%M:%S").time()
        deadline = datetime.strptime(ATTENDANCE_DEADLINE, "%H:%M:%S").time()
        
        if current < start:
            return "قبل الموعد", "⏳"
        elif current <= deadline:
            return "حاضر في الوقت", "✅"
        else:
            return "متأخر", "⏰"
    except:
        return "حاضر", "✅"

def record_attendance(student_id, student_name, grade, class_name, date, time, status, notes=""):
    """تسجيل الحضور مع التحقق من عدم التكرار"""
    try:
        # التحقق من عدم تسجيل الطالب مرتين في نفس اليوم
        if os.path.exists(ATTENDANCE_FILE):
            existing_df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            existing_today = existing_df[(existing_df['student_id'] == student_id) & (existing_df['date'] == date)]
            if not existing_today.empty:
                print(f"⚠️ الطالب {student_name} مسجل مسبقاً اليوم")
                return False, "مسجل مسبقاً"
        
        # إنشاء سجل جديد
        record = {
            'student_id': student_id,
            'student_name': student_name,
            'grade': grade,
            'class': class_name,
            'date': date,
            'time': time,
            'status': status,
            'notes': notes,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        df_new = pd.DataFrame([record])
        
        # حفظ الملف
        if os.path.exists(ATTENDANCE_FILE):
            df_existing = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        else:
            df_new.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        
        print(f"✅ تم تسجيل الحضور: {student_name} - {status} في {time}")
        return True, "تم التسجيل"
        
    except Exception as e:
        print(f"❌ خطأ في تسجيل الحضور: {e}")
        return False, str(e)

# ============== الصفحات الرئيسية ==============

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/scan")
def scan():
    return render_template("scan.html")

@app.route("/reports")
def reports():
    return render_template("reports.html")

# ============== API معالجة المسح ==============

@app.route("/process_scan", methods=["POST"])
def process_scan():
    """معالجة بيانات المسح من QR Code"""
    try:
        data = request.get_json()
        qr_data = data.get("qr_data", "").strip()
        
        print(f"📱 تم مسح الرقم: '{qr_data}'")
        
        students_df = load_students_data()
        
        if students_df is None:
            return jsonify({
                "success": False,
                "message": "⚠️ خطأ في قاعدة بيانات الطلاب",
                "status": "error"
            })
        
        student, found_id = find_student_flexible(students_df, qr_data)
        
        if student is None or student.empty:
            return jsonify({
                "success": False,
                "message": f"❌ لم يتم العثور على طالب بالرقم: '{qr_data}'",
                "status": "error"
            })
        
        student_data = student.iloc[0]
        student_id = str(student_data['student_id'])
        student_name = str(student_data['name'])
        student_grade = str(student_data['grade'])
        student_class = str(student_data['class'])
        student_phone = str(student_data.get('phone', '')) if pd.notna(student_data.get('phone', '')) else ''
        
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        current_date = now.strftime("%Y-%m-%d")
        
        status, status_icon = get_attendance_status(current_time)
        
        success, msg = record_attendance(student_id, student_name, student_grade, student_class,
                                         current_date, current_time, status, student_phone)
        
        if not success and msg == "مسجل مسبقاً":
            return jsonify({
                "success": True,
                "message": f"⚠️ {student_name} مسجل الحضور مسبقاً اليوم",
                "status": "already_registered",
                "status_icon": "⚠️",
                "student_name": student_name,
                "student_grade": student_grade,
                "student_class": student_class,
                "time": current_time,
                "date": current_date,
                "student_id": student_id
            })
        
        response = {
            "success": True,
            "message": f"{status_icon} تم تسجيل حضور {student_name} (الصف {student_grade} - الشعبة {student_class}) - {status} الساعة {current_time}",
            "status": status,
            "status_icon": status_icon,
            "student_name": student_name,
            "student_grade": student_grade,
            "student_class": student_class,
            "time": current_time,
            "date": current_date,
            "student_id": student_id
        }
        
        print(f"✅ تم التسجيل: {student_name} - {status}")
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return jsonify({
            "success": False,
            "message": f"حدث خطأ: {str(e)}",
            "status": "error"
        })

# ============== API التقارير ==============

@app.route("/api/students_list")
def students_list():
    try:
        students_df = load_students_data()
        if students_df is None:
            return jsonify({"success": True, "data": []})
        
        records = []
        for _, row in students_df.iterrows():
            records.append({
                "student_id": str(row['student_id']),
                "name": str(row['name']),
                "grade": str(row['grade']),
                "class": str(row['class'])
            })
        return jsonify({"success": True, "data": records, "count": len(records)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/attendance_summary")
def attendance_summary():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        students_df = load_students_data()
        total_students = len(students_df) if students_df is not None else 0
        
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({
                "success": True,
                "total_students": total_students,
                "present": 0, "late": 0, "early": 0, "absent": total_students,
                "percentage": 0, "date": today
            })
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        today_attendance = df[df['date'] == today]
        
        present_count = len(today_attendance[today_attendance['status'] == 'حاضر في الوقت'])
        late_count = len(today_attendance[today_attendance['status'] == 'متأخر'])
        early_count = len(today_attendance[today_attendance['status'] == 'قبل الموعد'])
        absent_count = total_students - (present_count + late_count + early_count)
        total_present = present_count + late_count + early_count
        percentage = round(total_present / total_students * 100, 2) if total_students > 0 else 0
        
        return jsonify({
            "success": True,
            "total_students": int(total_students),
            "present": int(present_count),
            "late": int(late_count),
            "early": int(early_count),
            "absent": int(absent_count) if absent_count > 0 else 0,
            "percentage": float(percentage),
            "date": today
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/attendance_details/<date>")
def attendance_details(date):
    try:
        students_df = load_students_data()
        if students_df is None:
            return jsonify({"success": True, "data": []})
        
        all_students = []
        for _, row in students_df.iterrows():
            all_students.append({
                "student_id": str(row['student_id']),
                "student_name": str(row['name']),
                "grade": str(row['grade']),
                "class": str(row['class']),
                "status": "غائب",
                "time": "-"
            })
        
        if os.path.exists(ATTENDANCE_FILE):
            df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            df['date'] = df['date'].astype(str)
            day_attendance = df[df['date'] == date]
            
            for _, att in day_attendance.iterrows():
                for student in all_students:
                    if student['student_id'] == str(att['student_id']):
                        student['status'] = str(att['status'])
                        student['time'] = str(att['time'])
                        break
        
        present_count = len([s for s in all_students if s['status'] in ['حاضر في الوقت', 'قبل الموعد']])
        late_count = len([s for s in all_students if s['status'] == 'متأخر'])
        absent_count = len([s for s in all_students if s['status'] == 'غائب'])
        
        return jsonify({
            "success": True,
            "data": all_students,
            "total": len(all_students),
            "present": present_count,
            "late": late_count,
            "absent": absent_count
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/absent_students_today")
def absent_students_today():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        students_df = load_students_data()
        
        if students_df is None:
            return jsonify({"success": True, "data": []})
        
        present_ids = set()
        if os.path.exists(ATTENDANCE_FILE):
            df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            present_ids = set(df[df['date'] == today]['student_id'].astype(str))
        
        absent_list = []
        for _, student in students_df.iterrows():
            student_id = str(student['student_id'])
            if student_id not in present_ids:
                absent_list.append({
                    "student_id": student_id,
                    "name": str(student['name']),
                    "grade": str(student['grade']),
                    "class": str(student['class'])
                })
        
        return jsonify({"success": True, "data": absent_list, "count": len(absent_list)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/student_report/<student_id>")
def student_report(student_id):
    try:
        students_df = load_students_data()
        student_data = students_df[students_df['student_id'].astype(str) == str(student_id)]
        
        if student_data.empty:
            return jsonify({"success": False, "error": "الطالب غير موجود"})
        
        student_name = str(student_data.iloc[0]['name'])
        
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({
                "success": True, "student_name": student_name, "student_id": str(student_id),
                "grade": str(student_data.iloc[0]['grade']), "class": str(student_data.iloc[0]['class']),
                "total_days": 0, "present": 0, "late": 0, "absent": 0, "attendance_rate": 0, "records": []
            })
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        student_records = df[df['student_id'].astype(str) == str(student_id)]
        
        # حساب أيام الدراسة
        if not student_records.empty:
            first_date = datetime.strptime(student_records['date'].min(), "%Y-%m-%d")
            today = datetime.now()
            school_days = 0
            current = first_date
            while current <= today:
                if current.weekday() < 5:
                    school_days += 1
                current += timedelta(days=1)
        else:
            school_days = 0
        
        present_count = len(student_records[student_records['status'].isin(['حاضر في الوقت', 'قبل الموعد'])])
        late_count = len(student_records[student_records['status'] == 'متأخر'])
        absent_count = school_days - (present_count + late_count) if school_days > 0 else 0
        
        records = []
        for _, row in student_records.iterrows():
            records.append({"date": str(row['date']), "time": str(row['time']), "status": str(row['status'])})
        
        return jsonify({
            "success": True,
            "student_name": student_name,
            "student_id": str(student_id),
            "grade": str(student_data.iloc[0]['grade']),
            "class": str(student_data.iloc[0]['class']),
            "total_days": school_days,
            "present": present_count,
            "late": late_count,
            "absent": absent_count if absent_count > 0 else 0,
            "attendance_rate": round((present_count + late_count) / school_days * 100, 2) if school_days > 0 else 0,
            "records": records
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/weekly_report")
def weekly_report():
    try:
        today = datetime.now().date()
        start_of_week = today - timedelta(days=today.weekday())
        
        weekly_data = []
        days_names = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس"]
        
        for i in range(5):
            current_date = start_of_week + timedelta(days=i)
            date_str = current_date.strftime("%Y-%m-%d")
            
            if os.path.exists(ATTENDANCE_FILE):
                df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
                df['date'] = df['date'].astype(str)
                day_data = df[df['date'] == date_str]
                present = len(day_data[day_data['status'].isin(['حاضر في الوقت', 'قبل الموعد'])])
                late = len(day_data[day_data['status'] == 'متأخر'])
            else:
                present, late = 0, 0
            
            weekly_data.append({"date": date_str, "day_name": days_names[i], "present": present, "late": late})
        
        return jsonify({"success": True, "data": weekly_data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_attendance/<date>")
def export_attendance(date):
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"error": "لا توجد بيانات"}), 404
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        df['date'] = df['date'].astype(str)
        day_attendance = df[df['date'] == date]
        
        if day_attendance.empty:
            return jsonify({"error": f"لا توجد بيانات لتاريخ {date}"}), 404
        
        filename = f"attendance_report_{date}.xlsx"
        day_attendance.to_excel(filename, index=False)
        return send_file(filename, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/test_attendance")
def test_attendance():
    """مسار اختبار للتأكد من أن التسجيل يعمل"""
    try:
        test_id = "TEST001"
        test_name = "طالب تجريبي"
        test_date = datetime.now().strftime("%Y-%m-%d")
        test_time = datetime.now().strftime("%H:%M:%S")
        
        success, msg = record_attendance(test_id, test_name, "اختبار", "أ", test_date, test_time, "حاضر", "سجل تجريبي")
        
        return jsonify({
            "success": success,
            "message": msg,
            "file_exists": os.path.exists(ATTENDANCE_FILE),
            "file_path": os.path.abspath(ATTENDANCE_FILE) if os.path.exists(ATTENDANCE_FILE) else "غير موجود"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("🚀 نظام رصد الحضور والتأخير - يعمل الآن!")
    print(f"⏰ وقت الحضور: {ATTENDANCE_START} - {ATTENDANCE_DEADLINE}")
    print(f"📍 الرابط: http://0.0.0.0:{port}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)