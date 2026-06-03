from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os
import pandas as pd
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)

# ============== الاتصال بقاعدة البيانات MongoDB ==============
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://taanet_db_user:4oCJjCk5KDYFF6Xh@cluster0.mlvuoaw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')

client = MongoClient(MONGO_URI)
db = client['attendance_system']
students_collection = db['students']
attendance_collection = db['attendance']

# ============== إعدادات النظام ==============
ATTENDANCE_DEADLINE = "07:30:00"  # 7:30 صباحاً

# ============== دوال مساعدة ==============

def load_students_from_excel():
    """تحميل الطلاب من ملف Excel إلى MongoDB"""
    try:
        # البحث عن ملف Excel
        excel_file = None
        for file in os.listdir('.'):
            if file.endswith(('.xlsx', '.xls')):
                excel_file = file
                break
        
        if not excel_file:
            print("❌ لا يوجد ملف Excel")
            return False
        
        # قراءة الملف
        df = pd.read_excel(excel_file)
        
        # تحويل البيانات
        students = []
        for _, row in df.iterrows():
            students.append({
                'student_id': str(row['student_id']).strip(),
                'name': str(row['name']),
                'grade': str(row['grade']),
                'class': str(row['class']),
                'phone': str(row.get('phone', '')),
                'notes': str(row.get('notes', ''))
            })
        
        # حفظ في MongoDB
        students_collection.drop()
        students_collection.insert_many(students)
        print(f"✅ تم تحميل {len(students)} طالب")
        return True
    except Exception as e:
        print(f"❌ خطأ: {e}")
        return False

def get_attendance_status():
    """تحديد حالة الحضور حسب الوقت"""
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    if current_time <= ATTENDANCE_DEADLINE:
        return "حاضر", current_time
    else:
        return "متأخر", current_time

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

# ============== API التسجيل ==============

