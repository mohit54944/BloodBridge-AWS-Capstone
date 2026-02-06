from flask import Flask, render_template, request, redirect, url_for, session, flash
import boto3
import uuid
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

app = Flask(__name__)
app.secret_key = 'bloodbridge_secure_key'  # Use a random string for production

# --- AWS Configuration ---
REGION = 'us-east-1'
SNS_TOPIC_ARN = 'arn:aws:sns:us-east-1:841162686181:bloodbridge_topic'

# Resources using IAM Role (No hardcoded keys for EC2 security)
dynamodb = boto3.resource('dynamodb', region_name=REGION)
sns = boto3.client('sns', region_name=REGION)

# Tables
users_table = dynamodb.Table('Users')
admin_table = dynamodb.Table('AdminUsers')
inventory_table = dynamodb.Table('BloodInventory')
requests_table = dynamodb.Table('BloodRequests')

# --- Helper Functions ---


def send_notification(subject, message):
    """Sends notifications via Amazon SNS."""
    try:
        sns.publish(TopicArn=SNS_TOPIC_ARN, Subject=subject, Message=message)
    except ClientError as e:
        print(f"SNS Error: {e}")


def check_low_stock():
    """Identifies blood types below 3 units and alerts Admin via SNS."""
    items = inventory_table.scan().get('Items', [])
    low_types = [i['blood_type'] for i in items if int(i['quantity']) < 3]
    if low_types:
        send_notification("Low Blood Stock Alert",
                          f"Critical levels detected: {', '.join(low_types)}")


def is_eligible(username):
    """Calculates the 56-day donation window (Scenario 2)."""
    res = users_table.get_item(Key={'username': username})
    last_date_str = res.get('Item', {}).get('last_donation')
    if not last_date_str or last_date_str == "":
        return True, 0

    last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
    next_date = last_date + timedelta(days=56)
    days_remaining = (next_date - datetime.now()).days
    return (days_remaining <= 0), max(0, days_remaining)

# --- PUBLIC ROUTES ---


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/about')
def about():
    return render_template('about.html')

# --- AUTH ROUTES ---


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        users_table.put_item(Item={
            'username': username,
            'password': request.form['password'],
            'last_donation': ''
        })
        send_notification("New User Signup",
                          f"User {username} has joined BloodBridge.")
        return redirect(url_for('login'))
    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        res = users_table.get_item(Key={'username': username})
        if 'Item' in res and res['Item']['password'] == request.form['password']:
            session['username'] = username
            send_notification("Login Alert", f"User {username} logged in.")
            return redirect(url_for('user_dashboard'))
        flash("Invalid credentials!", "danger")
    return render_template('login.html')


@app.route('/admin/signup', methods=['GET', 'POST'])
def admin_signup():
    if request.method == 'POST':
        username = request.form['username']
        admin_table.put_item(
            Item={'username': username, 'password': request.form['password']})
        send_notification("Admin Signup", f"New Admin created: {username}")
        return redirect(url_for('admin_login'))
    return render_template('admin_signup.html')


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        res = admin_table.get_item(Key={'username': username})
        if 'Item' in res and res['Item']['password'] == request.form['password']:
            session['admin'] = username
            return redirect(url_for('admin_dashboard'))
        flash("Invalid admin credentials!", "danger")
    return render_template('admin_login.html')

# --- USER FEATURES ---


@app.route('/dashboard')
def user_dashboard():
    if 'username' not in session:
        return redirect(url_for('login'))

    eligible, days_left = is_eligible(session['username'])
    inv = {i['blood_type']: i['quantity']
           for i in inventory_table.scan()['Items']}
    reqs = requests_table.scan()['Items']

    return render_template('user_dashboard.html',
                           username=session['username'], inventory=inv,
                           requests=reqs, eligible=eligible, days_left=days_left)


@app.route('/request-blood', methods=['GET', 'POST'])
def request_blood():
    if 'username' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        req_id = str(uuid.uuid4())
        qty = int(request.form.get('quantity', 0))
        if qty <= 0:
            flash("Quantity must be at least 1 unit.", "danger")
            return redirect(url_for('request_blood'))

        requests_table.put_item(Item={
            'id': req_id, 'user': session['username'],
            'blood_type': request.form['blood_type'], 'quantity': qty,
            'urgency': request.form['urgency'], 'status': 'Open'
        })
        send_notification(
            "New Request", f"Blood Type {request.form['blood_type']} requested by {session['username']}.")
        return redirect(url_for('user_dashboard'))
    return render_template('request_blood.html')


