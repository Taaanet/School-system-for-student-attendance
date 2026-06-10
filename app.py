from flask import Flask, render_template, request, jsonify, session, redirect, url_for, send_file, make_response
from flask_cors import CORS
from flask_mail import Mail, Message
from datetime import datetime, timedelta, time
import os
import json
import pandas as pd
from supabase import create_client
from dotenv import load_dotenv
from functools import wraps
from calendar import monthrange
import qrcode
from io import BytesIO
import base64
import threading
import time as time_module
import hashlib
import platform
import subprocess
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

load_dotenv()

app = Flask(__name__)

# ============== إعداد JSON للغة العربية ==============
app.config['JSON_AS_ASCII'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = True

# ============== إعداد Supabase ==============
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise Exception("SUPABASE_URL أو SUPABASE_KEY غير موجودين في ملف .env")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key-here-change-in-production')
CORS(app)

# ============== إعدادات واتساب (Twilio) ==============
TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_WHATSAPP_NUMBER = os.environ.get('TWILIO_WHATSAPP_NUMBER', '')

if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
    try:
        from twilio.rest import Client
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        twilio_enabled = True
    except:
        twilio_enabled = False
else:
    twilio_enabled = False

# ============== دعم اللغة الإنجليزية ==============
def get_language():
    return session.get('language', 'ar')

def set_language(lang):
    session['language'] = lang

# ============== دوال قراءة البيانات من Supabase ==============
def get_live_students():
    try:
        response = supabase.table("students").select("*").execute()
        return response.data or []
    except Exception as e:
        print(f"❌ خطأ Supabase: {e}")
        return []

def get_live_attendance():
    try:
        result = supabase.table("attendance").select("*").execute()
        return result.data or []
    except Exception as e:
        print(f"❌ خطأ قراءة الحضور: {e}")
        return []

def save_attendance(record):
    try:
        result = supabase.table("attendance").insert(record).execute()
        return True
    except Exception as e:
        print(f"❌ خطأ حفظ الحضور: {e}")
        return False

# ============== إرسال رسائل واتساب ==============
def send_whatsapp_message(to_number, student_name, status, attendance_time):
    try:
        if not twilio_enabled:
            return False, "خدمة واتساب غير مفعلة"

        message_body = f"""
🎓 *نظام حضور الطلاب*

👤 *الطالب:* {student_name}
✅ *الحالة:* {status}
⏰ *الوقت:* {attendance_time}
📅 *التاريخ:* {datetime.now().strftime('%Y-%m-%d')}

تم تسجيل حضور الطالب بنجاح.
"""
        message = twilio_client.messages.create(
            body=message_body,
            from_=TWILIO_WHATSAPP_NUMBER,
            to=f"whatsapp:{to_number}"
        )
        return True, "تم الإرسال"
    except Exception as e:
        print(f"❌ خطأ واتساب: {e}")
        return False, str(e)

# ============== إنشاء كود QR ==============
def generate_qr_code(student_id, student_name):
    attendance_url = f"https://school-system-for-student-attendance.onrender.com/scan?student_id={student_id}"

    qr = qrcode.QRCode(version=1, box_size=4, border=2)
    qr.add_data(attendance_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")

    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.b64encode(buffered.getvalue()).decode()

    return f"data:image/png;base64,{img_str}"

# ============== النسخ الاحتياطي التلقائي ==============
def create_backup():
    try:
        backup_dir = "backups"
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        students = get_live_students()
        students_df = pd.DataFrame(students)
        students_df.to_excel(f"{backup_dir}/students_backup_{timestamp}.xlsx", index=False)

        attendance = get_live_attendance()
        attendance_df = pd.DataFrame(attendance)
        attendance_df.to_excel(f"{backup_dir}/attendance_backup_{timestamp}.xlsx", index=False)

        print(f"✅ تم إنشاء نسخة احتياطية في {timestamp}")
        return True, f"تم إنشاء النسخة {timestamp}"
    except Exception as e:
        print(f"❌ خطأ في النسخ الاحتياطي: {e}")
        return False, str(e)

def scheduled_backup():
    while True:
        time_module.sleep(86400)
        create_backup()

# ============== التوقيت السعودي ==============
def get_saudi_time():
    return datetime.utcnow() + timedelta(hours=3)

def is_weekend(date):
    return date.weekday() == 4 or date.weekday() == 5

def can_register_attendance():
    now = get_saudi_time()
    if is_weekend(now.date()):
        return False, "لا يمكن تسجيل الحضور في أيام العطلات (الجمعة والسبت)"
    return True, None

def get_attendance_status():
    now = get_saudi_time()
    current_time = now.strftime("%H:%M:%S")
    return ("حاضر في الوقت", current_time) if current_time <= "07:30:00" else ("متأخر", current_time)

# ============== البريد الإلكتروني ==============
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = 'taaanet@gmail.com'
app.config['MAIL_PASSWORD'] = os.environ.get('EMAIL_PASSWORD', '')
app.config['MAIL_DEFAULT_SENDER'] = 'taaanet@gmail.com'

mail = Mail(app)

def send_report_email(recipient, subject, body, attachment_path=None):
    try:
        if not app.config['MAIL_PASSWORD']:
            return False, "كلمة مرور البريد غير مضبوطة"
        msg = Message(subject, recipients=[recipient])
        msg.html = body
        if attachment_path and os.path.exists(attachment_path):
            with app.open_resource(attachment_path) as fp:
                msg.attach(os.path.basename(attachment_path), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', fp.read())
        mail.send(msg)
        return True, "تم الإرسال"
    except Exception as e:
        return False, str(e)

# ============== دوال تشفير كلمات المرور ==============
def hash_password(password):
    """تشفير كلمة المرور"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, hashed):
    """التحقق من كلمة المرور"""
    return hash_password(password) == hashed

# ============== دوال الحماية والتشفير (Device Licensing) ==============
SECRET_KEY_FOR_LICENSES = hashlib.sha256(b"Your-Super-Secret-Key-For-Licensing-2024-Taha").digest()

def get_hardware_id():
    """يُولد مُعرّفاً فريداً للجهاز بناءً على مكونات الهاردوير الأساسية"""
    system = platform.system().lower()
    unique_id_parts = []

    try:
        if system == "windows":
            board_serial = subprocess.check_output("wmic baseboard get serialnumber", shell=True, text=True).strip().split("\n")[1].strip()
            cpu_id = subprocess.check_output("wmic cpu get processorid", shell=True, text=True).strip().split("\n")[1].strip()
            unique_id_parts = [board_serial, cpu_id]
        else:
            import uuid
            unique_id_parts = [str(uuid.getnode())]
    except Exception as e:
        print(f"⚠️ فشل في قراءة معرف الجهاز: {e}")
        import uuid
        unique_id_parts = [str(uuid.uuid4())]

    combined_string = "|".join(unique_id_parts)
    hardware_hash = hashlib.sha256(combined_string.encode()).hexdigest()
    return hardware_hash

def encrypt_activation_code(hardware_id, expiration_date):
    """تشفير معرف الجهاز وتاريخ انتهاء الصلاحية إلى رمز تفعيل"""
    data = f"{hardware_id}|{expiration_date.isoformat()}"
    cipher = AES.new(SECRET_KEY_FOR_LICENSES, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(data.encode(), AES.block_size))
    iv = base64.b64encode(cipher.iv).decode('utf-8')
    ct = base64.b64encode(ct_bytes).decode('utf-8')
    return f"{iv}${ct}"

def decrypt_activation_code(activation_code):
    """فك تشفير رمز التفعيل لاستخراج معرف الجهاز وتاريخ الانتهاء"""
    try:
        iv_b64, ct_b64 = activation_code.split('$')
        iv = base64.b64decode(iv_b64)
        ct = base64.b64decode(ct_b64)
        cipher = AES.new(SECRET_KEY_FOR_LICENSES, AES.MODE_CBC, iv=iv)
        pt = unpad(cipher.decrypt(ct), AES.block_size).decode()
        hardware_id, expiration_date_str = pt.split('|')
        return hardware_id, datetime.fromisoformat(expiration_date_str)
    except Exception as e:
        print(f"خطأ في فك تشفير رمز التفعيل: {e}")
        return None, None

def check_device_license():
    """تتحقق مما إذا كان الجهاز الحالي مرخصاً لاستخدام التطبيق"""
    current_hardware_id = get_hardware_id()
    if not current_hardware_id:
        return False

    try:
        result = supabase.table("device_licenses").select("expires_at").eq("hardware_id", current_hardware_id).execute()
        if result.data:
            expiry_date = datetime.fromisoformat(result.data[0]['expires_at'])
            if expiry_date > datetime.now():
                return True
            else:
                return False
    except Exception as e:
        print(f"⚠️ خطأ في الاتصال بقاعدة بيانات التراخيص: {e}")
        return False

    return False

def license_required(f):
    """ديكورator لحماية الصفحات، يمنع الوصول إذا لم يكن الجهاز مرخصاً"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # السماح بالوصول إلى صفحات الترخيص والمصادقة
        allowed_paths = [
            '/login', 
            '/logout',
            '/request_activation', 
            '/activate_device',
            '/admin/licenses',
            '/api/admin/',
            '/static/',
            '/test_supabase',
            '/health'
        ]
        for path in allowed_paths:
            if request.path.startswith(path):
                return f(*args, **kwargs)

        if 'logged_in' not in session:
            return redirect(url_for('login'))

        if not check_device_license():
            try:
                supabase.table("security_logs").insert({
                    "hardware_id": get_hardware_id(),
                    "ip_address": request.remote_addr,
                    "attempted_path": request.path
                }).execute()
            except:
                pass
            return redirect(url_for('activation_required_page'))
        return f(*args, **kwargs)
    return decorated_function

# ============== إدارة المستخدمين المتقدمة ==============
USERS_FILE = 'users.json'

def load_users():
    try:
        if os.path.exists(USERS_FILE):
            with open(USERS_FILE, 'r', encoding='utf-8') as f:
                users = json.load(f)
                updated = False
                for username, data in users.items():
                    if 'max_logins' in data:
                        if isinstance(data['max_logins'], str):
                            try:
                                if data['max_logins'] in ['null', '', 'None']:
                                    data['max_logins'] = None
                                else:
                                    data['max_logins'] = int(data['max_logins'])
                                updated = True
                            except:
                                data['max_logins'] = 5
                                updated = True
                    if 'login_count' in data and isinstance(data['login_count'], str):
                        try:
                            data['login_count'] = int(data['login_count'])
                            updated = True
                        except:
                            data['login_count'] = 0
                            updated = True
                if updated:
                    save_users(users)
                return users
    except:
        pass

    default_users = {
        'Taha_Mohamed': {'password': hash_password('hetaonet0hros'), 'role': 'admin', 'login_count': 0, 'max_logins': None},
        'admin': {'password': hash_password('admin123'), 'role': 'user', 'login_count': 0, 'max_logins': 5}
    }
    save_users(default_users)
    return default_users

def save_users(users):
    try:
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump(users, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"خطأ: {e}")

def can_login(username):
    users = load_users()
    if username not in users:
        return False, "اسم المستخدم غير موجود"
    user = users[username]
    if user['role'] == 'admin':
        return True, None
    if user['max_logins'] is not None and user['login_count'] >= user['max_logins']:
        return False, f"لقد تجاوزت الحد المسموح به ({user['max_logins']} مرات)"
    return True, None

def increment_login_count(username):
    users = load_users()
    if username in users and users[username]['role'] != 'admin':
        users[username]['login_count'] = users[username].get('login_count', 0) + 1
        save_users(users)

def get_remaining_logins(username):
    users = load_users()
    if username not in users:
        return 0
    user = users[username]
    if user.get('role') == 'admin':
        return "غير محدود"
    
    max_logins = user.get('max_logins', 5)
    used = user.get('login_count', 0)
    
    try:
        if max_logins is None or str(max_logins).lower() in ['null', 'none', '']:
            max_logins = 5
        else:
            max_logins = int(str(max_logins))
        
        if used is None or str(used).lower() in ['null', 'none', '']:
            used = 0
        else:
            used = int(str(used))
        
        remaining = max_logins - used
        if remaining < 0:
            return 0
        return remaining
    except:
        return 0

def create_user(username, password, role='user', max_logins=5):
    """إنشاء مستخدم جديد مع صلاحيات"""
    users = load_users()
    
    if username in users:
        return False, "اسم المستخدم موجود بالفعل"
    
    if role not in ['user', 'editor', 'admin']:
        role = 'user'
    
    users[username] = {
        'password': hash_password(password),
        'role': role,
        'login_count': 0,
        'max_logins': max_logins if role != 'admin' else None
    }
    
    save_users(users)
    
    role_names = {'user': 'معلم (قراءة فقط)', 'editor': 'محرر (إضافة وتعديل)', 'admin': 'مدير (كامل الصلاحيات)'}
    return True, f"تم إنشاء المستخدم {username} كـ {role_names[role]}"

def update_user(username, role=None, max_logins=None, password=None):
    """تحديث بيانات المستخدم"""
    users = load_users()
    
    if username not in users:
        return False, "المستخدم غير موجود"
    
    if username == 'Taha_Mohamed':
        return False, "لا يمكن تعديل حساب المدير الأساسي"
    
    if role:
        users[username]['role'] = role
        if role == 'admin':
            users[username]['max_logins'] = None
        elif max_logins:
            users[username]['max_logins'] = max_logins
    
    if max_logins and users[username]['role'] != 'admin':
        users[username]['max_logins'] = max_logins
    
    if password:
        users[username]['password'] = hash_password(password)
    
    save_users(users)
    return True, "تم تحديث المستخدم بنجاح"

def delete_user(username):
    """حذف مستخدم"""
    users = load_users()
    
    if username == 'Taha_Mohamed':
        return False, "لا يمكن حذف حساب المدير الأساسي"
    
    if username not in users:
        return False, "المستخدم غير موجود"
    
    del users[username]
    save_users(users)
    return True, "تم حذف المستخدم بنجاح"

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# ============== صفحات المصادقة ==============
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        users = load_users()
        
        if username in users:
            stored_password = users[username]['password']
            if stored_password == password or verify_password(password, stored_password):
                can_login_flag, message = can_login(username)
                if not can_login_flag:
                    return render_template('login.html', error=message)
                increment_login_count(username)
                session['logged_in'] = True
                session['username'] = username
                session['role'] = users[username]['role']
                session['remaining_logins'] = get_remaining_logins(username)
                return redirect(url_for('home'))
        
        return render_template('login.html', error="اسم المستخدم أو كلمة المرور غير صحيحة")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ============== صفحات الترخيص والحماية ==============
@app.route('/activation_required')
def activation_required_page():
    return render_template('activation_required.html')

@app.route('/request_activation')
def request_activation_page():
    hardware_id = get_hardware_id()
    return render_template('request_activation.html', hardware_id=hardware_id)

@app.route('/activate_device', methods=['GET', 'POST'])
def activate_device_page():
    if request.method == 'POST':
        activation_code = request.form.get('activation_code')
        hardware_id, expiry_date = decrypt_activation_code(activation_code)
        current_hardware_id = get_hardware_id()

        if not hardware_id or not expiry_date:
            return render_template('activate_device.html', error="رمز التفعيل غير صالح.")

        if hardware_id != current_hardware_id:
            return render_template('activate_device.html', error="هذا الرمز مخصص لجهاز آخر. يرجى مراجعة مدير النظام.")

        if expiry_date < datetime.now():
            return render_template('activate_device.html', error="هذا الرمز منتهي الصلاحية.")

        try:
            supabase.table("device_licenses").upsert({
                "hardware_id": hardware_id,
                "activation_code": activation_code,
                "expires_at": expiry_date.isoformat()
            }, on_conflict="hardware_id").execute()
            return render_template('activate_device.html', success="تم تفعيل الجهاز بنجاح!")
        except Exception as e:
            return render_template('activate_device.html', error=f"حدث خطأ في قاعدة البيانات: {e}")

    return render_template('activate_device.html')

@app.route('/admin/licenses')
@login_required
def admin_licenses_page():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    try:
        result = supabase.table("device_licenses").select("*").order("created_at", desc=True).execute()
        licenses = result.data
    except Exception as e:
        licenses = []
    return render_template('admin_licenses.html', licenses=licenses)

@app.route('/api/admin/create_license', methods=['POST'])
@login_required
def create_license_api():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"}), 403
    hardware_id = request.form.get('hardware_id')
    validity_days = int(request.form.get('validity_days', 365))

    if not hardware_id:
        return "معرف الجهاز مطلوب.", 400

    expiry_date = datetime.now() + timedelta(days=validity_days)
    activation_code = encrypt_activation_code(hardware_id, expiry_date)

    try:
        supabase.table("device_licenses").insert({
            "hardware_id": hardware_id,
            "activation_code": activation_code,
            "expires_at": expiry_date.isoformat(),
            "created_by": session.get('username')
        }).execute()
        return render_template('admin_licenses_result.html', activation_code=activation_code, hardware_id=hardware_id, expiry_date=expiry_date)
    except Exception as e:
        return f"حدث خطأ أثناء حفظ الترخيص: {e}", 500

@app.route('/api/admin/revoke_license/<int:license_id>')
@login_required
def revoke_license(license_id):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"}), 403
    try:
        supabase.table("device_licenses").delete().eq("id", license_id).execute()
        return redirect(url_for('admin_licenses_page'))
    except Exception as e:
        return f"حدث خطأ أثناء إلغاء الترخيص: {e}", 500

@app.route('/api/admin/check_license')
@login_required
def check_license_api():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"}), 403
    is_licensed = check_device_license()
    return jsonify({"success": True, "is_licensed": is_licensed, "hardware_id": get_hardware_id()})

# ============== APIs إدارة المستخدمين المتقدمة ==============
@app.route("/users_list")
@login_required
def users_list():
    try:
        if session.get('role') != 'admin':
            return redirect(url_for('home'))

        users = load_users()
        users_data = []

        for username, data in users.items():
            role = data.get('role', 'user')
            login_count = data.get('login_count', 0)
            
            try:
                login_count = int(login_count) if login_count is not None else 0
            except (ValueError, TypeError):
                login_count = 0

            if role == 'admin':
                max_logins_display = "غير محدود"
                remaining = "غير محدود"
            else:
                max_logins = data.get('max_logins', 5)
                try:
                    if max_logins is None or str(max_logins).lower() == 'null':
                        max_logins = 5
                    else:
                        max_logins = int(str(max_logins))
                except (ValueError, TypeError):
                    max_logins = 5
                
                max_logins_display = max_logins
                remaining = max_logins - login_count
                if remaining < 0:
                    remaining = 0

            users_data.append({
                'username': username,
                'role': role,
                'login_count': login_count,
                'max_logins': max_logins_display,
                'remaining': remaining
            })

        return render_template('users_list.html', users=users_data)

    except Exception as e:
        print(f"❌ خطأ في صفحة المستخدمين: {e}")
        import traceback
        traceback.print_exc()
        return f"<h1>خطأ في النظام</h1><p>الرجاء المحاولة لاحقاً</p><p>التفاصيل: {str(e)}</p>", 500

@app.route('/reset_logins/<username>')
@login_required
def reset_logins(username):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    users = load_users()
    if username in users:
        if users[username].get('role') == 'admin':
            return jsonify({"success": False, "message": "لا يمكن إعادة تعيين مدير النظام"})
        users[username]['login_count'] = 0
        save_users(users)
        return redirect(url_for('users_list'))
    return jsonify({"success": False, "message": "المستخدم غير موجود"})

@app.route("/api/users")
@login_required
def api_users():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    
    users = load_users()
    users_data = []
    
    for username, data in users.items():
        role = data.get('role', 'user')
        login_count = data.get('login_count', 0)
        
        try:
            login_count = int(login_count) if login_count else 0
        except:
            login_count = 0
        
        if role == 'admin':
            max_logins_display = "غير محدود"
            remaining = "غير محدود"
        else:
            max_logins = data.get('max_logins', 5)
            try:
                max_logins = int(max_logins) if max_logins else 5
            except:
                max_logins = 5
            max_logins_display = max_logins
            remaining = max_logins - login_count
            if remaining < 0:
                remaining = 0
        
        users_data.append({
            'username': username,
            'role': role,
            'login_count': login_count,
            'max_logins': max_logins_display,
            'remaining': remaining
        })
    
    return jsonify({"success": True, "users": users_data})

@app.route("/api/create_user", methods=["POST"])
@login_required
def api_create_user():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role = data.get('role', 'user')
    max_logins = data.get('max_logins', 5)
    
    if not username or not password:
        return jsonify({"success": False, "message": "الرجاء إدخال اسم المستخدم وكلمة المرور"})
    
    if len(password) < 4:
        return jsonify({"success": False, "message": "كلمة المرور يجب أن تكون 4 أحرف على الأقل"})
    
    success, message = create_user(username, password, role, max_logins)
    return jsonify({"success": success, "message": message})

@app.route("/api/update_user/<username>", methods=["PUT"])
@login_required
def api_update_user(username):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    
    data = request.get_json()
    role = data.get('role')
    max_logins = data.get('max_logins')
    password = data.get('password')
    
    success, message = update_user(username, role, max_logins, password)
    return jsonify({"success": success, "message": message})

@app.route("/api/delete_user/<username>", methods=["DELETE"])
@login_required
def api_delete_user(username):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})
    
    success, message = delete_user(username)
    return jsonify({"success": success, "message": message})

# ============== API إدارة الطلاب ==============
@app.route("/api/create_student", methods=["POST"])
@license_required
def api_create_student():
    if session.get('role') not in ['admin', 'editor']:
        return jsonify({"success": False, "message": "غير مصرح - ليس لديك صلاحية الإضافة"})
    
    data = request.get_json()
    student_id = str(data.get('student_id', '')).strip()
    name = data.get('name', '').strip()
    grade = data.get('grade', 'الأول الثانوي')
    class_val = data.get('class', '1')
    phone = data.get('phone', '')
    parent_phone = data.get('parent_phone', '')
    
    if not student_id or not name:
        return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب واسمه"})
    
    existing = supabase.table("students").select("*").eq("student_id", student_id).execute()
    if existing.data:
        return jsonify({"success": False, "message": f"الطالب رقم {student_id} موجود بالفعل"})
    
    new_student = {
        'student_id': student_id,
        'name': name,
        'grade': grade,
        'class': class_val,
        'phone': phone,
        'parent_phone': parent_phone
    }
    
    try:
        supabase.table("students").insert(new_student).execute()
        return jsonify({"success": True, "message": f"تم إضافة الطالب {name} بنجاح"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/update_student/<student_id>", methods=["PUT"])
@license_required
def api_update_student(student_id):
    if session.get('role') not in ['admin', 'editor']:
        return jsonify({"success": False, "message": "غير مصرح - ليس لديك صلاحية التعديل"})
    
    data = request.get_json()
    
    update_data = {}
    if 'name' in data:
        update_data['name'] = data['name']
    if 'grade' in data:
        update_data['grade'] = data['grade']
    if 'class' in data:
        update_data['class'] = data['class']
    if 'phone' in data:
        update_data['phone'] = data['phone']
    if 'parent_phone' in data:
        update_data['parent_phone'] = data['parent_phone']
    
    if not update_data:
        return jsonify({"success": False, "message": "لا توجد بيانات للتحديث"})
    
    try:
        supabase.table("students").update(update_data).eq("student_id", student_id).execute()
        return jsonify({"success": True, "message": f"تم تحديث بيانات الطالب بنجاح"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/delete_student/<student_id>", methods=["DELETE"])
@license_required
def api_delete_student(student_id):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح - ليس لديك صلاحية الحذف"})
    
    try:
        supabase.table("attendance").delete().eq("student_id", student_id).execute()
        supabase.table("students").delete().eq("student_id", student_id).execute()
        return jsonify({"success": True, "message": f"تم حذف الطالب رقم {student_id} وجميع سجلات حضوره"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ============== الصفحات الرئيسية (محمية بالترخيص) ==============
@app.route("/")
@license_required
def home():
    return render_template("index.html")

@app.route("/scan")
@license_required
def scan():
    return render_template("scan.html")

@app.route("/general_reports")
@license_required
def general_reports():
    return render_template("general_reports.html")

@app.route("/monthly_reports")
@license_required
def monthly_reports_page():
    return render_template("monthly_reports.html")

@app.route("/charts")
@license_required
def charts_page():
    return render_template("charts.html")

@app.route("/class_reports")
@license_required
def class_reports():
    return render_template("class_reports.html")

@app.route("/qr_codes")
@license_required
def qr_codes_page():
    return render_template("qr_codes.html")

@app.route("/backup")
@license_required
def backup_page():
    if session.get('role') != 'admin':
        return redirect(url_for('home'))
    return render_template("backup.html")

@app.route("/manage_students")
@license_required
def manage_students():
    return render_template("manage_students.html")

# ============== إعادة توجيه الصفحات القديمة ==============
@app.route("/reports")
@license_required
def reports_redirect():
    return redirect(url_for('general_reports'))

@app.route("/dashboard")
@license_required
def dashboard_redirect():
    return redirect(url_for('charts'))

@app.route("/reports_dashboard")
@license_required
def reports_dashboard_redirect():
    return redirect(url_for('general_reports'))

# ============== تبديل اللغة ==============
@app.route("/api/set_language/<lang>")
@license_required
def set_language_route(lang):
    if lang in ['ar', 'en']:
        session['language'] = lang
    return redirect(request.referrer or url_for('home'))

# ============== API تسجيل الحضور ==============
@app.route("/api/register", methods=["POST"])
@license_required
def register_attendance():
    try:
        can_register, error_message = can_register_attendance()
        if not can_register:
            return jsonify({"success": False, "message": error_message})

        data = request.get_json()
        student_id = str(data.get("student_id", "")).strip()

        if not student_id:
            return jsonify({"success": False, "message": "الرجاء إدخال رقم الطالب"})

        students = get_live_students()
        student = None
        for s in students:
            if str(s.get('student_id', '')) == student_id:
                student = s
                break

        if not student:
            return jsonify({"success": False, "message": f"الطالب {student_id} غير موجود"})

        status, current_time = get_attendance_status()
        now = get_saudi_time()
        current_date = now.strftime("%Y-%m-%d")

        existing = supabase.table("attendance").select("*").eq("student_id", student_id).eq("date", current_date).execute()

        if existing.data:
            return jsonify({
                "success": False,
                "message": f"⚠️ {student.get('name')} مسجل مسبقاً اليوم"
            })

        new_record = {
            'student_id': student_id,
            'student_name': str(student.get('name', '')),
            'grade': str(student.get('grade', '')),
            'class': str(student.get('class', '')),
            'date': current_date,
            'time': current_time,
            'status': status,
            'timestamp': now.isoformat()
        }

        if save_attendance(new_record):
            parent_phone = student.get('parent_phone', '')
            if parent_phone and len(parent_phone) > 5 and twilio_enabled:
                send_whatsapp_message(parent_phone, student.get('name', ''), status, current_time)

            return jsonify({
                "success": True,
                "message": f"✅ تم تسجيل حضور {student.get('name')} - {status} الساعة {current_time}",
                "student_name": str(student.get('name', '')),
                "student_grade": str(student.get('grade', '')),
                "student_class": str(student.get('class', '')),
                "time": current_time,
                "date": current_date,
                "status": status
            })
        else:
            return jsonify({"success": False, "message": "فشل حفظ البيانات"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ============== API أكواد QR ==============
@app.route("/api/student_qr/<student_id>")
@license_required
def student_qr(student_id):
    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})

    qr_code = generate_qr_code(student_id, student.get('name', ''))

    return jsonify({
        "success": True,
        "student_id": student_id,
        "student_name": student.get('name'),
        "qr_code": qr_code
    })

@app.route("/api/all_students_qr")
@license_required
def all_students_qr():
    students = get_live_students()
    qr_codes = []

    for student in students:
        qr_code = generate_qr_code(student.get('student_id'), student.get('name', ''))
        qr_codes.append({
            'student_id': student.get('student_id'),
            'student_name': student.get('name'),
            'qr_code': qr_code
        })

    return jsonify({"success": True, "data": qr_codes})

# ============== API النسخ الاحتياطي ==============
@app.route("/api/create_backup")
@license_required
def manual_backup():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})

    success, message = create_backup()
    return jsonify({"success": success, "message": message})

@app.route("/api/list_backups")
@license_required
def list_backups():
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})

    backup_dir = "backups"
    if not os.path.exists(backup_dir):
        return jsonify({"success": True, "backups": []})

    files = []
    for file in os.listdir(backup_dir):
        if file.endswith('.xlsx'):
            stat = os.stat(os.path.join(backup_dir, file))
            files.append({
                'name': file,
                'size': stat.st_size,
                'size_kb': round(stat.st_size / 1024, 2),
                'date': datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            })

    files.sort(key=lambda x: x['date'], reverse=True)
    return jsonify({"success": True, "backups": files})

@app.route("/api/download_backup/<filename>")
@license_required
def download_backup(filename):
    if session.get('role') != 'admin':
        return jsonify({"success": False, "message": "غير مصرح"})

    backup_path = os.path.join("backups", filename)
    if os.path.exists(backup_path):
        return send_file(backup_path, as_attachment=True)
    return jsonify({"success": False, "message": "الملف غير موجود"})

# ============== API الرسوم البيانية ==============
@app.route("/api/attendance_trend")
@license_required
def attendance_trend():
    year = int(request.args.get('year', get_saudi_time().year))
    attendance = get_live_attendance()

    def get_month_name(month):
        months = {1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل', 5: 'مايو', 6: 'يونيو',
                  7: 'يوليو', 8: 'أغسطس', 9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'}
        return months.get(month, str(month))

    monthly_data = []
    for month in range(1, 13):
        month_records = [r for r in attendance if r.get('date', '').startswith(f"{year}-{month:02d}")]
        present = len([r for r in month_records if r.get('status') == 'حاضر في الوقت'])
        late = len([r for r in month_records if r.get('status') == 'متأخر'])

        monthly_data.append({
            'month': get_month_name(month),
            'present': present,
            'late': late,
            'total': present + late
        })

    return jsonify({
        "success": True,
        "year": year,
        "data": monthly_data
    })

@app.route("/api/weekly_attendance")
@license_required
def weekly_attendance():
    attendance = get_live_attendance()
    weekdays = ['الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء', 'الخميس']
    day_stats = {day: {'present': 0, 'late': 0, 'total': 0} for day in weekdays}

    for record in attendance:
        try:
            record_date = datetime.strptime(record.get('date', ''), "%Y-%m-%d")
            weekday = record_date.weekday()
            if weekday in [4, 5]:
                continue
            day_name = weekdays[weekday]
            if record.get('status') == 'حاضر في الوقت':
                day_stats[day_name]['present'] += 1
            elif record.get('status') == 'متأخر':
                day_stats[day_name]['late'] += 1
            day_stats[day_name]['total'] += 1
        except:
            pass

    result = []
    for day in weekdays:
        total = day_stats[day]['total']
        result.append({
            'day': day,
            'attendance_rate': round((day_stats[day]['present'] + day_stats[day]['late']) / max(total, 1) * 100, 2) if total > 0 else 0,
            'present': day_stats[day]['present'],
            'late': day_stats[day]['late']
        })

    return jsonify({"success": True, "data": result})

# ============== API التقارير الأساسية ==============
@app.route("/api/students_list")
@license_required
def students_list():
    students = get_live_students()
    response = make_response(jsonify({"success": True, "data": students}))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/attendance_summary")
@license_required
def attendance_summary():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()

    total = len(students)
    today_records = [r for r in attendance if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = total - (present + late)
    percentage = round((present + late) / total * 100, 1) if total > 0 else 0

    response = make_response(jsonify({
        "success": True,
        "total_students": total,
        "present": present,
        "late": late,
        "absent": absent if absent > 0 else 0,
        "percentage": percentage,
        "date": today
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/attendance_details/<date>")
@license_required
def attendance_details(date):
    students = get_live_students()
    attendance = get_live_attendance()

    result = []
    for student in students:
        record = None
        for r in attendance:
            if r.get('student_id') == student.get('student_id') and r.get('date') == date:
                record = r
                break
        result.append({
            'student_id': student.get('student_id'),
            'student_name': student.get('name'),
            'grade': student.get('grade'),
            'class': student.get('class'),
            'status': record.get('status') if record else 'غائب',
            'time': record.get('time') if record else '-'
        })
    response = make_response(jsonify({"success": True, "data": result}))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/absent_students_today")
@license_required
def absent_students_today():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()

    present_ids = set(r.get('student_id') for r in attendance if r.get('date') == today)
    absent = [s for s in students if s.get('student_id') not in present_ids]
    response = make_response(jsonify({"success": True, "data": absent, "count": len(absent), "date": today}))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/top_students")
@license_required
def top_students():
    attendance = get_live_attendance()
    counts = {}
    for r in attendance:
        if r.get('status') in ['حاضر في الوقت', 'متأخر']:
            name = r.get('student_name')
            counts[name] = counts.get(name, 0) + 1
    sorted_students = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:10]
    response = make_response(jsonify({"success": True, "data": [{"name": n, "count": c} for n, c in sorted_students]}))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/student_report/<student_id>")
@license_required
def student_report(student_id):
    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})

    attendance = get_live_attendance()
    records = [r for r in attendance if r.get('student_id') == student_id]
    records.sort(key=lambda x: x.get('date', ''), reverse=True)

    response = make_response(jsonify({
        "success": True,
        "student_name": student.get('name'),
        "student_id": student_id,
        "grade": student.get('grade'),
        "class": student.get('class'),
        "records": records
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

# ============== التقارير الشهرية ==============
@app.route("/api/monthly_report")
@license_required
def monthly_report():
    year = int(request.args.get('year', get_saudi_time().year))
    month = int(request.args.get('month', get_saudi_time().month))
    students = get_live_students()
    attendance = get_live_attendance()

    days_in_month = monthrange(year, month)[1]
    daily_stats = []
    total_present = 0
    total_late = 0
    total_absent = 0
    total_days_with_attendance = 0

    def get_month_name(month):
        months = {1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل', 5: 'مايو', 6: 'يونيو',
                  7: 'يوليو', 8: 'أغسطس', 9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'}
        return months.get(month, str(month))

    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        day_records = [r for r in attendance if r.get('date') == date_str]
        present = len([r for r in day_records if r.get('status') == 'حاضر في الوقت'])
        late = len([r for r in day_records if r.get('status') == 'متأخر'])
        absent = len(students) - (present + late)

        total_present += present
        total_late += late
        total_absent += absent

        if present + late > 0:
            total_days_with_attendance += 1

        daily_stats.append({
            'day': day,
            'date': date_str,
            'present': present,
            'late': late,
            'absent': absent if absent > 0 else 0,
            'percentage': round((present + late) / len(students) * 100, 2) if len(students) > 0 else 0
        })

    avg_attendance = round((total_present + total_late) / (days_in_month * len(students)) * 100, 2) if len(students) > 0 else 0

    if request.args.get('export') == 'excel':
        df = pd.DataFrame(daily_stats)
        filename = f"monthly_report_{year}_{month}.xlsx"
        df.to_excel(filename, index=False, engine='openpyxl')
        return send_file(filename, as_attachment=True)

    response = make_response(jsonify({
        "success": True,
        "year": year,
        "month": month,
        "month_name": get_month_name(month),
        "days_in_month": days_in_month,
        "total_students": len(students),
        "summary": {
            "total_present": total_present,
            "total_late": total_late,
            "total_absent": total_absent,
            "avg_attendance_rate": avg_attendance,
            "days_with_attendance": total_days_with_attendance,
            "best_day": max(daily_stats, key=lambda x: x['present'] + x['late']) if daily_stats else None,
            "worst_day": min(daily_stats, key=lambda x: x['present'] + x['late']) if daily_stats else None
        },
        "daily_stats": daily_stats
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/student_monthly_report/<student_id>")
@license_required
def student_monthly_report(student_id):
    year = int(request.args.get('year', get_saudi_time().year))
    month = int(request.args.get('month', get_saudi_time().month))

    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})

    days_in_month = monthrange(year, month)[1]
    attendance = get_live_attendance()
    student_records = [r for r in attendance if r.get('student_id') == student_id]

    daily_status = []
    present_count = 0
    late_count = 0

    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        record = next((r for r in student_records if r.get('date') == date_str), None)

        if record:
            if record.get('status') == 'حاضر في الوقت':
                present_count += 1
            elif record.get('status') == 'متأخر':
                late_count += 1

        daily_status.append({
            'day': day,
            'date': date_str,
            'status': record.get('status') if record else 'غائب',
            'time': record.get('time') if record else '-'
        })

    absent_count = days_in_month - (present_count + late_count)
    attendance_rate = round((present_count + late_count) / days_in_month * 100, 2)

    if request.args.get('export') == 'excel':
        df = pd.DataFrame(daily_status)
        filename = f"student_{student_id}_{year}_{month}.xlsx"
        df.to_excel(filename, index=False, engine='openpyxl')
        return send_file(filename, as_attachment=True)

    response = make_response(jsonify({
        "success": True,
        "student_id": student_id,
        "student_name": student.get('name'),
        "grade": student.get('grade'),
        "class": student.get('class'),
        "year": year,
        "month": month,
        "month_name": get_month_name(month),
        "days_in_month": days_in_month,
        "summary": {
            "present": present_count,
            "late": late_count,
            "absent": absent_count,
            "attendance_rate": attendance_rate
        },
        "daily_status": daily_status
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/comparative_monthly_report")
@license_required
def comparative_monthly_report():
    year = int(request.args.get('year', get_saudi_time().year))
    months = request.args.get('months', '1,2,3,4,5,6,7,8,9,10,11,12')
    months = [int(m) for m in months.split(',')]

    students = get_live_students()
    attendance = get_live_attendance()

    def get_month_name(month):
        months = {1: 'يناير', 2: 'فبراير', 3: 'مارس', 4: 'أبريل', 5: 'مايو', 6: 'يونيو',
                  7: 'يوليو', 8: 'أغسطس', 9: 'سبتمبر', 10: 'أكتوبر', 11: 'نوفمبر', 12: 'ديسمبر'}
        return months.get(month, str(month))

    monthly_summary = []
    for month in months:
        days_in_month = monthrange(year, month)[1]
        month_records = [r for r in attendance if r.get('date', '').startswith(f"{year}-{month:02d}")]

        present = len([r for r in month_records if r.get('status') == 'حاضر في الوقت'])
        late = len([r for r in month_records if r.get('status') == 'متأخر'])
        expected = days_in_month * len(students)

        monthly_summary.append({
            'month': month,
            'month_name': get_month_name(month),
            'present': present,
            'late': late,
            'total_attendance': present + late,
            'expected': expected,
            'attendance_rate': round((present + late) / expected * 100, 2) if expected > 0 else 0
        })

    response = make_response(jsonify({
        "success": True,
        "year": year,
        "total_students": len(students),
        "monthly_summary": monthly_summary
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

# ============== API التقارير الأخرى ==============
@app.route("/api/attendance_chart")
@license_required
def attendance_chart():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()

    today_records = [r for r in attendance if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = len(students) - (present + late)
    response = make_response(jsonify({
        "success": True,
        "labels": ["حاضر في الوقت", "متأخر", "غائب"],
        "data": [present, late, absent],
        "colors": ["#28a745", "#fd7e14", "#dc3545"]
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

@app.route("/api/dashboard_stats")
@license_required
def dashboard_stats():
    today = get_saudi_time().strftime("%Y-%m-%d")
    students = get_live_students()
    attendance = get_live_attendance()

    total = len(students)
    today_records = [r for r in attendance if r.get('date') == today]
    present = len([r for r in today_records if r.get('status') == 'حاضر في الوقت'])
    late = len([r for r in today_records if r.get('status') == 'متأخر'])
    absent = total - (present + late)
    percentage = round((present + late) / total * 100, 1) if total > 0 else 0

    response = make_response(jsonify({
        "success": True,
        "percentage": percentage,
        "present_today": present + late,
        "present": present,
        "late": late,
        "absent": absent,
        "total_students": total,
        "total_records": len(attendance)
    }))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response

# ============== APIs التصدير ==============
@app.route("/api/export_today_excel")
@license_required
def export_today_excel():
    today = get_saudi_time().strftime("%Y-%m-%d")
    filename = f"attendance_{today}.xlsx"
    students = get_live_students()
    attendance = get_live_attendance()

    result = []
    for student in students:
        record = None
        for r in attendance:
            if r.get('student_id') == student.get('student_id') and r.get('date') == today:
                record = r
                break
        result.append({
            'رقم الطالب': student.get('student_id'),
            'اسم الطالب': student.get('name'),
            'الصف': student.get('grade'),
            'الشعبة': student.get('class'),
            'وقت التسجيل': record.get('time') if record else '-',
            'الحالة': record.get('status') if record else 'غائب'
        })
    df = pd.DataFrame(result)
    df.to_excel(filename, index=False, engine='openpyxl')
    return send_file(filename, as_attachment=True)

@app.route("/api/export_attendance/<date>")
@license_required
def export_attendance(date):
    filename = f"attendance_{date}.xlsx"
    students = get_live_students()
    attendance = get_live_attendance()

    result = []
    for student in students:
        record = None
        for r in attendance:
            if r.get('student_id') == student.get('student_id') and r.get('date') == date:
                record = r
                break
        result.append({
            'رقم الطالب': student.get('student_id'),
            'اسم الطالب': student.get('name'),
            'الصف': student.get('grade'),
            'الشعبة': student.get('class'),
            'وقت التسجيل': record.get('time') if record else '-',
            'الحالة': record.get('status') if record else 'غائب'
        })
    df = pd.DataFrame(result)
    df.to_excel(filename, index=False, engine='openpyxl')
    return send_file(filename, as_attachment=True)

@app.route("/api/export_student_excel/<student_id>")
@license_required
def export_student_excel(student_id):
    students = get_live_students()
    student = next((s for s in students if s.get('student_id') == student_id), None)
    if not student:
        return jsonify({"success": False, "error": "الطالب غير موجود"})

    attendance = get_live_attendance()
    records = [r for r in attendance if r.get('student_id') == student_id]
    records.sort(key=lambda x: x.get('date', ''), reverse=True)

    filename = f"student_{student_id}_report.xlsx"
    df = pd.DataFrame(records)
    df.to_excel(filename, index=False, engine='openpyxl')
    return send_file(filename, as_attachment=True)

# ============== APIs إدارة البيانات ==============
@app.route("/api/upload_local_students")
@license_required
def upload_local_students():
    try:
        if os.path.exists("students.csv"):
            df = pd.read_csv("students.csv", encoding='utf-8-sig')
        elif os.path.exists("students.xlsx"):
            df = pd.read_excel("students.xlsx")
        else:
            return jsonify({"success": False, "message": "لا يوجد ملف students.csv أو students.xlsx"})

        df = df.fillna("")
        for col in df.columns:
            df[col] = df[col].astype(str)

        df['student_id'] = df['student_id'].str.replace('.0', '', regex=False).str.strip()
        records = df.to_dict("records")

        supabase.table("students").delete().neq("student_id", "").execute()

        batch_size = 50
        for i in range(0, len(records), batch_size):
            batch = records[i:i+batch_size]
            supabase.table("students").insert(batch).execute()

        return jsonify({"success": True, "message": f"تم رفع {len(records)} طالب إلى Supabase"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/refresh_all")
@license_required
def refresh_all():
    students = get_live_students()
    attendance = get_live_attendance()
    return jsonify({
        "success": True,
        "students_count": len(students),
        "attendance_count": len(attendance)
    })

@app.route("/api/direct_test")
@license_required
def direct_test():
    try:
        result = supabase.table("attendance").select("*").limit(10).execute()
        return jsonify({"success": True, "total_rows": len(result.data), "sample_data": result.data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/clear_attendance")
@license_required
def clear_attendance():
    try:
        supabase.table("attendance").delete().neq("student_id", "").execute()
        return jsonify({"success": True, "message": "تم مسح جميع سجلات الحضور"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route("/api/stats")
@license_required
def stats():
    students = get_live_students()
    attendance = get_live_attendance()
    return jsonify({
        "success": True,
        "students_count": len(students),
        "attendance_count": len(attendance),
        "storage": "supabase"
    })

@app.route("/api/saudi_time")
@license_required
def saudi_time():
    now = get_saudi_time()
    return jsonify({
        "success": True,
        "datetime": now.strftime("%Y-%m-%d %H:%M:%S"),
        "is_weekend": is_weekend(now.date()),
        "can_register": can_register_attendance()[0]
    })

@app.route("/test_supabase")
def test_supabase():
    try:
        result = supabase.table("students").select("*").execute()
        return {"success": True, "rows": len(result.data)}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route("/test_attendance")
def test_attendance():
    try:
        result = supabase.table("attendance").select("*").execute()
        return {"success": True, "rows": len(result.data), "sample": result.data[:3]}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.route("/health")
def health():
    return {"status": "ok", "database": "supabase"}

# تشغيل النسخ الاحتياطي التلقائي في الخلفية
backup_thread = threading.Thread(target=scheduled_backup, daemon=True)
backup_thread.start()

# ============== تشغيل التطبيق ==============
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print("=" * 60)
    print("🚀 نظام الحضور يعمل الآن!")
    print("📊 قاعدة البيانات: Supabase")
    print("⏰ ساعات التسجيل: 24 ساعة (طوال اليوم)")
    print("📅 أيام العطلات: الجمعة والسبت فقط")
    print("🔒 نظام حماية الأجهزة: مفعل")
    print("")
    print("📱 الصفحات المتاحة:")
    print("   🏠 الرئيسية: /")
    print("   📱 تسجيل الحضور: /scan")
    print("   📊 التقارير العامة: /general_reports")
    print("   📅 التقارير الشهرية: /monthly_reports")
    print("   📈 الرسوم البيانية: /charts")
    print("   📋 تقارير الصف والفصل: /class_reports")
    print("   📱 أكواد QR: /qr_codes")
    print("   💾 النسخ الاحتياطي: /backup")
    print("   👥 المستخدمين: /users_list")
    print("   📚 إدارة الطلاب: /manage_students")
    print("   🔑 إدارة التراخيص: /admin/licenses")
    print("=" * 60)
    app.run(host='0.0.0.0', port=port, debug=False)