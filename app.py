from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
from datetime import datetime, timedelta
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
        # تنظيف البيانات
        df['student_id'] = df['student_id'].astype(str).str.strip()
        return df
    except Exception as e:
        print(f"خطأ في تحميل ملف Excel: {e}")
        return None

def record_attendance(student_id, student_name, grade, class_name, date, time, status, notes=""):
    """تسجيل الحضور في ملف CSV"""
    try:
        # التحقق من عدم تسجيل نفس الطالب مرتين في نفس اليوم
        if os.path.exists(ATTENDANCE_FILE):
            existing_df = pd.read_csv(ATTENDANCE_FILE)
            existing_today = existing_df[(existing_df['student_id'] == student_id) & (existing_df['date'] == date)]
            if not existing_today.empty:
                print(f"⚠️ الطالب {student_name} مسجل مسبقاً اليوم")
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
            df_existing = pd.read_csv(ATTENDANCE_FILE)
            df_combined = pd.concat([df_existing, df_new], ignore_index=True)
            df_combined.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        else:
            df_new.to_csv(ATTENDANCE_FILE, index=False, encoding='utf-8-sig')
        
        print(f"✅ تم تسجيل الحضور: {student_name} - {status} في {time}")
        return True, "تم التسجيل"
    except Exception as e:
        print(f"❌ خطأ في تسجيل الحضور: {e}")
        return False, str(e)

def find_student_flexible(students_df, student_id):
    """البحث عن الطالب بمرونة"""
    # تنظيف ID المدخل
    search_id = str(student_id).strip()
    
    # 1. بحث عادي
    student = students_df[students_df['student_id'] == search_id]
    if not student.empty:
        return student, search_id
    
    # 2. إزالة الأصفار من البداية
    if search_id.startswith('0'):
        without_zeros = str(int(search_id))
        student = students_df[students_df['student_id'] == without_zeros]
        if not student.empty:
            return student, without_zeros
    
    # 3. إضافة أصفار إلى 3 خانات
    if len(search_id) < 3:
        with_zeros = search_id.zfill(3)
        student = students_df[students_df['student_id'] == with_zeros]
        if not student.empty:
            return student, with_zeros
    
    # 4. بحث جزئي (إذا كان الرقم جزء من المعرف)
    student = students_df[students_df['student_id'].str.contains(search_id, na=False, case=False)]
    if not student.empty:
        return student, student.iloc[0]['student_id']
    
    return None, search_id

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

@app.route("/qr_codes")
def qr_codes_page():
    """صفحة عرض رموز QR"""
    return render_template("qr_codes.html")

@app.route("/debug")
def debug():
    """صفحة تصحيح الأخطاء"""
    return render_template("debug.html")

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
    
    print(f"📱 تم استلام البيانات: '{qr_data}'")
    
    # التحقق من وجود البيانات
    if not qr_data:
        return jsonify({
            "success": False,
            "message": "⚠️ لم يتم استلام بيانات QR",
            "status": "error"
        }), 400
    
    # تحميل بيانات الطلاب
    students_df = load_students_data()
    
    if students_df is None:
        return jsonify({
            "success": False,
            "message": "⚠️ خطأ في قاعدة بيانات الطلاب. يرجى التأكد من وجود ملف students.xlsx",
            "status": "error"
        }), 500
    
    # البحث المرن عن الطالب
    result, found_id = find_student_flexible(students_df, qr_data)
    
    if result is None:
        # عرض المعرفات المتاحة للمساعدة في التصحيح
        available_ids = students_df['student_id'].tolist()[:10]  # أول 10 فقط
        return jsonify({
            "success": False,
            "message": f"⚠️ لم يتم العثور على طالب بالرقم: '{qr_data}'\n\n✅ المعرفات المتاحة في النظام:\n{', '.join(available_ids[:5])}...",
            "status": "error",
            "scanned_id": qr_data,
            "available_ids": available_ids
        }), 404
    
    # استخراج معلومات الطالب
    student = result.iloc[0]
    student_id = found_id
    student_name = student['name']
    student_grade = student['grade']
    student_class = student['class']
    student_phone = str(student.get('phone', '')) if pd.notna(student.get('phone', '')) else ''
    student_notes = str(student.get('notes', '')) if pd.notna(student.get('notes', '')) else ''
    
    # الوقت الحالي
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    current_date = now.strftime("%Y-%m-%d")
    
    # تحديد حالة الحضور
    status, status_icon = get_attendance_status(current_time)
    
    # تسجيل الحضور
    success, msg = record_attendance(student_id, student_name, student_grade, student_class, 
                     current_date, current_time, status, student_notes)
    
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

@app.route("/api/students_list")
def students_list():
    """الحصول على قائمة جميع الطلاب"""
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
    print("📍 قم بفتح الروابط التالية:")
    print("   🏠 الرئيسية: http://localhost:5000")
    print("   📷 صفحة المسح: http://localhost:5000/scan")
    print("   📊 التقارير: http://localhost:5000/reports")
    print("   🔍 التصحيح: http://localhost:5000/debug")
    print("=" * 50)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
