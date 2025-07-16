import requests
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from flask_sqlalchemy import SQLAlchemy
import json
import os
import time
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "your_secret_key")  # Use env variable in production

# Configuration
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "YOUR_ALPHA_VANTAGE_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "your_email@gmail.com")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD", "your_app_password")

# Database Setup (PostgreSQL)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL", "sqlite:///stocks.db").replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    holdings = db.relationship("Holding", backref="user", lazy=True)
    watchlist = db.relationship("Watchlist", backref="user", lazy=True)

class Holding(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    symbol = db.Column(db.String(10), nullable=False)

class Watchlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    symbol = db.Column(db.String(10), nullable=False)

# HTML Templates
signup_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Sign Up</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100 font-sans">
    <div class="max-w-md mx-auto bg-white shadow-lg rounded-lg p-6 my-8">
        <h1 class="text-2xl font-bold text-gray-800 mb-4">Sign Up</h1>
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div class="bg-red-100 text-red-700 p-2 rounded mb-4">
                    {{ messages[0] }}
                </div>
            {% endif %}
        {% endwith %}
        <form method="POST" action="{{ url_for('signup') }}">
            <div class="mb-4">
                <label class="block text-gray-700">Email</label>
                <input type="email" name="email" class="w-full border rounded p-2" required>
            </div>
            <div class="mb-4">
                <label class="block text-gray-700">Password</label>
                <input type="password" name="password" class="w-full border rounded p-2" required>
            </div>
            <button type="submit" class="w-full bg-blue-600 text-white p-2 rounded hover:bg-blue-700">Sign Up</button>
        </form>
        <p class="mt-4 text-gray-600">Already have an account? <a href="{{ url_for('login') }}" class="text-blue-600 hover:underline">Log In</a></p>
    </div>
</body>
</html>
"""

login_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Log In</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100 font-sans">
    <div class="max-w-md mx-auto bg-white shadow-lg rounded-lg p-6 my-8">
        <h1 class="text-2xl font-bold text-gray-800 mb-4">Log In</h1>
        {% with messages = get_flashed_messages() %}
            {% if messages %}
                <div class="bg-red-100 text-red-700 p-2 rounded mb-4">
                    {{ messages[0] }}
                </div>
            {% endif %}
        {% endwith %}
        <form method="POST" action="{{ url_for('login') }}">
            <div class="mb-4">
                <label class="block text-gray-700">Email</label>
                <input type="email" name="email" class="w-full border rounded p-2" required>
            </div>
            <div class="mb-4">
                <label class="block text-gray-700">Password</label>
                <input type="password" name="password" class="w-full border rounded p-2" required>
            </div>
            <button type="submit" class="w-full bg-blue-600 text-white p-2 rounded hover:bg-blue-700">Log In</button>
        </form>
        <p class="mt-4 text-gray-600">Don't have an account? <a href="{{ url_for('signup') }}" class="text-blue-600 hover:underline">Sign Up</a></p>
    </div>
</body>
</html>
"""

dashboard_template = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard</title>
    <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
</head>
<body class="bg-gray-100 font-sans">
    <div class="max-w-3xl mx-auto bg-white shadow-lg rounded-lg p-6 my-8">
        <h1 class="text-2xl font-bold text-gray-800 mb-4">Stock Dashboard</h1>
        <p class="text-gray-600 mb-4">Welcome, {{ user_email }}! Manage your stock holdings and watchlist.</p>
        <a href="{{ url_for('logout') }}" class="text-blue-600 hover:underline">Log Out</a>
        <h2 class="text-xl font-semibold text-gray-800 mt-6">Add Stock</h2>
        <form method="POST" action="{{ url_for('add_stock') }}" class="mb-6">
            <div class="flex space-x-4">
                <input type="text" name="symbol" placeholder="Stock Symbol (e.g., AAPL)" class="w-full border rounded p-2" required>
                <select name="list_type" class="border rounded p-2">
                    <option value="holdings">Holdings</option>
                    <option value="watchlist">Watchlist</option>
                </select>
                <button type="submit" class="bg-blue-600 text-white p-2 rounded hover:bg-blue-700">Add</button>
            </div>
        </form>
        <h2 class="text-xl font-semibold text-gray-800">Your Holdings</h2>
        <ul class="list-disc pl-6 mb-6">
            {% for stock in holdings %}
                <li class="text-gray-700">{{ stock.symbol }} <a href="{{ url_for('remove_stock', symbol=stock.symbol, list_type='holdings') }}" class="text-red-600 hover:underline">Remove</a></li>
            {% else %}
                <li class="text-gray-600">No stocks in holdings.</li>
            {% endfor %}
        </ul>
        <h2 class="text-xl font-semibold text-gray-800">Your Watchlist</h2>
        <ul class="list-disc pl-6">
            {% for stock in watchlist %}
                <li class="text-gray-700">{{ stock.symbol }} <a href="{{ url_for('remove_stock', symbol=stock.symbol, list_type='watchlist') }}" class="text-red-600 hover:underline">Remove</a></li>
            {% else %}
                <li class="text-gray-600">No stocks in watchlist.</li>
            {% endfor %}
        </ul>
    </div>
</body>
</html>
"""

# Flask Routes
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        try:
            user = User(email=email, password=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            flash("Sign up successful! Please log in.")
            return redirect(url_for("login"))
        except Exception as e:
            flash("Email already exists.")
            return redirect(url_for("signup"))
    return render_template_string(signup_template)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            session["user_email"] = user.email
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.")
        return redirect(url_for("login"))
    return render_template_string(login_template)

@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user = User.query.get(session["user_id"])
    return render_template_string(dashboard_template, user_email=session["user_email"], holdings=user.holdings, watchlist=user.watchlist)

@app.route("/add_stock", methods=["POST"])
def add_stock():
    if "user_id" not in session:
        return redirect(url_for("login"))
    symbol = request.form["symbol"].upper()
    list_type = request.form["list_type"]
    Model = Holding if list_type == "holdings" else Watchlist
    try:
        stock = Model(user_id=session["user_id"], symbol=symbol)
        db.session.add(stock)
        db.session.commit()
    except Exception:
        db.session.rollback()
    return redirect(url_for("dashboard"))

@app.route("/remove_stock/<list_type>/<symbol>")
def remove_stock(list_type, symbol):
    if "user_id" not in session:
        return redirect(url_for("login"))
    Model = Holding if list_type == "holdings" else Watchlist
    stock = Model.query.filter_by(user_id=session["user_id"], symbol=symbol).first()
    if stock:
        db.session.delete(stock)
        db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("user_email", None)
    return redirect(url_for("login"))

@app.route("/send_newsletters", methods=["POST"])
def trigger_newsletters():
    if request.form.get("token") != os.getenv("SCHEDULER_TOKEN"):
        return "Unauthorized", 401
    with app.app_context():
        send_newsletters()
    return "Newsletters sent", 200

# Newsletter Logic
def fetch_stock_news(symbol):
    """Fetch recent news for a given stock symbol using Alpha Vantage."""
    time.sleep(12)  # Respect Alpha Vantage rate limit (5 calls/min)
    url = f"https://www.alphavantage.co/query?function=NEWS_SENTIMENT&tickers={symbol}&limit=3&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        news_items = data.get("feed", [])
        return news_items[:3]
    except requests.RequestException as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return []

def fetch_stock_performance(symbol):
    """Fetch weekly stock performance data including high, low, and change using Alpha Vantage."""
    time.sleep(12)  # Respect Alpha Vantage rate limit (5 calls/min)
    url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={symbol}&apikey={ALPHA_VANTAGE_API_KEY}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        time_series = data.get("Time Series (Daily)", {})
        if not time_series:
            return None
        today = datetime.now().date()
        one_week_ago = today - timedelta(days=7)
        latest_date = max([date for date in time_series.keys() if date <= str(today)], default=None)
        past_date = min([date for date in time_series.keys() if date >= str(one_week_ago)], default=latest_date)
        if not latest_date or not past_date:
            return None
        latest_close = float(time_series[latest_date]["4. close"])
        past_close = float(time_series[past_date]["4. close"])
        change = ((latest_close - past_close) / past_close) * 100
        weekly_data = [time_series[date] for date in time_series.keys() if one_week_ago.strftime("%Y-%m-%d") <= date <= str(today)]
        weekly_high = max(float(day["2. high"]) for day in weekly_data) if weekly_data else latest_close
        weekly_low = min(float(day["3. low"]) for day in weekly_data) if weekly_data else latest_close
        return {
            "latest_close": latest_close,
            "change_percent": change,
            "weekly_high": weekly_high,
            "weekly_low": weekly_low
        }
    except (requests.RequestException, KeyError, ValueError) as e:
        logger.error(f"Error fetching performance for {symbol}: {e}")
        return None

def create_newsletter(user_email, stocks):
    """Create HTML newsletter content for a user with their stock news and performance."""
    current_date = datetime.now().strftime("%Y-%m-%d")
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Weekly Stock Newsletter</title>
        <link href="https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css" rel="stylesheet">
    </head>
    <body class="bg-gray-100 font-sans">
        <div class="max-w-3xl mx-auto bg-white shadow-lg rounded-lg p-6 my-8">
            <header class="text-center mb-6">
                <h1 class="text-3xl font-bold text-gray-800">Weekly Stock Market Newsletter</h1>
                <p class="text-gray-600">Market updates for {user_email} as of {current_date}</p>
            </header>
            <main>
    """
    for symbol in stocks:
        news_items = fetch_stock_news(symbol)
        performance = fetch_stock_performance(symbol)
        
        html_content += f"""
        <div class="mb-6 p-4 bg-gray-50 rounded-lg shadow">
            <h2 class="text-2xl font-semibold text-gray-800">{symbol}</h2>
        """
        
        if performance:
            color = "text-green-600" if performance["change_percent"] >= 0 else "text-red-600"
            html_content += f"""
            <div class="mt-2">
                <p class="text-gray-700">Latest Close: <span class="font-medium">${performance['latest_close']:.2f}</span></p>
                <p class="text-gray-700">Weekly Change: <span class="{color} font-medium">{performance['change_percent']:.2f}%</span></p>
                <p class="text-gray-700">Weekly High: <span class="font-medium">${performance['weekly_high']:.2f}</span></p>
                <p class="text-gray-700">Weekly Low: <span class="font-medium">${performance['weekly_low']:.2f}</span></p>
            </div>
            """
        
        if news_items:
            html_content += "<h3 class='text-lg font-semibold text-gray-700 mt-4'>Recent News:</h3>"
            for item in news_items:
                title = item.get("title", "No title")
                summary = item.get("summary", "No summary")
                url = item.get("url", "#")
                html_content += f"""
                <div class="mt-2 pl-4 border-l-2 border-gray-200">
                    <p class="text-gray-800 font-medium">{title}</p>
                    <p class="text-gray-600 text-sm">{summary}</p>
                    <a href="{url}" class="text-blue-600 text-sm hover:underline">Read more</a>
                </div>
                """
        else:
            html_content += "<p class='text-gray-600 mt-2'>No recent news available.</p>"
        
        html_content += "</div>"
    
    html_content += """
            </main>
            <footer class="text-center text-gray-500 text-sm mt-6">
                <p>Powered by Alpha Vantage | <a href="{dashboard_url}" class="text-blue-600 hover:underline">Manage your stocks</a></p>
            </footer>
        </div>
    </body>
    </html>
    """.format(dashboard_url=url_for("dashboard", _external=True))
    return html_content

def send_email(recipient_email, html_content):
    """Send the newsletter to a recipient."""
    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = recipient_email
    msg["Subject"] = "Weekly Stock Market Newsletter"
    
    msg.attach(MIMEText(html_content, "html"))
    
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        server.quit()
        logger.info(f"Newsletter sent to {recipient_email}")
    except Exception as e:
        logger.error(f"Error sending email to {recipient_email}: {e}")

def send_newsletters():
    """Send newsletters to all users with their stocks."""
    try:
        users = User.query.all()
        for user in users:
            stocks = [h.symbol for h in user.holdings] + [w.symbol for w in user.watchlist]
            if stocks:
                newsletter_content = create_newsletter(user.email, stocks)
                send_email(user.email, newsletter_content)
    except Exception as e:
        logger.error(f"Error sending newsletters: {e}")

# Initialize database with error handling
try:
    with app.app_context():
        db.create_all()
        logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Error initializing database: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "send_newsletters":
        with app.app_context():
            send_newsletters()
    else:
        port = int(os.getenv("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_ENV") == "development")
# To run the Flask app locally: python stock_newsletter.py
# To send newsletters: python stock_newsletter.py send_newsletters
# Schedule newsletters with Google Cloud Scheduler or Render cron job (paid tier):
# POST to /send_newsletters with token in the request body