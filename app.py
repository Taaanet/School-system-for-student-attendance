from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from datetime import datetime, timedelta
import os
import hashlib

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
                'parent_phone': ['', '', '', '', ''],
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
    """تسجيل الحضور مع منع التكرار"""
    try:
        if os.path.exists(ATTENDANCE_FILE):
            existing_df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            existing_today = existing_df[(existing_df['student_id'] == student_id) & (existing_df['date'] == date)]
            if not existing_today.empty:
                return False, "مسجل مسبقاً"
        
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
        
        if os.path.exists(ATTENDANCE_FILE):
            df_existing = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        else:
            df_new.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        
        return True, "تم التسجيل"
    except Exception as e:
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
    try:
        data = request.get_json()
        qr_data = data.get("qr_data", "").strip()
        
        students_df = load_students_data()
        
        if students_df is None:
            return jsonify({"success": False, "message": "⚠️ خطأ في قاعدة بيانات الطلاب"})
        
        student, found_id = find_student_flexible(students_df, qr_data)
        
        if student is None or student.empty:
            return jsonify({"success": False, "message": f"❌ لم يتم العثور على طالب بالرقم: '{qr_data}'"})
        
        student_data = student.iloc[0]
        student_id = str(student_data['student_id'])
        student_name = str(student_data['name'])
        student_grade = str(student_data['grade'])
        student_class = str(student_data['class'])
        
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        current_date = now.strftime("%Y-%m-%d")
        
        status, status_icon = get_attendance_status(current_time)
        
        success, msg = record_attendance(student_id, student_name, student_grade, student_class,
                                         current_date, current_time, status, "")
        
        if not success and msg == "مسجل مسبقاً":
            return jsonify({
                "success": True,
                "message": f"⚠️ {student_name} مسجل الحضور مسبقاً اليوم",
                "status": "already_registered",
                "student_name": student_name,
                "student_grade": student_grade,
                "student_class": student_class,
                "time": current_time,
                "date": current_date
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
            "date": current_date
        }
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({"success": False, "message": f"حدث خطأ: {str(e)}"})

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
        return jsonify({"success": True, "data": records})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/attendance_summary")
def attendance_summary():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        students_df = load_students_data()
        total_students = len(students_df) if students_df is not None else 0
        
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "total_students": total_students,
                           "present": 0, "late": 0, "early": 0, "absent": total_students,
                           "percentage": 0, "date": today})
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        today_attendance = df[df['date'] == today]
        
        present_count = len(today_attendance[today_attendance['status'] == 'حاضر في الوقت'])
        late_count = len(today_attendance[today_attendance['status'] == 'متأخر'])
        early_count = len(today_attendance[today_attendance['status'] == 'قبل الموعد'])
        absent_count = total_students - (present_count + late_count + early_count)
        total_present = present_count + late_count + early_count
        percentage = round(total_present / total_students * 100, 2) if total_students > 0 else 0
        
        return jsonify({"success": True, "total_students": int(total_students),
                       "present": int(present_count), "late": int(late_count),
                       "early": int(early_count), "absent": int(absent_count) if absent_count > 0 else 0,
                       "percentage": float(percentage), "date": today})
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
        
        return jsonify({"success": True, "data": all_students, "total": len(all_students),
                       "present": present_count, "late": late_count, "absent": absent_count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/attendance_chart_data")
def attendance_chart_data():
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "daily_data": [], "status_distribution": {}})
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        df['date'] = pd.to_datetime(df['date'])
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        daily_stats = []
        current = start_date
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            day_data = df[df['date'].dt.strftime("%Y-%m-%d") == date_str]
            daily_stats.append({
                "date": date_str,
                "present": len(day_data[day_data['status'].isin(['حاضر في الوقت', 'قبل الموعد'])]),
                "late": len(day_data[day_data['status'] == 'متأخر'])
            })
            current += timedelta(days=1)
        
        status_dist = df['status'].value_counts().to_dict()
        
        return jsonify({"success": True, "daily_data": daily_stats, "status_distribution": status_dist})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/top_students")
