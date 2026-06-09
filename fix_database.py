import pandas as pd
from supabase import create_client
from dotenv import load_dotenv
import os
import unicodedata

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def normalize_arabic(text):
    """تحويل الأحرف العربية من صيغة Presentation إلى صيغة طبيعية"""
    if not isinstance(text, str):
        return ""
    # تطبيع Unicode
    text = unicodedata.normalize('NFKC', text)
    return text.strip()

# قراءة ملف Excel
print("📖 جاري قراءة ملف students.xlsx...")
df = pd.read_excel("students.xlsx")

print(f"📊 عدد الطلاب: {len(df)}")
print("📋 الأعمدة الموجودة:", df.columns.tolist())

# تنظيف جميع الأعمدة النصية
for col in df.columns:
    if col != 'student_id':
        df[col] = df[col].apply(lambda x: normalize_arabic(x) if pd.notna(x) else "")

# تنظيف أرقام الطلاب
df['student_id'] = df['student_id'].astype(str).str.strip()
if 'phone' in df.columns:
    df['phone'] = df['phone'].astype(str).str.replace('.0', '', regex=False).str.strip()
if 'parent_phone' in df.columns:
    df['parent_phone'] = df['parent_phone'].astype(str).str.replace('.0', '', regex=False).str.strip()

# تعبئة القيم الفارغة
df = df.fillna("")

# عرض عينة للتأكد
print("\n✅ عينة من البيانات بعد التنظيف:")
print(df[['student_id', 'name', 'grade', 'class']].head(10))

# معرفة عدد الطلاب الحاليين
try:
    result = supabase.table("students").select("*", count="exact").execute()
    current_count = result.count if hasattr(result, 'count') else len(result.data)
    print(f"\n⚠️ عدد الطلاب الحاليين في قاعدة البيانات: {current_count}")
except Exception as e:
    print(f"خطأ في قراءة العدد: {e}")
    current_count = 0

# تأكيد قبل الحذف
confirm = input("\nهل تريد حذف جميع الطلاب الحاليين ورفع البيانات الجديدة؟ (اكتب 'نعم' للمتابعة): ")

if confirm != 'نعم':
    print("❌ تم الإلغاء")
    exit()

# حذف جميع الطلاب
print("🗑️ جاري حذف البيانات القديمة...")
try:
    supabase.table("students").delete().neq("student_id", "").execute()
    print("✅ تم حذف البيانات القديمة")
except Exception as e:
    print(f"خطأ في الحذف: {e}")

# رفع البيانات الجديدة على دفعات (50 طالب في كل مرة)
print("📤 جاري رفع البيانات الجديدة...")
records = df.to_dict("records")
batch_size = 50
success_count = 0

for i in range(0, len(records), batch_size):
    batch = records[i:i+batch_size]
    try:
        supabase.table("students").insert(batch).execute()
        success_count += len(batch)
        print(f"  ✅ تم رفع {success_count}/{len(records)} طالب")
    except Exception as e:
        print(f"  ❌ خطأ في رفع البATCH: {e}")

print(f"\n🎉 تم رفع {success_count} طالب بنجاح!")

# التحقق
print("\n🔍 التحقق من البيانات في Supabase...")
try:
    result = supabase.table("students").select("student_id", "name").limit(5).execute()
    print("أول 5 طلاب:")
    for student in result.data:
        print(f"  {student['student_id']}: {student['name']}")
except Exception as e:
    print(f"خطأ في التحقق: {e}")