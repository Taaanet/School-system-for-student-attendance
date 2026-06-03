import qrcode
import pandas as pd

# قراءة ملف Excel
df = pd.read_excel('students.xlsx')

# إنشاء QR لكل طالب
for index, row in df.iterrows():
    student_id = str(row['student_id']).strip()
    student_name = row['name']
    
    # إنشاء QR Code
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(student_id)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    filename = f"QR_{student_id}_{student_name}.png"
    img.save(filename)
    
    print(f"✅ تم إنشاء QR للطالب: {student_name} (الرقم: {student_id}) -> الملف: {filename}")

print("\n" + "="*50)
print("🎉 تم الإنشاء! استخدم ملفات PNG هذه لاختبار المسح")
print("="*50)
