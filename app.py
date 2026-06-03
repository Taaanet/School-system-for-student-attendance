from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)

# ============== إعدادات النظام ==============
ATTENDANCE_DEADLINE = "07:30:00"
STUDENTS_FILE = 'students.xlsx'
ATTENDANCE_FILE = 'attendance.csv'

# ============== دوال مساعدة ==============

def load_students_data():
    """تحميل بيانات الطلاب"""
    try:
        if not os.path.exists(STUDENTS_FILE):
            test_data = pd.DataFrame({
                'student_id': ['1150436838', '1152217368', '1152327969', '1152502371', '1153472889'],
                'name': ['عبدالله فيصل شندي', 'أحمد محمد علي', 'سارة خالد', 'محمد إبراهيم', 'نورة سعيد'],
                'grade': ['الأول الثانوي', 'الأول الثانوي', 'الثاني الثانوي', 'الثاني الثانوي', 'الثالث الثانوي'],
                'class': ['أ', 'ب', 'أ', 'ج', 'أ'],
                'phone': ['', '', '', '', ''],
                'notes': ['', '', '', '', '']
            })
            test_data.to_excel(STUDENTS_FILE, index=False)
            print("✅ تم إنشاء ملف students.xlsx")
        
        df = pd.read_excel(STUDENTS_FILE)
        df['student_id'] = df['student_id'].astype(str).str.strip()
        return df
    except Exception as e:
        print(f"خطأ: {e}")
        return pd.DataFrame()

def get_attendance_status():
    """تحديد حالة الحضور حسب الوقت الحالي"""
    try:
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        deadline = datetime.strptime(ATTENDANCE_DEADLINE, "%H:%M:%S").time()
        current = datetime.strptime(current_time, "%H:%M:%S").time()
        
        if current <= deadline:
            return "حاضر في الوقت", current_time
        else:
            return "متأخر", current_time
    except:
        return "حاضر", datetime.now().strftime("%H:%M:%S")

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
    try:
        data = request.get_json()
        student_id = str(data.get("student_id", "")).strip()
        
        if not student_id:
            return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب"})
        
        students_df = load_students_data()
        if students_df.empty:
            return jsonify({"success": False, "message": "لا توجد بيانات طلاب"})
        
        student = students_df[students_df['student_id'] == student_id]
        
        if student.empty:
            return jsonify({"success": False, "message": f"الطالب رقم {student_id} غير موجود"})
        
        student_name = str(student.iloc[0]['name'])
        student_grade = str(student.iloc[0]['grade'])
        student_class = str(student.iloc[0]['class'])
        
        status, current_time = get_attendance_status()
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # التحقق من عدم التكرار
        if os.path.exists(ATTENDANCE_FILE):
            existing_df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            existing_today = existing_df[(existing_df['student_id'] == student_id) & (existing_df['date'] == current_date)]
            if not existing_today.empty:
                return jsonify({
                    "success": True,
                    "message": f"⚠️ {student_name} مسجل مسبقاً اليوم",
                    "already_registered": True,
                    "student_name": student_name,
                    "student_grade": student_grade,
                    "student_class": student_class,
                    "time": current_time,
                    "date": current_date,
                    "status": status
                })
        
        # تسجيل الحضور
        new_record = pd.DataFrame([{
            'student_id': student_id,
            'student_name': student_name,
            'grade': student_grade,
            'class': student_class,
            'date': current_date,
            'time': current_time,
            'status': status,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }])
        
        if os.path.exists(ATTENDANCE_FILE):
            existing_df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            combined = pd.concat([existing_df, new_record], ignore_index=True)
            combined.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        else:
            new_record.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        
        return jsonify({
            "success": True,
            "message": f"✅ تم تسجيل حضور {student_name} ({student_grade} - {student_class}) - {status} الساعة {current_time}",
            "student_name": student_name,
            "student_grade": student_grade,
            "student_class": student_class,
            "time": current_time,
            "date": current_date,
            "status": status
        })
        
    except Exception as e:
        return jsonify({"success": False, "message": f"خطأ: {str(e)}"})

# ============== API التقارير ==============

@app.route("/api/students_list")
def students_list():
    try:
        students_df = load_students_data()
        if students_df.empty:
            return jsonify({"success": True, "data": []})
        
        records = []
        for _, row in students_df.iterrows():
            records.append({
                "student_id": str(row['student_id']),
                "name": str(row['name']),
                "grade": str(row['grade']),
                "class": str(row['class'])
            })
        return jsonify({"success": True, "data": records})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/attendance_summary")
