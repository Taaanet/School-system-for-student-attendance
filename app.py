from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from datetime import datetime
import os
import json

app = Flask(__name__)
CORS(app)

# ============== إعدادات النظام ==============
ATTENDANCE_DEADLINE = "08:30:00"  # وقت الحضور المحدد
STUDENTS_FILE = 'students.xlsx'
ATTENDANCE_FILE = 'attendance.csv'

# ============== دوال مساعدة ==============

def load_students_data():
    """تحميل بيانات الطلاب من ملف Excel"""
    try:
        if not os.path.exists(STUDENTS_FILE):
            print(f"⚠️ ملف {STUDENTS_FILE} غير موجود")
            return None
        
        df = pd.read_excel(STUDENTS_FILE)
        df['student_id'] = df['student_id'].astype(str)
        return df
    except Exception as e:
        print(f"خطأ في تحميل ملف Excel: {e}")
        return None

def record_attendance(student_id, student_name, grade, class_name, date, time, status, notes=""):
    """تسجيل الحضور في ملف CSV"""
    try:
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
            df_existing = pd.read_csv(ATTENDANCE_FILE)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        else:
            df_new.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        
        print(f"✅ تم تسجيل الحضور: {student_name} - {status} في {time}")
        return True
    except Exception as e:
        print(f"❌ خطأ في تسجيل الحضور: {e}")
        return False

def send_message(phone, student_name, status, time):
    """إرسال رسالة للطالب أو ولي الأمر"""
    # هذا مجرد نموذج - يمكنك تفعيل الخدمة الفعلية لاحقاً
    message = f"مرحباً {student_name}، تم تسجيل حضورك {status} الساعة {time}"
    print(f"📱 جاري إرسال رسالة إلى {phone}: {message}")
    
    # مثال باستخدام Twilio (قم بتفعيله عند الحاجة):
    # from twilio.rest import Client
    # client = Client(account_sid, auth_token)
    # client.messages.create(body=message, from_='+1234567890', to=phone)
    
    return True

def get_attendance_status(current_time):
    """تحديد حالة الحضور حسب الوقت"""
    if current_time <= ATTENDANCE_DEADLINE:
        return "حاضر في الوقت", "✅"
    else:
        return "متأخر", "⏰"

# ============== الصفحات الرئيسية ==============

@app.route("/")
def home():
    """الصفحة الرئيسية"""
    return render_template("index.html")

@app.route("/scan")
def scan():
    """صفحة مسح QR"""
    return render_template("scan.html")

@app.route("/reports")
def reports():
    """صفحة التقارير"""
    return render_template("reports.html")

# ============== API معالجة المسح ==============

@app.route("/process_scan", methods=["POST", "GET"])
def process_scan():
    """معالجة بيانات المسح من QR Code"""
    
    # استلام البيانات من الطلب
    if request.method == "POST":
        data = request.get_json()
        if data:
            qr_data = data.get("qr_data")
        else:
            qr_data = request.form.get("qr_data")
    else:  # GET
        qr_data = request.args.get("qr_data")
    
    print(f"📱 تم استلام البيانات: {qr_data}")
    
    # التحقق من وجود البيانات
    if not qr_data:
        return jsonify({
            "success": False,
            "message": "⚠️ لم يتم استلام بيانات QR",
            "status": "error"
        }), 400
    
    student_id = str(qr_data).strip()
    
    # تحميل بيانات الطلاب
    students_df = load_students_data()
    
    if students_df is None:
        return jsonify({
            "success": False,
            "message": "⚠️ خطأ في قاعدة بيانات الطلاب. يرجى التأكد من وجود ملف students.xlsx",
            "status": "error"
        }), 500
    
    # البحث عن الطالب
    student = students_df[students_df['student_id'] == student_id]
    
    if student.empty:
        return jsonify({
            "success": False,
            "message": f"⚠️ لم يتم العثور على طالب بالرقم: {student_id}",
            "status": "error"
        }), 404
    
    # استخراج معلومات الطالب
    student_name = student.iloc[0]['name']
    student_grade = student.iloc[0]['grade']
    student_class = student.iloc[0]['class']
    student_phone = str(student.iloc[0].get('phone', '')) if pd.notna(student.iloc[0].get('phone', '')) else ''
    student_notes = str(student.iloc[0].get('notes', '')) if pd.notna(student.iloc[0].get('notes', '')) else ''
    
    # الوقت الحالي
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    current_date = now.strftime("%Y-%m-%d")
    
    # تحديد حالة الحضور
    status, status_icon = get_attendance_status(current_time)
    
    # تسجيل الحضور
    record_attendance(student_id, student_name, student_grade, student_class, 
                     current_date, current_time, status, student_notes)
    
    # إرسال رسالة (إذا كان هناك رقم جوال)
    if student_phone and student_phone != 'nan' and len(student_phone) > 5:
        send_message(student_phone, student_name, status, current_time)
    
    # تجهيز رسالة النتيجة
    if status == "حاضر في الوقت":
        result_message = f"{status_icon} تم تسجيل حضور {student_name} (الصف {student_grade} - الشعبة {student_class}) في الوقت المحدد {current_time}"
    else:
        result_message = f"{status_icon} تم تسجيل حضور {student_name} (الصف {student_grade} - الشعبة {student_class}) متأخراً الساعة {current_time}"
    
    # إرجاع النتيجة
    response_data = {
        "success": True,
        "message": result_message,
        "status": status,
        "status_icon": status_icon,
        "student_name": student_name,
        "student_grade": student_grade,
        "student_class": student_class,
        "time": current_time,
        "date": current_date,
        "student_id": student_id,
        "phone": student_phone
    }
    
    print(f"✅ تمت المعالجة بنجاح: {student_name}")
    return jsonify(response_data)

