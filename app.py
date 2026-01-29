from flask import Flask, render_template, request, redirect, url_for, session

app = Flask(__name__)
app.secret_key = "secret_key"

# ---------------- DATA ----------------
users = {"user": "user"}
admin_users = {"admin": "admin"}

blood_inventory = {
    "O+": 10, "O-": 5,
    "A+": 8,  "A-": 4,
    "B+": 6,  "B-": 3,
    "AB+": 2, "AB-": 1
}

blood_requests = []
request_counter = 1


# ---------------- PUBLIC ----------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/about")
def about():
    return render_template("about.html")


# ---------------- USER AUTH ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in users:
            return "User already exists"

        users[username] = password
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in users and users[username] == password:
            session.clear()
            session["username"] = username
            return redirect(url_for("user_dashboard"))

        return "Invalid credentials"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------- USER FEATURES ----------------
@app.route("/dashboard")
def user_dashboard():
    if "username" not in session:
        return redirect(url_for("login"))

    return render_template(
        "user_dashboard.html",
        username=session["username"],
        inventory=blood_inventory,
        requests=blood_requests
    )


@app.route("/request-blood", methods=["GET", "POST"])
def request_blood():
    global request_counter

    if "username" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        qty = int(request.form.get("quantity"))
        
        # Validation: Stop negative or zero requests
        if qty <= 0:
            return "Error: Quantity must be at least 1 unit.", 400

    if request.method == "POST":
        blood_requests.append({
            "id": request_counter,
            "user": session["username"],
            "blood_type": request.form["blood_type"],
            "quantity": qty,
            "urgency": request.form["urgency"],
            "status": "Open"
        })
        request_counter += 1
        return redirect(url_for("user_dashboard"))

    return render_template("request_blood.html")


# ---------------- ADMIN AUTH ----------------
@app.route("/admin/signup", methods=["GET", "POST"])
def admin_signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in admin_users:
            return "Admin already exists"

        admin_users[username] = password
        return redirect(url_for("admin_login"))

    return render_template("admin_signup.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username in admin_users and admin_users[username] == password:
            session.clear()
            session["admin"] = username
            return redirect(url_for("admin_dashboard"))

        return "Invalid admin credentials"

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("index"))


# ---------------- ADMIN FEATURES ----------------
@app.route("/admin/dashboard", methods=["GET", "POST"])
def admin_dashboard():
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        for bt in blood_inventory:
            val = int(request.form.get(bt, 0))
            # Ensure inventory is never negative
            blood_inventory[bt] = max(0, val)

    low_stock_alerts = [bt for bt, units in blood_inventory.items() if units < 3]

    return render_template(
        "admin_dashboard.html",
        username=session["admin"],
        inventory=blood_inventory,
        requests=blood_requests,
        alerts=low_stock_alerts
    )

# Add this under your ADMIN FEATURES section
@app.route("/admin/fulfill/<int:request_id>")
def fulfill_request(request_id):
    if "admin" not in session:
        return redirect(url_for("admin_login"))

    # Find the specific request
    for r in blood_requests:
        if r["id"] == request_id and r["status"] == "Open":
            bt = r["blood_type"]
            qty = int(r["quantity"])

            # Logic: Check if we have enough stock
            if blood_inventory[bt] >= qty:
                blood_inventory[bt] -= qty  # Deduct from inventory
                r["status"] = "Fulfilled"    # Update request status
            else:
                # Optionally, you could pass a flash message here saying "Insufficient stock"
                return "Insufficient blood inventory to fulfill this request", 400
            break
            
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=True)

