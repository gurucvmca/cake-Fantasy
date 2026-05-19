from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from pymongo import MongoClient
from bson import ObjectId
from werkzeug.utils import secure_filename
import os
import razorpay
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ---------------- PATH CONFIG ----------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
UPLOAD_FOLDER = os.path.join(FRONTEND_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(
    __name__,
    template_folder=os.path.join(FRONTEND_DIR, "templates"),
    static_folder=os.path.join(FRONTEND_DIR, "static")
)
app.secret_key = os.environ.get("SECRET_KEY", "cakeshop_secret_default_2026")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024  # 8 MB max upload

# This token changes when the backend restarts. Stored in sessions to invalidate stale client cookies.
SERVER_SESSION_TOKEN = os.urandom(16).hex()

# ---- SECURE SESSION CONFIG ----
app.config["SESSION_COOKIE_HTTPONLY"] = True      # Prevent JS access to cookies
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"     # CSRF protection
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)  # Auto-expire sessions


# ---------------- MONGODB ----------------
MONGO_URI = os.environ.get("MONGODB_URI", "mongodb://127.0.0.1:27017/")
client = MongoClient(MONGO_URI)
db = client["cakeshop"]
users  = db["users"]
orders = db["orders"]
cakes  = db["cakes"]


# ---------------- RAZORPAY ----------------
RZP_KEY_ID = os.environ.get("RAZORPAY_KEY_ID", "rzp_test_placeholderID")
RZP_KEY_SECRET = os.environ.get("RAZORPAY_KEY_SECRET", "rzp_test_placeholderSecret")
rzp_client = razorpay.Client(auth=(RZP_KEY_ID, RZP_KEY_SECRET))

print("[OK] MongoDB connected & Razorpay Initialized")

# Seed admin account if not present
if not users.find_one({"email": "admin@cakeshop.com"}):
    hashed_pw = generate_password_hash("admin123")
    users.insert_one({"email": "admin@cakeshop.com", "password": hashed_pw, "role": "admin"})
    print("[OK] Admin account seeded: admin@cakeshop.com / admin123")

# Seed default cakes if none exist
if cakes.count_documents({}) == 0:
    cakes.insert_many([
        {
            "name": "Rasmalia Cake",
            "description": "Soft sponge soaked in saffron milk, topped with rabri & pistachios.",
            "price": 600,
            "image": "https://images.unsplash.com/photo-1563729784474-d77dbb933a9e?w=600&q=80",
            "badge": "⭐ Bestseller",
            "badge_color": "#ff6f61"
        },
        {
            "name": "Vanilla Dream Cake",
            "description": "Classic moist vanilla sponge with fresh whipped cream & seasonal fruits.",
            "price": 550,
            "image": "https://images.unsplash.com/photo-1571115177098-24ec42ed204d?w=600&q=80",
            "badge": "🌸 Light & Fresh",
            "badge_color": "#ffc371"
        },
        {
            "name": "Chocolate Truffle Cake",
            "description": "Dark chocolate ganache drip cake with truffle layers & raspberries.",
            "price": 700,
            "image": "https://images.unsplash.com/photo-1606890737304-57a1ca8a5b62?w=600&q=80",
            "badge": "🍫 Rich & Decadent",
            "badge_color": "#4a2c2a"
        }
    ])
    print("[OK] Default cakes seeded")

# ---------------- HELPERS ----------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def is_admin():
    return session.get("role") == "admin"

def cart_count():
    return sum(item["qty"] for item in session.get("cart", []))


def get_saved_cart(email):
    """Return the saved cart stored in the user's MongoDB document."""
    if not email:
        return []
    user = users.find_one({"email": email}, {"cart": 1})
    return user.get("cart", []) if user else []


def save_cart_for_user(email, cart):
    """Persist the current cart into the user's MongoDB document."""
    if not email:
        return
    users.update_one({"email": email}, {"$set": {"cart": cart}})


def merge_cart_items(saved_cart, session_cart):
    """Merge existing saved cart with current session cart by cake id."""
    merged = {item["id"]: item.copy() for item in saved_cart}
    for item in session_cart:
        if item["id"] in merged:
            merged[item["id"]]["qty"] += item["qty"]
            merged[item["id"]]["total"] = merged[item["id"]]["qty"] * merged[item["id"]]["price"]
        else:
            merged[item["id"]] = item.copy()
    return list(merged.values())

# ---------------- SECURITY MIDDLEWARE ----------------

@app.after_request
def add_no_cache_headers(response):
    """Prevent browser from caching protected pages (back-button protection after logout)."""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, public, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

@app.before_request
def make_session_permanent():
    """Ensure every session uses the configured expiry time and clear stale server sessions."""
    if session.get("server_session_token") != SERVER_SESSION_TOKEN:
        session.clear()
    session.permanent = True

# ---------------- AUTH ROUTES ----------------

@app.route("/")
def login_page():
    # If already logged in, redirect to appropriate dashboard
    if session.get("user"):
        if session.get("role") == "admin":
            return redirect(url_for("admin"))
        return redirect(url_for("welcome"))
    return render_template("login.html")

