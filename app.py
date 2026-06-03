from flask import Flask, render_template

app = Flask(**name**)

# الصفحة الرئيسية

@app.route("/")
def home():
return render_template("index.html")

# صفحة مسح QR

@app.route("/scan")
def scan():
return render_template("scan.html")

if **name** == "**main**":
app.run(debug=True)