# ============== API التقارير والإحصائيات ==============

@app.route("/api/attendance_summary")
def attendance_summary():
    """الحصول على ملخص الحضور لليوم"""
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({
                "success": True,
                "total_students": 0,
                "present": 0,
                "late": 0,
                "absent": 0,
                "percentage": 0,
                "date": datetime.now().strftime("%Y-%m-%d")
            })
        
        df = pd.read_csv(ATTENDANCE_FILE)
        today = datetime.now().strftime("%Y-%m-%d")
        
        # بيانات اليوم
        today_attendance = df[df['date'] == today]
        
        # تحميل كل الطلاب
        students_df = load_students_data()
        total_students = len(students_df) if students_df is not None else 0
        
        present_count = len(today_attendance[today_attendance['status'] == 'حاضر في الوقت'])
        late_count = len(today_attendance[today_attendance['status'] == 'متأخر'])
        absent_count = total_students - (present_count + late_count)
        
        percentage = round((present_count + late_count) / total_students * 100, 2) if total_students > 0 else 0
        
        return jsonify({
            "success": True,
            "total_students": total_students,
            "present": present_count,
            "late": late_count,
            "absent": absent_count if absent_count > 0 else 0,
            "percentage": percentage,
            "date": today
        })
    except Exception as e:
        print(f"❌ خطأ في attendance_summary: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/attendance_details/<date>")
def attendance_details(date):
    """تفاصيل الحضور لتاريخ محدد"""
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "data": []})
        
        df = pd.read_csv(ATTENDANCE_FILE)
        df['date'] = df['date'].astype(str)
        
        day_attendance = df[df['date'] == date]
        
        return jsonify({
            "success": True,
            "data": day_attendance.to_dict('records'),
            "count": len(day_attendance)
        })
    except Exception as e:
        print(f"❌ خطأ في attendance_details: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/export_attendance/<date>")
def export_attendance(date):
    """تصدير تقرير الحضور كملف Excel"""
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"error": "لا توجد بيانات"}), 404
        
        df = pd.read_csv(ATTENDANCE_FILE)
        df['date'] = df['date'].astype(str)
        
        day_attendance = df[df['date'] == date]
        
        if day_attendance.empty:
            return jsonify({"error": f"لا توجد بيانات لتاريخ {date}"}), 404
        
        filename = f"attendance_report_{date}.xlsx"
        day_attendance.to_excel(filename, index=False)
        
        return send_file(filename, as_attachment=True, download_name=filename)
    except Exception as e:
        print(f"❌ خطأ في export_attendance: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/student_attendance/<student_id>")
def student_attendance(student_id):
    """تقرير حضور طالب محدد"""
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({
                "success": True,
                "student_id": student_id,
                "total_days": 0,
                "on_time": 0,
                "late": 0,
                "attendance_rate": 0,
                "records": []
            })
        
        df = pd.read_csv(ATTENDANCE_FILE)
        student_records = df[df['student_id'].astype(str) == str(student_id)]
        
        total_days = len(student_records)
        on_time = len(student_records[student_records['status'] == 'حاضر في الوقت'])
        late = len(student_records[student_records['status'] == 'متأخر'])
        
        # جلب اسم الطالب
        students_df = load_students_data()
        student_name = ""
        if students_df is not None:
            student_data = students_df[students_df['student_id'].astype(str) == str(student_id)]
            if not student_data.empty:
                student_name = student_data.iloc[0]['name']
        
        return jsonify({
            "success": True,
            "student_id": student_id,
            "student_name": student_name,
            "total_days": total_days,
            "on_time": on_time,
            "late": late,
            "attendance_rate": round(on_time / total_days * 100, 2) if total_days > 0 else 0,
            "records": student_records.to_dict('records')
        })
    except Exception as e:
        print(f"❌ خطأ في student_attendance: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/absent_students")
