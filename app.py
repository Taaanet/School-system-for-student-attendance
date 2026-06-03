from flask import Flask, render_template, request, jsonify
from flask_cors import CORS  # أضف هذا السطر الجديد
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)  # أضف هذا السطر الجديد لتمكين CORS

# تحميل بيانات الطلاب من ملف Excel
def load_students_data():
    try:
        df = pd.read_excel('students.xlsx')
        df['student_id'] = df['student_id'].astype(str)
        return df
    except Exception as e:
        print(f"خطأ في تحميل ملف Excel: {e}")
        return None

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/scan")
def scan():
    return render_template("scan.html")

# تعديل مسار معالجة المسح ليقبل طرق مختلفة
@app.route("/process_scan", methods=["POST", "GET"])
def process_scan():
    # دعم كل من POST و GET للتأكد من استقبال البيانات
    if request.method == "POST":
        data = request.get_json()
        if data:
            qr_data = data.get("qr_data")
        else:
            qr_data = request.form.get("qr_data")
    else:  # GET
        qr_data = request.args.get("qr_data")
    
    print(f"📱 تم استلام البيانات: {qr_data}")  # للتصحيح
    
    if not qr_data:
        return jsonify({
            "message": "لم يتم استلام بيانات QR",
            "status": "error"
        })
    
    student_id = str(qr_data).strip()
    
    # تحميل بيانات الطلاب
    students_df = load_students_data()
    
    if students_df is None:
        return jsonify({
            "message": "⚠️ خطأ في قاعدة بيانات الطلاب",
            "status": "error"
        })
    
    # البحث عن الطالب
    student = students_df[students_df['student_id'] == student_id]
    
    if student.empty:
        return jsonify({
            "message": f"⚠️ لم يتم العثور على طالب بالرقم: {student_id}",
            "status": "error"
        })
    
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
    
    # تحديد وقت الحضور المحدد (8:30 صباحاً)
    attendance_deadline = "08:30:00"
    
    # تحديد الحضور أو التأخير
    if current_time <= attendance_deadline:
        status = "حاضر في الوقت"
        status_icon = "✅"
    else:
        status = "متأخر"
        status_icon = "⏰"
    
    # تسجيل الحضور
    record_attendance(student_id, student_name, student_grade, student_class, 
                     current_date, current_time, status, student_notes)
    
    # تجهيز رسالة النتيجة
    if status == "حاضر في الوقت":
        result_message = f"{status_icon} تم تسجيل حضور {student_name} (الصف {student_grade} - الشعبة {student_class}) في الوقت المحدد {current_time}"
    else:
        result_message = f"{status_icon} تم تسجيل حضور {student_name} (الصف {student_grade} - الشعبة {student_class}) متأخراً الساعة {current_time}"
    
    # إرسال الرد
    response_data = {
        "message": result_message,
        "status": status,
        "student_name": student_name,
        "student_grade": student_grade,
        "student_class": student_class,
        "time": current_time,
        "date": current_date,
        "student_id": student_id
    }
    
    print(f"✅ جاري إرسال الرد: {response_data}")  # للتصحيح
    return jsonify(response_data)

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
    
    print(f"💾 تم تسجيل الحضور: {student_name} - {status} في {time}")

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