@app.route("/signup", methods=["POST"])
def signup():
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    if not email or not password:
        return "Missing email or password"
    print(f"[DEBUG] Signup attempt for email={email}")
    existing = users.find_one({"email": email})
    if existing:
        print(f"[DEBUG] Signup blocked — user exists: {email}")
        flash("User already exists. Please login.", "error")
        return redirect(url_for("login_page"))
    
    hashed_pw = generate_password_hash(password)
    users.insert_one({"email": email, "password": hashed_pw, "role": "customer", "cart": []})
    session["user"] = email
    session["role"] = "customer"
    session["server_session_token"] = SERVER_SESSION_TOKEN
    session["cart"] = []
    session.modified = True
    flash("Account created! You are now logged in.", "success")
    return redirect(url_for("welcome"))

@app.route("/login", methods=["POST"])
def login():
    email    = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "").strip()
    print(f"[DEBUG] Login attempt for email={email}")
    user = users.find_one({"email": email})
    if not user:
        print(f"[DEBUG] Login failed — no such user: {email}")
    else:
        print(f"[DEBUG] User found, checking password for: {email}")
    pw_ok = user and check_password_hash(user.get("password", ""), password)
    print(f"[DEBUG] Password check for {email}: {bool(pw_ok)}")
    if pw_ok:
        print(f"[DEBUG] Login successful for: {email}")
        session["user"] = email
        session["role"] = user.get("role", "customer")
        session["server_session_token"] = SERVER_SESSION_TOKEN
        saved_cart = get_saved_cart(email)
        current_cart = session.get("cart", [])
        if current_cart and saved_cart:
            merged_cart = merge_cart_items(saved_cart, current_cart)
        else:
            merged_cart = saved_cart or current_cart or []
        session["cart"] = merged_cart
        session.modified = True
        save_cart_for_user(email, merged_cart)
        if session["role"] == "admin":
            return redirect(url_for("admin"))
        return redirect(url_for("welcome"))
    
    flash("Invalid email or password", "error")
    return redirect(url_for("login_page"))

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect("/")

# ---------------- SHOP ROUTES ----------------

@app.route("/welcome")
def welcome():
    if not session.get("user"):
        return redirect("/")
    all_cakes = list(cakes.find())
    for c in all_cakes:
        c["_id"] = str(c["_id"])
    return render_template("welcome.html", user=session["user"], cakes=all_cakes, cart_count=cart_count())

# ---------------- CART ROUTES ----------------

@app.route("/cart/add", methods=["POST"])
def cart_add():
    if not session.get("user"):
        return redirect("/")
    cake_id   = request.form.get("cake_id")
    cake_name = request.form.get("cake_name")
    image     = request.form.get("image", "")
    price     = int(request.form.get("price", 0))
    qty       = int(request.form.get("qty", 1))
    cart = session.get("cart", [])
    for item in cart:
        if item["id"] == cake_id:
            item["qty"] += qty
            item["total"] = item["qty"] * item["price"]
            session["cart"] = cart
            session.modified = True
            save_cart_for_user(session.get("user"), cart)
            return redirect(url_for("welcome"))
    cart.append({"id": cake_id, "name": cake_name, "price": price, "qty": qty, "total": price * qty, "image": image})
    session["cart"] = cart
    session.modified = True
    save_cart_for_user(session.get("user"), cart)
    flash("🍰 Added to cart successfully!", "success")
    return redirect(url_for("welcome"))

@app.route("/cart/update", methods=["POST"])
def cart_update():
    cake_id = request.form.get("cake_id")
    qty     = int(request.form.get("qty", 1))
    cart = session.get("cart", [])
    for item in cart:
        if item["id"] == cake_id:
            item["qty"]   = max(1, qty)
            item["total"] = item["qty"] * item["price"]
    session["cart"] = cart
    session.modified = True
    save_cart_for_user(session.get("user"), cart)
    return redirect(url_for("cart"))

@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    cake_id = request.form.get("cake_id")
    session["cart"] = [i for i in session.get("cart", []) if i["id"] != cake_id]
    session.modified = True
    save_cart_for_user(session.get("user"), session.get("cart", []))
    return redirect(url_for("cart"))

@app.route("/cart")
def cart():
    if not session.get("user"):
        return redirect("/")
    cart_items = session.get("cart", [])
    subtotal   = sum(i["total"] for i in cart_items)
    return render_template("cart.html", cart=cart_items, subtotal=subtotal, cart_count=cart_count())

@app.route("/cart/checkout", methods=["POST"])
def cart_checkout():
    cart_items = session.get("cart", [])
    if not cart_items:
        return redirect(url_for("cart"))
    subtotal  = sum(i["total"] for i in cart_items)
    cake_list = ", ".join(f"{i['name']}×{i['qty']}" for i in cart_items)
    return render_template("payment.html", cake=cake_list, amount=subtotal, from_cart=True, rzp_key_id=RZP_KEY_ID)

# ---------------- PAYMENT / ORDER ROUTES ----------------

