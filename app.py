from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)

# ============== إعدادات النظام ==============
ATTENDANCE_START = "07:00:00"
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
                'name': ['عبدالله فيصل شندي', 'أحمد محمد علي', 'سارة خالد عبدالله', 'محمد إبراهيم', 'نورة سعيد'],
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
        print(f"❌ خطأ في تحميل الطلاب: {e}")
        return None

def get_attendance_status(current_time_str):
    """تحديد حالة الحضور"""
    try:
        current = datetime.strptime(current_time_str, "%H:%M:%S").time()
        deadline = datetime.strptime(ATTENDANCE_DEADLINE, "%H:%M:%S").time()
        if current <= deadline:
            return "حاضر في الوقت", "✅"
        else:
            return "متأخر", "⏰"
    except:
        return "حاضر", "✅"

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
    """تسجيل حضور الطالب"""
    try:
        data = request.get_json()
        student_id = str(data.get("student_id", "")).strip()
        
        print(f"📱 محاولة تسجيل الرقم: {student_id}")
        
        if not student_id:
            return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب"})
        
        # تحميل بيانات الطلاب
        students_df = load_students_data()
        if students_df is None:
            return jsonify({"success": False, "message": "خطأ في قاعدة بيانات الطلاب"})
        
        # البحث عن الطالب
        student = students_df[students_df['student_id'] == student_id]
        
        if student.empty:
            # تجربة البحث بدون أصفار
            try:
                clean_id = str(int(student_id))
                student = students_df[students_df['student_id'] == clean_id]
            except:
                pass
        
        if student.empty:
            return jsonify({"success": False, "message": f"الطالب رقم {student_id} غير موجود"})
        
        # استخراج البيانات
        student_name = str(student.iloc[0]['name'])
        student_grade = str(student.iloc[0]['grade'])
        student_class = str(student.iloc[0]['class'])
        
        # الوقت الحالي
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        current_date = now.strftime("%Y-%m-%d")
        
        # تحديد الحالة
        status, icon = get_attendance_status(current_time)
        
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
                    "date": current_date
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
        
        print(f"✅ تم تسجيل: {student_name} - {status} الساعة {current_time}")
        
        return jsonify({
            "success": True,
            "message": f"{icon} تم تسجيل حضور {student_name} ({student_grade} - {student_class}) - {status} الساعة {current_time}",
            "student_name": student_name,
            "student_grade": student_grade,
            "student_class": student_class,
            "time": current_time,
            "date": current_date,
            "status": status
        })
        
    except Exception as e:
        print(f"❌ خطأ في التسجيل: {e}")
        return jsonify({"success": False, "message": f"خطأ: {str(e)}"})

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
                           "present": 0, "late": 0, "absent": total_students,
                           "percentage": 0, "date": today})
        
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        today_attendance = df[df['date'] == today]
        
        present = len(today_attendance[today_attendance['status'] == 'حاضر في الوقت'])
        late = len(today_attendance[today_attendance['status'] == 'متأخر'])
        absent = total_students - (present + late)
        percentage = round((present + late) / total_students * 100, 2) if total_students > 0 else 0
        
        return jsonify({"success": True, "total_students": total_students,
                       "present": present, "late": late, "absent": absent,
                       "percentage": percentage, "date": today})
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
        
        present = len([s for s in all_students if s['status'] == 'حاضر في الوقت'])
        late = len([s for s in all_students if s['status'] == 'متأخر'])
        absent = len([s for s in all_students if s['status'] == 'غائب'])
        
        return jsonify({"success": True, "data": all_students, "present": present, "late": late, "absent": absent})
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
        return jsonify({"success": True, "data": absent_list})
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
            return jsonify({"error": "لا توجد بيانات"}), 404
        filename = f"attendance_{date}.xlsx"
        day_attendance.to_excel(filename, index=False)
        return send_file(filename, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/top_students")
def top_students():
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "data": []})
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        top = df[df['status'] == 'حاضر في الوقت'].groupby('student_name').size().sort_values(ascending=False).head(10)
        result = [{"name": name, "count": int(count)} for name, count in top.items()]
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/monthly_report")
def monthly_report():
    try:
        year = request.args.get('year', datetime.now().year)
        month = request.args.get('month', datetime.now().month)
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "daily_stats": []})
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        df['date'] = pd.to_datetime(df['date'])
        monthly = df[(df['date'].dt.year == int(year)) & (df['date'].dt.month == int(month))]
        stats = []
        for day in range(1, 32):
            try:
                day_date = datetime(int(year), int(month), day)
                if day_date <= datetime.now():
                    date_str = day_date.strftime("%Y-%m-%d")
                    day_data = monthly[monthly['date'].dt.strftime("%Y-%m-%d") == date_str]
                    stats.append({"day": day, "present": len(day_data), "late": len(day_data[day_data['status'] == 'متأخر'])})
            except:
                pass
        return jsonify({"success": True, "daily_stats": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/advanced_stats")
def advanced_stats():
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "avg_daily": 0, "best_day": None})
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        df['date'] = pd.to_datetime(df['date'])
        daily = df.groupby(df['date'].dt.date).size()
        avg = daily.mean() if len(daily) > 0 else 0
        best = daily.idxmax().strftime("%Y-%m-%d") if len(daily) > 0 else None
        return jsonify({"success": True, "avg_daily_attendance": round(avg, 2), "best_day": best})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/attendance_chart_data")
def attendance_chart_data():
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "daily_data": []})
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        df['date'] = pd.to_datetime(df['date'])
        end = datetime.now()
        start = end - timedelta(days=30)
        data = []
        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            day_data = df[df['date'].dt.strftime("%Y-%m-%d") == date_str]
            data.append({"date": date_str, "present": len(day_data), "late": len(day_data[day_data['status'] == 'متأخر'])})
            current += timedelta(days=1)
        return jsonify({"success": True, "daily_data": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/student_report/<student_id>")
def student_report(student_id):
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": False, "error": "لا توجد بيانات"})
        df = pd.read_csv(ATTENDANCE_FILE, encoding='utf-8-sig')
        student_records = df[df['student_id'].astype(str) == str(student_id)]
        records = []
        for _, row in student_records.iterrows():
            records.append({"date": str(row['date']), "time": str(row['time']), "status": str(row['status'])})
        return jsonify({"success": True, "records": records, "total": len(records)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("🚀 النظام يعمل الآن!")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port, debug=False)