from flask import Flask, render_template

app = Flask(__name__)

# الصفحة الرئيسية
@app.route("/")
def home():
    return render_template("index.html")

# صفحة مسح QR
@app.route("/scan")
def scan():
    return render_template("scan.html")

if __name__ == "__main__":
    app.run()