@app.route("/payment")
def payment():
    cake   = request.args.get("cake")
    amount = request.args.get("amount")
    return render_template("payment.html", cake=cake, amount=amount, from_cart=False, rzp_key_id=RZP_KEY_ID)

@app.route("/confirm-order", methods=["POST"])
def confirm_order():
    payment_method = request.form.get("payment_method", "Razorpay")
    cake           = request.form.get("cake")
    price          = request.form.get("price")
    from_cart      = request.form.get("from_cart") == "True"
    
    if payment_method == "COD":
        orders.insert_one({
            "user":    session.get("user", "guest"),
            "cake":    cake,
            "price":   price,
            "payment": "Cash on Delivery",
            "status":  "Pending Delivery"
        })
        display_payment = "Cash on Delivery (COD)"
    else:
        # Razorpay payment verification
        rzp_payment_id = request.form.get("razorpay_payment_id")
        rzp_order_id   = request.form.get("razorpay_order_id")
        rzp_signature  = request.form.get("razorpay_signature")
        
        orders.insert_one({
            "user":    session.get("user", "guest"),
            "cake":    cake,
            "price":   price,
            "payment": "Razorpay",
            "rzp_payment_id": rzp_payment_id,
            "rzp_order_id": rzp_order_id,
            "status":  "Pending"
        })
        display_payment = "Razorpay Secure"
    
    if from_cart:
        session["cart"] = []
        session.modified = True
        save_cart_for_user(session.get("user"), [])
    return render_template("success.html", cake=cake, price=price, payment=display_payment)

@app.route("/razorpay/create-order", methods=["POST"])
def rzp_create_order():
    try:
        amount = int(request.json.get("amount", 0)) * 100 # In paise
        data = { "amount": amount, "currency": "INR", "receipt": "order_rcptid_11" }
        order = rzp_client.order.create(data=data)
        return jsonify(order)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

# ---------------- POLICY PAGES ----------------

POLICY_TITLES = {
    "privacy": "Privacy Policy",
    "terms": "Terms & Conditions",
    "refund": "Cancellation & Refund Policy",
    "shipping": "Shipping & Delivery Policy",
    "contact": "Contact Us"
}

@app.route("/policy/<page>")
def policy(page):
    if page not in POLICY_TITLES:
        return redirect(url_for("welcome"))
    return render_template("policy.html", page=page, title=POLICY_TITLES[page])


# ---------------- ADMIN ROUTES ----------------



@app.route("/admin")
def admin():
    if not is_admin():
        return redirect("/")
    all_cakes  = list(cakes.find())
    all_orders = list(orders.find().sort("_id", -1).limit(50))
    for c in all_cakes:
        c["_id"] = str(c["_id"])
    for o in all_orders:
        o["_id"] = str(o["_id"])
    total_revenue = sum(int(o.get("price", 0)) for o in all_orders if o.get("status") != "Rejected")
    return render_template("admin.html",
        cakes=all_cakes, orders=all_orders,
        total_orders=len(all_orders), total_cakes=len(all_cakes),
        total_revenue=total_revenue
    )

@app.route("/admin/add-cake", methods=["POST"])
def admin_add_cake():
    if not is_admin():
        return redirect("/")
    name   = request.form.get("name", "").strip()
    desc   = request.form.get("description", "").strip()
    price  = int(request.form.get("price", 0))
    price_half = int(request.form.get("price_half", 0))
    badge  = request.form.get("badge", "").strip()
    image_url = ""
    file = request.files.get("image")
    if file and file.filename and allowed_file(file.filename):
        filename  = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        image_url = f"/static/uploads/{filename}"
    elif request.form.get("image_url"):
        image_url = request.form.get("image_url").strip()
    cakes.insert_one({
        "name": name, "description": desc, "price": price, "price_half": price_half,
        "image": image_url, "badge": badge, "badge_color": "#ff6f61"
    })
    return redirect(url_for("admin"))


@app.route("/admin/update-cake/<cake_id>", methods=["POST"])
def admin_update_cake(cake_id):
    if not is_admin():
        return redirect("/")
    price = int(request.form.get("price", 0))
    price_half = int(request.form.get("price_half", 0))
    desc  = request.form.get("description", "").strip()
    cakes.update_one({"_id": ObjectId(cake_id)}, {"$set": {"price": price, "price_half": price_half, "description": desc}})
    return redirect(url_for("admin"))

@app.route("/admin/delete-cake/<cake_id>", methods=["POST"])
def admin_delete_cake(cake_id):
    if not is_admin():
        return redirect("/")
    cakes.delete_one({"_id": ObjectId(cake_id)})
    return redirect(url_for("admin"))

@app.route("/admin/order/accept/<order_id>", methods=["POST"])
def admin_accept_order(order_id):
    if not is_admin():
        return redirect("/")
    orders.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "Accepted"}})
    return redirect(url_for("admin"))

@app.route("/admin/order/reject/<order_id>", methods=["POST"])
def admin_reject_order(order_id):
    if not is_admin():
        return redirect("/")
    orders.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "Rejected"}})
    return redirect(url_for("admin"))

# ---------------- MAIN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