@app.route('/cancel-request/<req_id>', methods=['POST'])
def cancel_request(req_id):
    """Allow a user to cancel/delete their own open request."""
    if 'username' not in session:
        return redirect(url_for('login'))

    res = requests_table.get_item(Key={'id': req_id})
    req = res.get('Item')

    if not req:
        flash("Request not found.", "danger")
        return redirect(url_for('user_dashboard'))

    if req.get('user') != session['username']:
        flash("You can only cancel your own requests.", "danger")
        return redirect(url_for('user_dashboard'))

    if req.get('status') != 'Open':
        flash("Only open requests can be cancelled.", "danger")
        return redirect(url_for('user_dashboard'))

    requests_table.delete_item(Key={'id': req_id})
    flash("Your request has been cancelled.", "success")
    return redirect(url_for('user_dashboard'))


@app.route('/donate/<req_id>')
def donate_to_request(req_id):
    """User provides blood to fulfill a need (Inventory Increases)."""
    if 'username' not in session:
        return redirect(url_for('login'))

    eligible, _ = is_eligible(session['username'])
    if not eligible:
        flash("You are not yet eligible to donate.", "danger")
        return redirect(url_for('user_dashboard'))

    req = requests_table.get_item(Key={'id': req_id})['Item']
    if req.get('user') == session['username']:
        flash("You cannot donate to your own request.", "danger")
        return redirect(url_for('user_dashboard'))

    bt = req['blood_type']
    qty = int(req['quantity'])

    # Update Inventory (+)
    inv_res = inventory_table.get_item(Key={'blood_type': bt})
    current_qty = int(inv_res.get('Item', {'quantity': 0})['quantity'])
    inventory_table.put_item(
        Item={'blood_type': bt, 'quantity': current_qty + qty})

    # Update Request and User Eligibility
    requests_table.update_item(Key={'id': req_id}, UpdateExpression="set #s = :v",
                               ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':v': 'Donated/Stocked'})
    users_table.update_item(Key={'username': session['username']},
                            UpdateExpression="set last_donation = :d",
                            ExpressionAttributeValues={':d': datetime.now().strftime("%Y-%m-%d")})

    flash(
        f"Thank you! {qty} units of {bt} have been added to stock.", "success")
    return redirect(url_for('user_dashboard'))

# --- ADMIN FEATURES ---


@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        for bt in ['O+', 'O-', 'A+', 'A-', 'B+', 'B-', 'AB+', 'AB-']:
            val = request.form.get(bt)
            if val is not None:
                inventory_table.put_item(
                    Item={'blood_type': bt, 'quantity': int(val)})
        check_low_stock()
        flash("Inventory updated successfully.", "success")

    inv = {i['blood_type']: i['quantity']
           for i in inventory_table.scan()['Items']}
    reqs = requests_table.scan()['Items']
    low_alerts = [bt for bt, q in inv.items() if int(q) < 3]

    return render_template('admin_dashboard.html', username=session['admin'], inventory=inv, requests=reqs, alerts=low_alerts)


@app.route('/admin/fulfill/<req_id>')
def fulfill_request(req_id):
    """Admin dispatches blood to hospital (Inventory Decreases)."""
    if 'admin' not in session:
        return redirect(url_for('admin_login'))

    req = requests_table.get_item(Key={'id': req_id})['Item']
    bt = req['blood_type']
    qty_needed = int(req['quantity'])

    inv_res = inventory_table.get_item(Key={'blood_type': bt})
    current_qty = int(inv_res.get('Item', {'quantity': 0})['quantity'])

    if current_qty >= qty_needed:
        inventory_table.put_item(
            Item={'blood_type': bt, 'quantity': current_qty - qty_needed})
        requests_table.update_item(Key={'id': req_id}, UpdateExpression="set #s = :v",
                                   ExpressionAttributeNames={'#s': 'status'}, ExpressionAttributeValues={':v': 'Dispatched'})
        flash(f"Units dispatched successfully.", "success")
    else:
        flash(f"Insufficient {bt} stock to fulfill this request!", "danger")

    return redirect(url_for('admin_dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