@app.route("/api/register", methods=["POST"])
def register_attendance():
    try:
        data = request.get_json()
        student_id = str(data.get("student_id", "")).strip()
        
        if not student_id:
            return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب"})
        
        # البحث عن الطالب
        student = students_collection.find_one({'student_id': student_id})
        if not student:
            return jsonify({"success": False, "message": f"الطالب {student_id} غير موجود"})
        
        status, current_time = get_attendance_status()
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        # منع التسجيل أكثر من مرة
        existing = attendance_collection.find_one({
            'student_id': student_id, 
            'date': current_date
        })
        
        if existing:
            return jsonify({
                "success": False,
                "message": f"⚠️ {student['name']} مسجل مسبقاً اليوم الساعة {existing['time']}",
                "already_registered": True,
                "student_name": student['name'],
                "student_grade": student['grade'],
                "student_class": student['class']
            })
        
        # تسجيل الحضور
        attendance_collection.insert_one({
            'student_id': student_id,
            'student_name': student['name'],
            'grade': student['grade'],
            'class': student['class'],
            'date': current_date,
            'time': current_time,
            'status': status
        })
        
        return jsonify({
            "success": True,
            "message": f"✅ تم تسجيل حضور {student['name']} - {status} الساعة {current_time}",
            "student_name": student['name'],
            "student_grade": student['grade'],
            "student_class": student['class'],
            "time": current_time,
            "date": current_date,
            "status": status
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ============== API التقارير ==============

@app.route("/api/students_list")
def students_list():
    students = list(students_collection.find({}, {'_id': 0, 'student_id': 1, 'name': 1, 'grade': 1, 'class': 1}))
    return jsonify({"success": True, "data": students})

@app.route("/api/attendance_summary")
def attendance_summary():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        total = students_collection.count_documents({})
        
        today_records = list(attendance_collection.find({'date': today}))
        present = len([r for r in today_records if r['status'] == 'حاضر'])
        late = len([r for r in today_records if r['status'] == 'متأخر'])
        absent = total - (present + late)
        percentage = round(((present + late) / total) * 100, 1) if total > 0 else 0
        
        return jsonify({
            "success": True,
            "total_students": total,
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
        all_students = list(students_collection.find({}, {'_id': 0, 'student_id': 1, 'name': 1, 'grade': 1, 'class': 1}))
        
        attendance_records = {}
        for rec in attendance_collection.find({'date': date}):
            attendance_records[rec['student_id']] = rec
        
        result = []
        for student in all_students:
            rec = attendance_records.get(student['student_id'])
            result.append({
                'student_id': student['student_id'],
                'student_name': student['name'],
                'grade': student['grade'],
                'class': student['class'],
                'status': rec['status'] if rec else 'غائب',
                'time': rec['time'] if rec else '-'
            })
        
        return jsonify({
            "success": True,
            "data": result,
            "present": len([s for s in result if s['status'] == 'حاضر']),
            "late": len([s for s in result if s['status'] == 'متأخر']),
            "absent": len([s for s in result if s['status'] == 'غائب'])
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/absent_students_today")
def absent_students_today():
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        present_ids = set(rec['student_id'] for rec in attendance_collection.find({'date': today}))
        all_students = list(students_collection.find({}, {'_id': 0, 'student_id': 1, 'name': 1, 'grade': 1, 'class': 1}))
        absent = [s for s in all_students if s['student_id'] not in present_ids]
        return jsonify({"success": True, "data": absent})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/top_students")
def top_students():
    try:
        pipeline = [
            {'$match': {'status': 'حاضر'}},
            {'$group': {'_id': '$student_name', 'count': {'$sum': 1}}},
            {'$sort': {'count': -1}},
            {'$limit': 10}
        ]
        result = [{'name': item['_id'], 'count': item['count']} for item in attendance_collection.aggregate(pipeline)]
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/student_report/<student_id>")
def student_report(student_id):
    try:
        student = students_collection.find_one({'student_id': student_id})
        if not student:
            return jsonify({"success": False, "error": "الطالب غير موجود"})
        
        records = list(attendance_collection.find(
            {'student_id': student_id},
            {'_id': 0, 'date': 1, 'time': 1, 'status': 1}
        ).sort('date', -1))
        
        present = len([r for r in records if r['status'] == 'حاضر'])
        late = len([r for r in records if r['status'] == 'متأخر'])
        total = len(records)
        
        return jsonify({
            "success": True,
            "student_name": student['name'],
            "student_id": student_id,
            "grade": student['grade'],
            "class": student['class'],
            "total_days": total,
            "present": present,
            "late": late,
            "absent": total - (present + late),
            "attendance_rate": round((present + late) / total * 100, 1) if total > 0 else 0,
            "records": records
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

# ============== API الإدارة ==============

@app.route("/api/load_excel")
def load_excel():
    """تحميل بيانات Excel إلى MongoDB"""
    try:
        excel_file = None
        for file in os.listdir('.'):
            if file.endswith(('.xlsx', '.xls')):
                excel_file = file
                break
        
        if not excel_file:
            return jsonify({"success": False, "message": "لا يوجد ملف Excel"})
        
        df = pd.read_excel(excel_file)
        students = []
        for _, row in df.iterrows():
            students.append({
                'student_id': str(row['student_id']).strip(),
                'name': str(row['name']),
                'grade': str(row['grade']),
                'class': str(row['class']),
                'phone': str(row.get('phone', '')),
                'notes': str(row.get('notes', ''))
            })
        
        students_collection.drop()
        students_collection.insert_many(students)
        
        return jsonify({"success": True, "message": f"✅ تم تحميل {len(students)} طالب", "count": len(students)})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/list_files")
def list_files():
    """عرض قائمة الملفات"""
    files = [f for f in os.listdir('.') if not f.startswith('.')]
    return jsonify({"success": True, "files": files})

@app.route("/api/clear_attendance")
def clear_attendance():
    """مسح سجلات الحضور"""
    result = attendance_collection.delete_many({})
    return jsonify({"success": True, "message": f"تم مسح {result.deleted_count} سجل"})

@app.route("/api/stats")
def stats():
    """إحصائيات قاعدة البيانات"""
    return jsonify({
        "success": True,
        "students_count": students_collection.count_documents({}),
        "attendance_count": attendance_collection.count_documents({})
    })

# ============== التشغيل ==============
if __name__ == "__main__":
    # محاولة تحميل البيانات عند التشغيل
    if students_collection.count_documents({}) == 0:
        load_students_from_excel()
    
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)