def top_students():
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "data": []})
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        
        attendance_count = df[df['status'].isin(['حاضر في الوقت', 'قبل الموعد'])].groupby('student_name').size().reset_index(name='count')
        attendance_count = attendance_count.sort_values('count', ascending=False).head(10)
        
        result = []
        for _, row in attendance_count.iterrows():
            result.append({"name": row['student_name'], "count": int(row['count'])})
        
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/monthly_report")
def monthly_report():
    try:
        year = request.args.get('year', datetime.now().year)
        month = request.args.get('month', datetime.now().month)
        
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "daily_stats": [], "total_present": 0, "total_late": 0})
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        df['date'] = pd.to_datetime(df['date'])
        
        monthly_data = df[(df['date'].dt.year == int(year)) & (df['date'].dt.month == int(month))]
        
        daily_stats = []
        for day in range(1, 32):
            try:
                day_date = datetime(int(year), int(month), day)
                if day_date <= datetime.now():
                    date_str = day_date.strftime("%Y-%m-%d")
                    day_data = monthly_data[monthly_data['date'].dt.strftime("%Y-%m-%d") == date_str]
                    daily_stats.append({
                        "day": day,
                        "present": len(day_data[day_data['status'].isin(['حاضر في الوقت', 'قبل الموعد'])]),
                        "late": len(day_data[day_data['status'] == 'متأخر'])
                    })
            except:
                pass
        
        total_present = len(monthly_data[monthly_data['status'].isin(['حاضر في الوقت', 'قبل الموعد'])])
        total_late = len(monthly_data[monthly_data['status'] == 'متأخر'])
        
        return jsonify({"success": True, "daily_stats": daily_stats,
                       "total_present": total_present, "total_late": total_late,
                       "year": year, "month": month})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/advanced_stats")
def advanced_stats():
    try:
        students_df = load_students_data()
        total_students = len(students_df) if students_df is not None else 0
        
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "total_students": total_students,
                           "avg_daily_attendance": 0, "best_day": None, "worst_day": None,
                           "most_late_student": None, "total_records": 0})
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        df['date'] = pd.to_datetime(df['date'])
        
        daily_counts = df.groupby(df['date'].dt.date).size()
        avg_daily = daily_counts.mean() if len(daily_counts) > 0 else 0
        
        if len(daily_counts) > 0:
            best_day = daily_counts.idxmax().strftime("%Y-%m-%d")
            worst_day = daily_counts.idxmin().strftime("%Y-%m-%d")
        else:
            best_day = worst_day = None
        
        late_counts = df[df['status'] == 'متأخر'].groupby('student_name').size()
        most_late = late_counts.idxmax() if len(late_counts) > 0 else None
        
        return jsonify({"success": True, "total_students": total_students,
                       "avg_daily_attendance": round(avg_daily, 2),
                       "best_day": best_day, "worst_day": worst_day,
                       "most_late_student": most_late,
                       "total_records": len(df)})
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

@app.route("/api/student_report/<student_id>")
def student_report(student_id):
    try:
        students_df = load_students_data()
        student_data = students_df[students_df['student_id'].astype(str) == str(student_id)]
        
        if student_data.empty:
            return jsonify({"success": False, "error": "الطالب غير موجود"})
        
        student_name = str(student_data.iloc[0]['name'])
        
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "student_name": student_name, "student_id": str(student_id),
                           "grade": str(student_data.iloc[0]['grade']), "class": str(student_data.iloc[0]['class']),
                           "total_days": 0, "present": 0, "late": 0, "absent": 0, "attendance_rate": 0, "records": []})
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        student_records = df[df['student_id'].astype(str) == str(student_id)]
        
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
        
        return jsonify({"success": True, "student_name": student_name, "student_id": str(student_id),
                       "grade": str(student_data.iloc[0]['grade']), "class": str(student_data.iloc[0]['class']),
                       "total_days": school_days, "present": present_count, "late": late_count,
                       "absent": absent_count if absent_count > 0 else 0,
                       "attendance_rate": round((present_count + late_count) / school_days * 100, 2) if school_days > 0 else 0,
                       "records": records})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/export_full_report")
def export_full_report():
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"error": "لا توجد بيانات"}), 404
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        filename = f"full_attendance_report_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.xlsx"
        df.to_excel(filename, index=False)
        return send_file(filename, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("🚀 نظام رصد الحضور والتأخير - يعمل الآن!")
    print(f"⏰ وقت الحضور: {ATTENDANCE_START} - {ATTENDANCE_DEADLINE}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)