def attendance_summary():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        students_df = load_students_data()
        total_students = len(students_df) if not students_df.empty else 0
        
        present = 0
        late = 0
        
        if os.path.exists(ATTENDANCE_FILE) and os.path.getsize(ATTENDANCE_FILE) > 0:
            df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            today_attendance = df[df['date'] == today]
            present = len(today_attendance[today_attendance['status'] == 'حاضر في الوقت'])
            late = len(today_attendance[today_attendance['status'] == 'متأخر'])
        
        absent = total_students - (present + late)
        percentage = round((present + late) / total_students * 100, 2) if total_students > 0 else 0
        
        return jsonify({
            "success": True,
            "total_students": total_students,
            "present": present,
            "late": late,
            "absent": absent if absent > 0 else 0,
            "percentage": percentage,
            "date": today
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/attendance_details/<date>")
def attendance_details(date):
    try:
        students_df = load_students_data()
        if students_df.empty:
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
        
        if os.path.exists(ATTENDANCE_FILE) and os.path.getsize(ATTENDANCE_FILE) > 0:
            df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            df['date'] = df['date'].astype(str)
            day_attendance = df[df['date'] == date]
            
            for _, att in day_attendance.iterrows():
                for student in all_students:
                    if student['student_id'] == str(att['student_id']):
                        student['status'] = str(att['status'])
                        student['time'] = str(att['time'])
                        break
        
        present = len([s for s in all_students if s['status'] == 'حاضر في الوقت'])
        late = len([s for s in all_students if s['status'] == 'متأخر'])
        absent = len([s for s in all_students if s['status'] == 'غائب'])
        
        return jsonify({
            "success": True,
            "data": all_students,
            "present": present,
            "late": late,
            "absent": absent
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/absent_students_today")
def absent_students_today():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        students_df = load_students_data()
        
        if students_df.empty:
            return jsonify({"success": True, "data": []})
        
        present_ids = set()
        if os.path.exists(ATTENDANCE_FILE) and os.path.getsize(ATTENDANCE_FILE) > 0:
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
        
        return jsonify({"success": True, "data": absent_list})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/top_students")
def top_students():
    try:
        if not os.path.exists(ATTENDANCE_FILE) or os.path.getsize(ATTENDANCE_FILE) == 0:
            return jsonify({"success": True, "data": []})
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        top = df[df['status'] == 'حاضر في الوقت'].groupby('student_name').size().sort_values(ascending=False).head(10)
        
        result = []
        for name, count in top.items():
            result.append({"name": name, "count": int(count)})
        
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/student_report/<student_id>")
def student_report(student_id):
    try:
        students_df = load_students_data()
        student_info = students_df[students_df['student_id'].astype(str) == str(student_id)]
        
        student_name = ""
        student_grade = ""
        student_class = ""
        if not student_info.empty:
            student_name = str(student_info.iloc[0]['name'])
            student_grade = str(student_info.iloc[0]['grade'])
            student_class = str(student_info.iloc[0]['class'])
        
        if not os.path.exists(ATTENDANCE_FILE) or os.path.getsize(ATTENDANCE_FILE) == 0:
            return jsonify({
                "success": True,
                "student_name": student_name,
                "student_id": str(student_id),
                "grade": student_grade,
                "class": student_class,
                "total_days": 0,
                "present": 0,
                "late": 0,
                "absent": 0,
                "attendance_rate": 0,
                "records": []
            })
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        student_records = df[df['student_id'].astype(str) == str(student_id)]
        
        present = len(student_records[student_records['status'] == 'حاضر في الوقت'])
        late = len(student_records[student_records['status'] == 'متأخر'])
        total_days = len(student_records)
        attendance_rate = round((present + late) / total_days * 100, 2) if total_days > 0 else 0
        
        records = []
        for _, row in student_records.iterrows():
            records.append({
                "date": str(row['date']),
                "time": str(row['time']),
                "status": str(row['status'])
            })
        
        return jsonify({
            "success": True,
            "student_name": student_name,
            "student_id": str(student_id),
            "grade": student_grade,
            "class": student_class,
            "total_days": total_days,
            "present": present,
            "late": late,
            "absent": total_days - (present + late),
            "attendance_rate": attendance_rate,
            "records": records
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/create_test_data")
def create_test_data():
    """إنشاء بيانات تجريبية للاختبار"""
    try:
        students_df = load_students_data()
        if students_df.empty:
            return jsonify({"error": "لا توجد بيانات طلاب"})
        
        today = datetime.now().strftime("%Y-%m-%d")
        test_records = []
        
        # تسجيل الطلاب كحاضرين
        for i in range(min(3, len(students_df))):
            student = students_df.iloc[i]
            test_records.append({
                'student_id': str(student['student_id']),
                'student_name': str(student['name']),
                'grade': str(student['grade']),
                'class': str(student['class']),
                'date': today,
                'time': (datetime.now() - timedelta(hours=2)).strftime("%H:%M:%S"),
                'status': 'حاضر في الوقت',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        
        # تسجيل طالب متأخر
        if len(students_df) > 3:
            student = students_df.iloc[3]
            test_records.append({
                'student_id': str(student['student_id']),
                'student_name': str(student['name']),
                'grade': str(student['grade']),
                'class': str(student['class']),
                'date': today,
                'time': (datetime.now() + timedelta(hours=1)).strftime("%H:%M:%S"),
                'status': 'متأخر',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
        
        df_new = pd.DataFrame(test_records)
        df_new.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        
        return jsonify({
            "success": True,
            "message": f"✅ تم إنشاء {len(test_records)} سجل تجريبي",
            "count": len(test_records)
        })
    except Exception as e:
        return jsonify({"error": str(e)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("🚀 نظام الحضور يعمل الآن!")
    print(f"📍 الرابط: http://0.0.0.0:{port}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)