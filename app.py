from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from datetime import datetime
import os
from pymongo import MongoClient

app = Flask(__name__)
CORS(app)

# ============== الاتصال بقاعدة البيانات ==============
MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://taanet_db_user:4oCJjCk5KDYFF6Xh@cluster0.mlvuoaw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0')

client = MongoClient(MONGO_URI)
db = client['attendance_system']
students_collection = db['students']
attendance_collection = db['attendance']

# ============== إعدادات النظام ==============
ATTENDANCE_DEADLINE = "07:30:00"

def init_database():
    """تهيئة قاعدة البيانات ببيانات تجريبية"""
    if students_collection.count_documents({}) == 0:
        sample_students = [
            {'student_id': '1150436838', 'name': 'عبدالله فيصل شندي', 'grade': 'الأول الثانوي', 'class': 'أ'},
            {'student_id': '1152217368', 'name': 'أحمد محمد علي', 'grade': 'الأول الثانوي', 'class': 'ب'},
            {'student_id': '1152327969', 'name': 'سارة خالد عبدالله', 'grade': 'الثاني الثانوي', 'class': 'أ'},
            {'student_id': '1152502371', 'name': 'محمد إبراهيم', 'grade': 'الثاني الثانوي', 'class': 'ج'},
            {'student_id': '1153472889', 'name': 'نورة سعيد', 'grade': 'الثالث الثانوي', 'class': 'أ'}
        ]
        students_collection.insert_many(sample_students)
        print("✅ تم إضافة بيانات الطلاب إلى MongoDB")

def get_attendance_status():
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    if current_time <= ATTENDANCE_DEADLINE:
        return "حاضر", current_time
    else:
        return "متأخر", current_time

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
        
        student = students_collection.find_one({'student_id': student_id})
        if not student:
            return jsonify({"success": False, "message": f"الطالب {student_id} غير موجود"})
        
        status, current_time = get_attendance_status()
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        existing = attendance_collection.find_one({'student_id': student_id, 'date': current_date})
        if existing:
            return jsonify({
                "success": True,
                "message": f"⚠️ {student['name']} مسجل مسبقاً اليوم",
                "already_registered": True,
                "student_name": student['name'],
                "student_grade": student['grade'],
                "student_class": student['class'],
                "time": current_time,
                "date": current_date
            })
        
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
            "message": f"✅ تم تسجيل {student['name']} - {status} الساعة {current_time}",
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
    today = datetime.now().strftime("%Y-%m-%d")
    total = students_collection.count_documents({})
    present = attendance_collection.count_documents({'date': today, 'status': 'حاضر'})
    late = attendance_collection.count_documents({'date': today, 'status': 'متأخر'})
    absent = total - (present + late)
    percent = round((present + late) / total * 100, 1) if total > 0 else 0
    
    return jsonify({
        "success": True,
        "total_students": total,
        "present": present,
        "late": late,
        "absent": absent,
        "percentage": percent,
        "date": today
    })

@app.route("/api/attendance_details/<date>")
def attendance_details(date):
    all_students = list(students_collection.find({}, {'_id': 0, 'student_id': 1, 'name': 1, 'grade': 1, 'class': 1}))
    attendance_records = {rec['student_id']: rec for rec in attendance_collection.find({'date': date})}
    
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
    
    present = len([s for s in result if s['status'] == 'حاضر'])
    late = len([s for s in result if s['status'] == 'متأخر'])
    absent = len([s for s in result if s['status'] == 'غائب'])
    
    return jsonify({
        "success": True,
        "data": result,
        "present": present,
        "late": late,
        "absent": absent
    })

@app.route("/api/absent_students_today")
def absent_students_today():
    today = datetime.now().strftime("%Y-%m-%d")
    present_ids = set(rec['student_id'] for rec in attendance_collection.find({'date': today}))
    all_students = list(students_collection.find({}, {'_id': 0, 'student_id': 1, 'name': 1, 'grade': 1, 'class': 1}))
    absent = [s for s in all_students if s['student_id'] not in present_ids]
    return jsonify({"success": True, "data": absent})

@app.route("/api/top_students")
def top_students():
    pipeline = [
        {'$match': {'status': 'حاضر'}},
        {'$group': {'_id': '$student_name', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 10}
    ]
    result = [{'name': item['_id'], 'count': item['count']} for item in attendance_collection.aggregate(pipeline)]
    return jsonify({"success": True, "data": result})

@app.route("/api/student_report/<student_id>")
def student_report(student_id):
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

if __name__ == "__main__":
    init_database()
    port = int(os.environ.get("PORT", 5000))
    print("🚀 نظام الحضور يعمل مع MongoDB!")
    app.run(host='0.0.0.0', port=port, debug=False)