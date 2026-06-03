from flask import Flask, render_template, request, jsonify
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)

# تحميل بيانات الطلاب من ملف Excel
def load_students_data():
    try:
        # تأكد من وجود ملف Excel بنفس المسار
        df = pd.read_excel('students.xlsx')
        
        # تحويل student_id إلى نص للتأكد من تطابق البيانات
        df['student_id'] = df['student_id'].astype(str)
        
        return df
    except Exception as e:
        print(f"خطأ في تحميل ملف Excel: {e}")
        return None

# الصفحة الرئيسية
@app.route("/")
def home():
    return render_template("index.html")

# صفحة مسح QR
@app.route("/scan")
def scan():
    return render_template("scan.html")

# صفحة عرض التقارير (اختياري)
@app.route("/reports")
def reports():
    return render_template("reports.html")

# معالجة بيانات المسح
@app.route("/process_scan", methods=["POST"])
def process_scan():
    data = request.get_json()
    qr_data = data.get("qr_data")
    
    # تنظيف البيانات المستلمة من QR Code
    student_id = str(qr_data).strip()
    
    # تحميل بيانات الطلاب
    students_df = load_students_data()
    
    if students_df is None:
        return jsonify({
            "message": "خطأ في قاعدة بيانات الطلاب",
            "status": "error"
        }), 500
    
    # البحث عن الطالب باستخدام student_id
    student = students_df[students_df['student_id'] == student_id]
    
    if student.empty:
        return jsonify({
            "message": f"⚠️ لم يتم العثور على طالب بالرقم: {student_id}",
            "status": "error"
        }), 404
    
    # استخراج معلومات الطالب
    student_name = student.iloc[0]['name']
    student_grade = student.iloc[0]['grade']
    student_class = student.iloc[0]['class']
    student_phone = student.iloc[0].get('phone', '')
    student_notes = student.iloc[0].get('notes', '')
    
    # الوقت الحالي
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    current_date = now.strftime("%Y-%m-%d")
    
    # تحديد وقت الحضور المحدد (مثلاً 8:30 صباحاً)
    attendance_deadline = "08:30:00"
    
    # تحديد الحضور أو التأخير
    if current_time <= attendance_deadline:
        status = "حاضر في الوقت"
        status_icon = "✅"
    else:
        status = "متأخر"
        status_icon = "⏰"
    
    # تسجيل الحضور في ملف CSV
    record_attendance(student_id, student_name, student_grade, student_class, 
                     current_date, current_time, status, student_notes)
    
    # تجهيز رسالة النتيجة
    if status == "حاضر في الوقت":
        result_message = f"{status_icon} تم تسجيل حضور {student_name} (الصف {student_grade} - الشعبة {student_class}) في الوقت المحدد {current_time}"
    else:
        result_message = f"{status_icon} تم تسجيل حضور {student_name} (الصف {student_grade} - الشعبة {student_class}) متأخراً الساعة {current_time}"
    
    # إرسال رسائل (يمكن تفعيلها لاحقاً)
    if student_phone and student_phone != '':
        send_message_to_student(student_phone, student_name, status, current_time)
    
    return jsonify({
        "message": result_message,
        "status": status,
        "student_name": student_name,
        "student_grade": student_grade,
        "student_class": student_class,
        "time": current_time,
        "date": current_date
    })

def record_attendance(student_id, student_name, grade, class_name, date, time, status, notes):
    """تسجيل الحضور في ملف CSV"""
    attendance_file = 'attendance.csv'
    
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
    
    if os.path.exists(attendance_file):
        df_existing = pd.read_csv(attendance_file)
        df_combined = pd.concat([df_existing, df_new], ignore_index=True)
        df_combined.to_csv(attendance_file, index=False, encoding='utf-8-sig')
    else:
        df_new.to_csv(attendance_file, index=False, encoding='utf-8-sig')
    
    print(f"تم تسجيل الحضور: {student_name} - {status} في {time}")

def send_message_to_student(phone, name, status, time):
    """إرسال رسالة للطالب (تستطيع تعديلها لاحقاً حسب الخدمة المستخدمة)"""
    # هذا مجرد مثال - يمكنك إضافة خدمة رسائل حقيقية مثل Twilio أو WhatsApp API
    
    message = f"مرحباً {name}، تم تسجيل حضورك {status} الساعة {time}"
    
    # طباعة للاختبار فقط
    print(f"📱 جاري إرسال رسالة إلى {phone}: {message}")
    
    # هنا يمكنك إضافة كود الإرسال الفعلي
    # مثال باستخدام Twilio:
    # from twilio.rest import Client
    # client = Client(account_sid, auth_token)
    # client.messages.create(body=message, from_='+1234567890', to=phone)
    
    return True

# API للحصول على تقارير الحضور (اختياري)
@app.route("/api/attendance/<date>", methods=["GET"])
def get_attendance_by_date(date):
    """الحصول على تقرير الحضور لتاريخ محدد"""
    attendance_file = 'attendance.csv'
    
    if not os.path.exists(attendance_file):
        return jsonify({"error": "لا توجد بيانات حضور"}), 404
    
    df = pd.read_csv(attendance_file)
    df['date'] = df['date'].astype(str)
    
    date_attendance = df[df['date'] == date]
    
    if date_attendance.empty:
        return jsonify({"message": f"لا توجد بيانات حضور لتاريخ {date}"}), 404
    
    # إحصائيات الحضور
    total_students = len(date_attendance)
    on_time = len(date_attendance[date_attendance['status'] == 'حاضر في الوقت'])
    late = len(date_attendance[date_attendance['status'] == 'متأخر'])
    
    return jsonify({
        "date": date,
        "total": total_students,
        "on_time": on_time,
        "late": late,
        "attendance_list": date_attendance.to_dict('records')
    })

# API لإضافة طالب جديد (اختياري)
@app.route("/api/add_student", methods=["POST"])
def add_student():
    """إضافة طالب جديد إلى ملف Excel"""
    data = request.get_json()
    
    students_df = load_students_data()
    
    new_student = pd.DataFrame([{
        'student_id': str(data.get('student_id')),
        'name': data.get('name'),
        'grade': data.get('grade'),
        'class': data.get('class'),
        'phone': data.get('phone', ''),
        'notes': data.get('notes', '')
    }])
    
    if students_df is None:
        new_student.to_excel('students.xlsx', index=False)
    else:
        updated_df = pd.concat([students_df, new_student], ignore_index=True)
        updated_df.to_excel('students.xlsx', index=False)
    
    return jsonify({"message": "تم إضافة الطالب بنجاح"})

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