def absent_students():
    """الحصول على قائمة الطلاب الغائبين اليوم"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        
        # تحميل كل الطلاب
        students_df = load_students_data()
        if students_df is None:
            return jsonify({"success": True, "data": []})
        
        # تحميل حضور اليوم
        present_ids = set()
        if os.path.exists(ATTENDANCE_FILE):
            df = pd.read_csv(ATTENDANCE_FILE)
            today_attendance = df[df['date'] == today]
            present_ids = set(today_attendance['student_id'].astype(str))
        
        # تحديد الغائبين
        absent_students = []
        for _, student in students_df.iterrows():
            student_id = str(student['student_id'])
            if student_id not in present_ids:
                absent_students.append({
                    "student_id": student_id,
                    "name": student['name'],
                    "grade": student['grade'],
                    "class": student['class'],
                    "phone": str(student.get('phone', '')) if pd.notna(student.get('phone', '')) else ''
                })
        
        return jsonify({
            "success": True,
            "data": absent_students,
            "count": len(absent_students)
        })
    except Exception as e:
        print(f"❌ خطأ في absent_students: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/all_attendance")
def all_attendance():
    """الحصول على جميع سجلات الحضور"""
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "data": []})
        
        df = pd.read_csv(ATTENDANCE_FILE)
        return jsonify({
            "success": True,
            "data": df.to_dict('records'),
            "total": len(df)
        })
    except Exception as e:
        print(f"❌ خطأ في all_attendance: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/stats/weekly")
def weekly_stats():
    """إحصائيات الأسبوع الحالي"""
    try:
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({"success": True, "data": []})
        
        df = pd.read_csv(ATTENDANCE_FILE)
        df['date'] = pd.to_datetime(df['date'])
        
        # آخر 7 أيام
        today = datetime.now()
        week_ago = today - timedelta(days=7)
        
        weekly_data = df[df['date'] >= week_ago]
        
        stats = []
        for date, group in weekly_data.groupby(weekly_data['date'].dt.date):
            stats.append({
                "date": str(date),
                "present": len(group[group['status'] == 'حاضر في الوقت']),
                "late": len(group[group['status'] == 'متأخر']),
                "total": len(group)
            })
        
        return jsonify({"success": True, "data": stats})
    except Exception as e:
        print(f"❌ خطأ في weekly_stats: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ============== API إدارة الطلاب ==============

@app.route("/api/students")
def get_all_students():
    """الحصول على جميع الطلاب"""
    try:
        students_df = load_students_data()
        if students_df is None:
            return jsonify({"success": True, "data": []})
        
        return jsonify({
            "success": True,
            "data": students_df.to_dict('records'),
            "count": len(students_df)
        })
    except Exception as e:
        print(f"❌ خطأ في get_all_students: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/add_student", methods=["POST"])
def add_student():
    """إضافة طالب جديد إلى ملف Excel"""
    try:
        data = request.get_json()
        
        new_student = pd.DataFrame([{
            'student_id': str(data.get('student_id')),
            'name': data.get('name'),
            'grade': data.get('grade'),
            'class': data.get('class'),
            'phone': data.get('phone', ''),
            'notes': data.get('notes', '')
        }])
        
        if os.path.exists(STUDENTS_FILE):
            existing_df = pd.read_excel(STUDENTS_FILE)
            updated_df = pd.concat([existing_df, new_student], ignore_index=True)
        else:
            updated_df = new_student
        
        updated_df.to_excel(STUDENTS_FILE, index=False)
        
        return jsonify({
            "success": True,
            "message": f"تم إضافة الطالب {data.get('name')} بنجاح"
        })
    except Exception as e:
        print(f"❌ خطأ في add_student: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ============== API إحصائيات عامة ==============

@app.route("/api/dashboard_stats")
def dashboard_stats():
    """إحصائيات عامة للوحة التحكم"""
    try:
        students_df = load_students_data()
        total_students = len(students_df) if students_df is not None else 0
        
        # إحصائيات الحضور الكلية
        if os.path.exists(ATTENDANCE_FILE):
            df = pd.read_csv(ATTENDANCE_FILE)
            total_attendance_records = len(df)
            
            # أكثر الطلاب حضوراً
            top_students = df.groupby('student_name').size().sort_values(ascending=False).head(5).to_dict()
        else:
            total_attendance_records = 0
            top_students = {}
        
        return jsonify({
            "success": True,
            "total_students": total_students,
            "total_attendance_records": total_attendance_records,
            "top_students": top_students,
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        print(f"❌ خطأ في dashboard_stats: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    print("=" * 50)
    print("🚀 تشغيل نظام رصد الحضور والتأخير")
    print("=" * 50)
    print(f"📁 ملف الطلاب: {STUDENTS_FILE}")
    print(f"📁 ملف الحضور: {ATTENDANCE_FILE}")
    print(f"⏰ وقت الحضور المحدد: {ATTENDANCE_DEADLINE}")
    print("=" * 50)
    print("📍 قم بفتح الرابط التالي في المتصفح:")
    print("   http://localhost:5000")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
