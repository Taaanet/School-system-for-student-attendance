from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import pandas as pd
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)

# ============== دوال مساعدة ==============

def load_students_data():
    """تحميل بيانات الطلاب من ملف Excel"""
    try:
        if not os.path.exists('students.xlsx'):
            # إنشاء ملف تجريبي إذا لم يكن موجوداً
            test_data = pd.DataFrame({
                'student_id': ['1', '2', '3', '001', '002', '003'],
                'name': ['أحمد محمد', 'سارة علي', 'محمد خالد', 'نورا أحمد', 'عمر وليد', 'ليلى محمود'],
                'grade': ['الأول الثانوي', 'الأول الثانوي', 'الثاني الثانوي', 'الأول الثانوي', 'الثاني الثانوي', 'الثالث الثانوي'],
                'class': ['أ', 'ب', 'أ', 'ج', 'ب', 'أ'],
                'phone': ['', '', '', '', '', ''],
                'notes': ['', '', '', '', '', '']
            })
            test_data.to_excel('students.xlsx', index=False)
            print("✅ تم إنشاء ملف students.xlsx تجريبي")
        
        df = pd.read_excel('students.xlsx')
        df['student_id'] = df['student_id'].astype(str).str.strip()
        return df
    except Exception as e:
        print(f"خطأ: {e}")
        return None

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

# ============== معالجة المسح ==============

@app.route("/process_scan", methods=["POST"])
def process_scan():
    try:
        data = request.get_json()
        qr_data = data.get("qr_data", "").strip()
        
        print(f"📱 تم مسح: '{qr_data}'")
        
        # تحميل بيانات الطلاب
        students_df = load_students_data()
        
        if students_df is None:
            return jsonify({
                "success": False,
                "message": "⚠️ خطأ في قاعدة البيانات"
            })
        
        # البحث المباشر
        student = students_df[students_df['student_id'] == qr_data]
        
        # إذا لم يجد، جرب كرقم
        if student.empty and qr_data.isdigit():
            # جرب بدون أصفار
            as_int = str(int(qr_data))
            student = students_df[students_df['student_id'] == as_int]
            
            # جرب مع أصفار لثلاث خانات
            if student.empty:
                with_zeros = qr_data.zfill(3)
                student = students_df[students_df['student_id'] == with_zeros]
        
        if student.empty:
            # طباعة المعرفات المتاحة للتصحيح
            available = students_df['student_id'].tolist()
            print(f"المعرفات المتاحة: {available}")
            
            return jsonify({
                "success": False,
                "message": f"❌ لم يتم العثور على طالب بالرقم: '{qr_data}'\n\nالمعرفات المتاحة: {', '.join(available[:5])}",
                "scanned": qr_data,
                "available": available[:5]
            })
        
        # استخراج البيانات
        student = student.iloc[0]
        now = datetime.now()
        
        result = {
            "success": True,
            "status_icon": "✅",
            "student_name": student['name'],
            "student_grade": student['grade'],
            "student_class": student['class'],
            "time": now.strftime("%H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "student_id": str(student['student_id']),
            "message": f"✅ مرحباً {student['name']} - تم تسجيل حضورك"
        }
        
        # حفظ attendance
        attendance_data = pd.DataFrame([{
            'student_id': result['student_id'],
            'student_name': result['student_name'],
            'grade': result['student_grade'],
            'class': result['student_class'],
            'date': result['date'],
            'time': result['time'],
            'status': 'حاضر'
        }])
        
        if os.path.exists('attendance.csv'):
            existing = pd.read_csv('attendance.csv')
            combined = pd.concat([existing, attendance_data], ignore_index=True)
            combined.to_csv('attendance.csv', index=False, encoding='utf-8-sig')
        else:
            attendance_data.to_csv('attendance.csv', index=False, encoding='utf-8-sig')
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return jsonify({
            "success": False,
            "message": f"خطأ: {str(e)}"
        })

if __name__ == "__main__":
    print("="*50)
    print("🚀 تشغيل النظام - نسخة مبسطة للاختبار")
    print("="*50)
    app.run(debug=True, host='0.0.0.0', port=5000)
