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
ATTENDANCE_DEADLINE = "08:30:00"  # وقت الحضور المحدد
STUDENTS_FILE = 'students.xlsx'
ATTENDANCE_FILE = 'attendance.csv'

# ============== دوال مساعدة ==============

def convert_to_serializable(obj):
    """تحويل الأرقام من int64 إلى int عادي ليتوافق مع JSON"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, pd.Timestamp):
        return str(obj)
    return obj

def load_students_data():
    """تحميل بيانات الطلاب من ملف Excel"""
    try:
        if not os.path.exists(STUDENTS_FILE):
            # إنشاء ملف تجريبي إذا لم يكن موجوداً
            test_data = pd.DataFrame({
                'student_id': ['1150436838', '2', '3', '4', '5'],
                'name': ['طالب تجريبي', 'أحمد محمد', 'سارة علي', 'محمد خالد', 'نورا أحمد'],
                'grade': ['الثالث الثانوي', 'الأول الثانوي', 'الأول الثانوي', 'الثاني الثانوي', 'الأول الثانوي'],
                'class': ['أ', 'أ', 'ب', 'أ', 'ج'],
                'phone': ['', '', '', '', ''],
                'notes': ['', '', '', '', '']
            })
            test_data.to_excel(STUDENTS_FILE, index=False)
            print("✅ تم إنشاء ملف students.xlsx تجريبي")
        
        df = pd.read_excel(STUDENTS_FILE)
        # تحويل جميع الأعمدة إلى النوع المناسب
        df['student_id'] = df['student_id'].astype(str).str.strip()
        return df
    except Exception as e:
        print(f"خطأ في تحميل ملف Excel: {e}")
        return None

def find_student_flexible(students_df, student_id):
    """البحث عن الطالب بمرونة"""
    search_id = str(student_id).strip()
    
    # بحث تام
    student = students_df[students_df['student_id'] == search_id]
    if not student.empty:
        return student, search_id
    
    # بحث مع إزالة الأصفار
    if search_id.startswith('0'):
        without_zeros = str(int(search_id))
        student = students_df[students_df['student_id'] == without_zeros]
        if not student.empty:
            return student, without_zeros
    
    return None, search_id

def record_attendance(student_id, student_name, grade, class_name, date, time, status, notes=""):
    """تسجيل الحضور مع التحقق من عدم التكرار"""
    try:
        if os.path.exists(ATTENDANCE_FILE):
            existing_df = pd.read_csv(ATTENDANCE_FILE)
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
            df_existing = pd.read_csv(ATTENDANCE_FILE)
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
    """معالجة بيانات المسح من QR Code"""
    try:
        data = request.get_json()
        qr_data = data.get("qr_data", "").strip()
        
        print(f"📱 تم مسح الرقم: '{qr_data}'")
        
        # تحميل بيانات الطلاب
        students_df = load_students_data()
        
        if students_df is None:
            return jsonify({
                "success": False,
                "message": "⚠️ خطأ في قاعدة بيانات الطلاب",
                "status": "error"
            })
        
        # البحث عن الطالب
        student, found_id = find_student_flexible(students_df, qr_data)
        
        if student is None or student.empty:
            available = students_df['student_id'].tolist()
            return jsonify({
                "success": False,
                "message": f"❌ لم يتم العثور على طالب بالرقم: '{qr_data}'\n\n✅ المعرفات المتاحة: {', '.join(available[:5])}",
                "scanned_id": qr_data,
                "available_ids": available[:5],
                "status": "error"
            })
        
        # تحويل البيانات إلى أنواع JSON صديقة
        student_data = student.iloc[0]
        student_id = str(student_data['student_id'])
        student_name = str(student_data['name'])
        student_grade = str(student_data['grade'])
        student_class = str(student_data['class'])
        student_phone = str(student_data.get('phone', '')) if pd.notna(student_data.get('phone', '')) else ''
        
        # الوقت الحالي
        now = datetime.now()
        current_time = now.strftime("%H:%M:%S")
        current_date = now.strftime("%Y-%m-%d")
        
        # تحديد الحالة
        status = "حاضر في الوقت" if current_time <= ATTENDANCE_DEADLINE else "متأخر"
        status_icon = "✅" if status == "حاضر في الوقت" else "⏰"
        
        # تسجيل الحضور
        success, msg = record_attendance(student_id, student_name, student_grade, student_class,
                                         current_date, current_time, status, student_phone)
        
        # تجهيز الرد
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
        
        print(f"✅ تم التسجيل: {student_name}")
        return jsonify(response)
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return jsonify({
            "success": False,
            "message": f"حدث خطأ: {str(e)}",
            "status": "error"
        })

# ============== API إضافية ==============

@app.route("/api/students_list")
def students_list():
    """إرجاع قائمة الطلاب مع تحويل البيانات"""
    try:
        students_df = load_students_data()
        if students_df is None:
            return jsonify({"success": True, "data": []})
        
        # تحويل DataFrame إلى قائمة من القواميس مع تحويل الأنواع
        records = students_df.to_dict('records')
        serializable_records = []
        for record in records:
            clean_record = {}
            for key, value in record.items():
                if pd.isna(value):
                    clean_record[key] = ""
                elif isinstance(value, (np.integer, np.int64)):
                    clean_record[key] = int(value)
                elif isinstance(value, (np.floating, np.float64)):
                    clean_record[key] = float(value)
                else:
                    clean_record[key] = str(value)
            serializable_records.append(clean_record)
        
        return jsonify({
            "success": True,
            "data": serializable_records,
            "count": len(serializable_records)
        })
    except Exception as e:
        print(f"خطأ: {e}")
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/attendance_summary")
def attendance_summary():
    """ملخص الحضور اليوم"""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        students_df = load_students_data()
        total = len(students_df) if students_df is not None else 0
        
        if not os.path.exists(ATTENDANCE_FILE):
            return jsonify({
                "success": True,
                "total_students": total,
                "present": 0,
                "late": 0,
                "absent": total,
                "percentage": 0,
                "date": today
            })
        
        df = pd.read_csv(ATTENDANCE_FILE)
        today_attendance = df[df['date'] == today]
        
        present = len(today_attendance[today_attendance['status'] == 'حاضر في الوقت'])
        late = len(today_attendance[today_attendance['status'] == 'متأخر'])
        absent = total - (present + late)
        percentage = round((present + late) / total * 100, 2) if total > 0 else 0
        
        return jsonify({
            "success": True,
            "total_students": int(total),
            "present": int(present),
            "late": int(late),
            "absent": int(absent),
            "percentage": float(percentage),
            "date": today
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ============== التشغيل ==============
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print("=" * 50)
    print("🚀 نظام رصد الحضور والتأخير - يعمل الآن!")
    print(f"📍 الرابط: http://0.0.0.0:{port}")
    print("=" * 50)
    app.run(host='0.0.0.0', port=port)