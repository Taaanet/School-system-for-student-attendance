import os
import re

templates_dir = "templates"

# النمط للبحث عن سطر QR
pattern = r'<a href="/qr_codes">\{\{ t\(\'qr_codes\'\) \}\}</a>\s*\n?'

for filename in os.listdir(templates_dir):
    if filename.endswith('.html'):
        filepath = os.path.join(templates_dir, filename)
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        new_content = re.sub(pattern, '', content)
        
        if new_content != content:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"✅ تم التعديل: {filename}")

print("🎉 تم حذف زر أكواد QR من جميع الملفات!")