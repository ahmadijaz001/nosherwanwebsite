#!/usr/bin/env python3
"""
PrestigeMotors UK — Flask + SQLite Backend
Full API: auth, cars, images (stored as base64 blobs in DB), sell submissions, admin users
"""

import sqlite3
import hashlib
import hmac
import os
import base64
import json
import uuid
import re
import time
from datetime import datetime
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, 'db', 'prestigemotors.db')
STATIC_DIR = os.path.join(BASE_DIR, 'static')
SECRET_KEY = 'pm_secret_key_2025_uk'
MAX_IMAGE_SIZE_MB = 8
ALLOWED_EXTS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path='/static')
app.secret_key = SECRET_KEY
CORS(app, origins='*', supports_credentials=True)

# ─────────────────────────────────────────────
# DATABASE HELPERS
# ─────────────────────────────────────────────
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA journal_mode=WAL")
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()

def query(sql, params=(), one=False, commit=False):
    db = get_db()
    cur = db.execute(sql, params)
    if commit:
        db.commit()
        return cur.lastrowid
    rows = cur.fetchone() if one else cur.fetchall()
    return dict(rows) if (one and rows) else ([dict(r) for r in rows] if rows else (None if one else []))

# ─────────────────────────────────────────────
# DB SCHEMA INIT
# ─────────────────────────────────────────────
def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")

    db.executescript("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT    NOT NULL,
        username    TEXT    NOT NULL UNIQUE,
        password_hash TEXT  NOT NULL,
        role        TEXT    NOT NULL DEFAULT 'admin',
        whatsapp    TEXT,
        receive_enquiries INTEGER DEFAULT 0,
        created_at  TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS cars (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        make            TEXT    NOT NULL,
        model           TEXT    NOT NULL,
        year            INTEGER NOT NULL,
        mileage         TEXT,
        price           REAL,
        body_type       TEXT,
        fuel            TEXT,
        transmission    TEXT,
        colour          TEXT,
        engine          TEXT,
        reg             TEXT,
        badge           TEXT,
        description     TEXT,
        status          TEXT    DEFAULT 'active',
        created_at      TEXT    DEFAULT (datetime('now')),
        updated_at      TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS car_images (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        car_id      INTEGER NOT NULL REFERENCES cars(id) ON DELETE CASCADE,
        image_data  BLOB    NOT NULL,
        mime_type   TEXT    NOT NULL DEFAULT 'image/jpeg',
        is_primary  INTEGER DEFAULT 0,
        sort_order  INTEGER DEFAULT 0,
        created_at  TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS sell_submissions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_name     TEXT    NOT NULL,
        seller_phone    TEXT    NOT NULL,
        seller_email    TEXT,
        make            TEXT    NOT NULL,
        model           TEXT    NOT NULL,
        year            INTEGER,
        mileage         TEXT,
        asking_price    REAL,
        reg             TEXT,
        notes           TEXT,
        status          TEXT    DEFAULT 'pending',
        submitted_at    TEXT    DEFAULT (datetime('now')),
        reviewed_at     TEXT,
        reviewed_by     INTEGER REFERENCES admin_users(id)
    );

    CREATE TABLE IF NOT EXISTS submission_images (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        submission_id   INTEGER NOT NULL REFERENCES sell_submissions(id) ON DELETE CASCADE,
        image_data      BLOB    NOT NULL,
        mime_type       TEXT    NOT NULL DEFAULT 'image/jpeg',
        sort_order      INTEGER DEFAULT 0,
        created_at      TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS enquiries (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        car_id      INTEGER REFERENCES cars(id) ON DELETE SET NULL,
        name        TEXT,
        contact     TEXT,
        message     TEXT,
        created_at  TEXT    DEFAULT (datetime('now'))
    );

    CREATE TABLE IF NOT EXISTS sessions (
        token       TEXT    PRIMARY KEY,
        user_id     INTEGER NOT NULL REFERENCES admin_users(id) ON DELETE CASCADE,
        created_at  TEXT    DEFAULT (datetime('now')),
        expires_at  TEXT    NOT NULL
    );
    """)
    db.commit()

    # Seed default super admin if none exists
    existing = db.execute("SELECT COUNT(*) as c FROM admin_users").fetchone()['c']
    if existing == 0:
        ph = hash_password('admin123')
        db.execute(
            "INSERT INTO admin_users (name, username, password_hash, role, whatsapp, receive_enquiries) VALUES (?,?,?,?,?,?)",
            ('Super Admin', 'admin', ph, 'superadmin', '+447587476393', 1)
        )
        # Seed sample cars
        sample_cars = [
            ('BMW',           '5 Series 530d M Sport',      2021, '28,450', 32995, 'Saloon',  'Diesel',  'Automatic', 'Black Sapphire',  '3.0L', 'YD21 BMW', 'Featured', 'Stunning BMW 530d M Sport in Black Sapphire. Full BMW service history, HPI clear, heated seats, panoramic roof, pro navigation. One careful owner.'),
            ('Mercedes-Benz', 'E-Class E220d AMG Line',     2020, '41,200', 27500, 'Saloon',  'Diesel',  'Automatic', 'Obsidian Black',  '2.0L', 'VK70 MBZ', '',         'Elegant E220d AMG Line with full service history. Widescreen digital cockpit, ambient lighting, parking assist.'),
            ('Range Rover',   'Sport HSE Dynamic 3.0',      2022, '19,800', 58900, 'SUV',     'Diesel',  'Automatic', 'Carpathian Grey', '3.0L', 'EV22 RRS', 'New',      'Nearly new Range Rover Sport HSE Dynamic. Meridian audio, 22" alloys, pano roof, air suspension.'),
            ('Audi',          'A6 Avant S Line 40 TDI',     2021, '35,600', 29750, 'Estate',  'Diesel',  'Automatic', 'Daytona Grey',    '2.0L', 'MK21 AUD', '',         'Superb Audi A6 Avant S Line. Virtual cockpit, B&O sound, matrix headlights. Full Audi service history.'),
            ('Porsche',       'Cayenne S E-Hybrid',          2020, '22,400', 64500, 'SUV',     'Hybrid',  'Automatic', 'Carrara White',   '3.0L', 'BX20 POR', 'Premium',  'Exceptional Porsche Cayenne S E-Hybrid. Bose surround, air suspension, heated/ventilated seats.'),
            ('Jaguar',        'XF R-Dynamic SE D200',       2021, '31,100', 26995, 'Saloon',  'Diesel',  'Automatic', 'Eiger Grey',      '2.0L', 'YK21 JAG', '',         'Sporty Jaguar XF R-Dynamic SE. Heated steering, InControl navigation, 19" alloys, blind spot monitor.'),
            ('Volkswagen',    'Golf R 2.0T DSG',             2022, '14,300', 38500, 'Hatchback','Petrol', 'Automatic', 'Lapiz Blue',      '2.0L', 'EV22 VWR', 'New',      'Low mileage Volkswagen Golf R. 320bhp, Akrapovic exhaust, performance pack, IQ.DRIVE, Harman Kardon.'),
            ('BMW',           'X5 xDrive40d M Sport',       2022, '18,900', 55750, 'SUV',     'Diesel',  'Automatic', 'Mineral White',   '3.0L', 'ML22 BMW', '',         'Immaculate BMW X5 40d M Sport. Panoramic roof, 7 seats, Harman Kardon, laser lights, Pro navigation.'),
            ('Lexus',         'LS 500h F Sport',             2020, '29,700', 45995, 'Saloon',  'Hybrid',  'Automatic', 'Sonic Titanium',  '3.5L', 'VK20 LEX', '',         'Ultra-premium Lexus LS 500h F Sport. Mark Levinson audio, climate seats, executive rear lounge.'),
        ]
        car_ids = []
        for sc in sample_cars:
            cur = db.execute(
                "INSERT INTO cars (make,model,year,mileage,price,body_type,fuel,transmission,colour,engine,reg,badge,description) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                sc
            )
            car_ids.append(cur.lastrowid)
        db.commit()

        # Seed dummy images for each sample car (download from Unsplash CDN)
        _seed_sample_images(db, car_ids)

    db.close()
    print("✅ Database initialised at:", DB_PATH)


def _seed_sample_images(db, car_ids):
    """Download and store 4 car photos per sample car from Unsplash CDN."""
    import urllib.request as _req
    PHOTO_SETS = [
        ['1503376780353-7e6692767b70','1494976388531-d1058494cdd8','1552519507-da3b142c6e3d','1605816988069-b11383b50717'],
        ['1617531653332-bd46c16f7c6b','1590362891991-d1c64b313f41','1541899481282-d53bffe3c35d','1503376780353-7e6692767b70'],
        ['1571607388263-1044f9ea01eb','1489824904134-891ab64532f1','1526726538690-5cbf956ae2fd','1555215695-3004980ad54e'],
        ['1606664515524-ed2f786a0bd6','1614162692292-7ac56d7f7f1e','1552519507-da3b142c6e3d','1617531653332-bd46c16f7c6b'],
        ['1580274455191-1c62238fa1c3','1555215695-3004980ad54e','1526726538690-5cbf956ae2fd','1583121274602-3e2820c69888'],
        ['1626668893632-6f3a4466d22f','1606664515524-ed2f786a0bd6','1544636331-e26879cd4d9b','1605816988069-b11383b50717'],
        ['1558618666-fcd25c85cd64','1541899481282-d53bffe3c35d','1503376780353-7e6692767b70','1552519507-da3b142c6e3d'],
        ['1571607388263-1044f9ea01eb','1614162692292-7ac56d7f7f1e','1494976388531-d1058494cdd8','1503376780353-7e6692767b70'],
        ['1590362891991-d1c64b313f41','1617531653332-bd46c16f7c6b','1606664515524-ed2f786a0bd6','1605816988069-b11383b50717'],
    ]
    HDRS = {'User-Agent': 'Mozilla/5.0'}
    BASE = 'https://images.unsplash.com/photo-{id}?w=900&q=72&auto=format&fit=crop'
    for idx, car_id in enumerate(car_ids):
        photos = PHOTO_SETS[idx % len(PHOTO_SETS)]
        for order, pid in enumerate(photos):
            try:
                url = BASE.format(id=pid)
                r = _req.Request(url, headers=HDRS)
                with _req.urlopen(r, timeout=30) as resp:
                    raw  = resp.read()
                    mime = resp.getheader('Content-Type','image/jpeg').split(';')[0].strip()
                    b64  = base64.b64encode(raw).decode()
                db.execute(
                    "INSERT INTO car_images (car_id,image_data,mime_type,is_primary,sort_order) VALUES (?,?,?,?,?)",
                    (car_id, b64, mime, 1 if order==0 else 0, order)
                )
                db.commit()
                print(f"  ✓ image {order+1}/4 → car {car_id}")
            except Exception as e:
                print(f"  ✗ skipped photo {pid}: {e}")

# ─────────────────────────────────────────────
# AUTH HELPERS
# ─────────────────────────────────────────────
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def create_session(user_id):
    token = str(uuid.uuid4()).replace('-', '')
    expires = datetime.fromtimestamp(time.time() + 86400 * 30).strftime('%Y-%m-%d %H:%M:%S')
    query("DELETE FROM sessions WHERE user_id=?", (user_id,), commit=True)
    query("INSERT INTO sessions (token, user_id, expires_at) VALUES (?,?,?)", (token, user_id, expires), commit=True)
    return token

def get_current_user():
    token = request.headers.get('X-Auth-Token') or request.cookies.get('pm_token')
    if not token:
        return None
    row = query("SELECT s.user_id, u.* FROM sessions s JOIN admin_users u ON u.id=s.user_id WHERE s.token=? AND s.expires_at > datetime('now')", (token,), one=True)
    return row

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Unauthorised'}), 401
        g.current_user = user
        return f(*args, **kwargs)
    return decorated

def require_superadmin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = get_current_user()
        if not user:
            return jsonify({'error': 'Unauthorised'}), 401
        if user['role'] != 'superadmin':
            return jsonify({'error': 'Forbidden — Super Admin only'}), 403
        g.current_user = user
        return f(*args, **kwargs)
    return decorated

# ─────────────────────────────────────────────
# IMAGE HELPERS
# ─────────────────────────────────────────────
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTS

def file_to_b64(file_obj):
    data = file_obj.read()
    if len(data) > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        return None, f'Image too large (max {MAX_IMAGE_SIZE_MB}MB)'
    b64 = base64.b64encode(data).decode('utf-8')
    return b64, None

def image_to_data_url(b64_data, mime_type='image/jpeg'):
    if not b64_data:
        return None
    return f"data:{mime_type};base64,{b64_data}"

def car_with_image(car_row):
    """Attach primary image data_url to a car dict."""
    c = dict(car_row)
    img = query(
        "SELECT image_data, mime_type FROM car_images WHERE car_id=? AND is_primary=1 LIMIT 1",
        (c['id'],), one=True
    )
    if not img:
        img = query(
            "SELECT image_data, mime_type FROM car_images WHERE car_id=? ORDER BY sort_order LIMIT 1",
            (c['id'],), one=True
        )
    c['primary_image'] = image_to_data_url(img['image_data'], img['mime_type']) if img else None
    return c

def car_all_images(car_id):
    imgs = query(
        "SELECT id, mime_type, is_primary, sort_order, image_data FROM car_images WHERE car_id=? ORDER BY is_primary DESC, sort_order",
        (car_id,)
    )
    return [{'id': i['id'], 'is_primary': i['is_primary'], 'data_url': image_to_data_url(i['image_data'], i['mime_type'])} for i in imgs]

# ─────────────────────────────────────────────
# SERVE FRONTEND FILES
# ─────────────────────────────────────────────
@app.route('/')
def serve_index():
    return send_from_directory(STATIC_DIR, 'index.html')

@app.route('/admin')
@app.route('/admin.html')
def serve_admin():
    return send_from_directory(STATIC_DIR, 'admin.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(STATIC_DIR, path)

# ─────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.get_json()
    username = (data.get('username') or '').strip().lower()
    password = data.get('password') or ''
    user = query("SELECT * FROM admin_users WHERE username=?", (username,), one=True)
    if not user or user['password_hash'] != hash_password(password):
        return jsonify({'error': 'Invalid credentials'}), 401
    token = create_session(user['id'])
    return jsonify({
        'token': token,
        'user': {
            'id': user['id'], 'name': user['name'],
            'username': user['username'], 'role': user['role'],
            'whatsapp': user['whatsapp'], 'receive_enquiries': user['receive_enquiries']
        }
    })

@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def logout():
    token = request.headers.get('X-Auth-Token') or request.cookies.get('pm_token')
    query("DELETE FROM sessions WHERE token=?", (token,), commit=True)
    return jsonify({'ok': True})

@app.route('/api/auth/me', methods=['GET'])
@require_auth
def me():
    u = g.current_user
    return jsonify({'id': u['id'], 'name': u['name'], 'username': u['username'], 'role': u['role'], 'whatsapp': u['whatsapp']})

# ─────────────────────────────────────────────
# PUBLIC CAR ROUTES
# ─────────────────────────────────────────────
@app.route('/api/cars', methods=['GET'])
def get_cars():
    make     = request.args.get('make', '')
    body     = request.args.get('type', '')
    max_p    = request.args.get('maxPrice', '')
    keyword  = request.args.get('q', '')
    status   = request.args.get('status', 'active')

    sql = "SELECT * FROM cars WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"; params.append(status)
    if make:
        sql += " AND LOWER(make)=LOWER(?)"; params.append(make)
    if body:
        sql += " AND LOWER(body_type)=LOWER(?)"; params.append(body)
    if max_p:
        sql += " AND price<=?"; params.append(float(max_p))
    if keyword:
        sql += " AND (LOWER(make||' '||model) LIKE LOWER(?))"; params.append(f'%{keyword}%')
    sql += " ORDER BY id DESC"

    cars = query(sql, params)
    result = []
    for c in cars:
        result.append(car_with_image(c))
    return jsonify(result)

@app.route('/api/cars/<int:car_id>', methods=['GET'])
def get_car(car_id):
    c = query("SELECT * FROM cars WHERE id=?", (car_id,), one=True)
    if not c:
        return jsonify({'error': 'Not found'}), 404
    c['images'] = car_all_images(car_id)
    return jsonify(c)

@app.route('/api/cars/<int:car_id>/images', methods=['GET'])
def get_car_images(car_id):
    return jsonify(car_all_images(car_id))

# ─────────────────────────────────────────────
# PUBLIC ENQUIRY
# ─────────────────────────────────────────────
@app.route('/api/enquiries', methods=['POST'])
def submit_enquiry():
    data = request.get_json()
    query(
        "INSERT INTO enquiries (car_id, name, contact, message) VALUES (?,?,?,?)",
        (data.get('car_id'), data.get('name'), data.get('contact'), data.get('message')),
        commit=True
    )
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# PUBLIC SELL SUBMISSION (with image upload)
# ─────────────────────────────────────────────
@app.route('/api/submissions', methods=['POST'])
def submit_sell():
    # Supports multipart (with images) or JSON
    if request.content_type and 'multipart' in request.content_type:
        f = request.form
        seller_name  = f.get('seller_name', '').strip()
        seller_phone = f.get('seller_phone', '').strip()
        seller_email = f.get('seller_email', '').strip()
        make         = f.get('make', '').strip()
        model        = f.get('model', '').strip()
        year         = f.get('year')
        mileage      = f.get('mileage', '').strip()
        asking_price = f.get('asking_price')
        reg          = f.get('reg', '').strip()
        notes        = f.get('notes', '').strip()
        files        = request.files.getlist('images')
    else:
        d            = request.get_json() or {}
        seller_name  = d.get('seller_name', '').strip()
        seller_phone = d.get('seller_phone', '').strip()
        seller_email = d.get('seller_email', '').strip()
        make         = d.get('make', '').strip()
        model        = d.get('model', '').strip()
        year         = d.get('year')
        mileage      = d.get('mileage', '').strip()
        asking_price = d.get('asking_price')
        reg          = d.get('reg', '').strip()
        notes        = d.get('notes', '').strip()
        files        = []

    if not seller_name or not seller_phone or not make or not model:
        return jsonify({'error': 'Required fields missing'}), 400

    sub_id = query(
        "INSERT INTO sell_submissions (seller_name,seller_phone,seller_email,make,model,year,mileage,asking_price,reg,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (seller_name, seller_phone, seller_email, make, model, year, mileage, asking_price, reg, notes),
        commit=True
    )

    for i, f in enumerate(files):
        if f and allowed_file(f.filename):
            b64, err = file_to_b64(f)
            if b64:
                mime = f'image/{f.filename.rsplit(".",1)[1].lower()}'
                if mime == 'image/jpg': mime = 'image/jpeg'
                query(
                    "INSERT INTO submission_images (submission_id, image_data, mime_type, sort_order) VALUES (?,?,?,?)",
                    (sub_id, b64, mime, i), commit=True
                )

    return jsonify({'ok': True, 'id': sub_id})

# ─────────────────────────────────────────────
# ADMIN — CARS CRUD
# ─────────────────────────────────────────────
@app.route('/api/admin/cars', methods=['GET'])
@require_auth
def admin_get_cars():
    q_str   = request.args.get('q', '')
    status  = request.args.get('status', '')
    sql = "SELECT * FROM cars WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"; params.append(status)
    if q_str:
        sql += " AND (LOWER(make||' '||model) LIKE LOWER(?))"; params.append(f'%{q_str}%')
    sql += " ORDER BY id DESC"
    cars = query(sql, params)
    result = [car_with_image(c) for c in cars]
    return jsonify(result)

@app.route('/api/admin/cars', methods=['POST'])
@require_auth
def admin_add_car():
    make  = request.form.get('make','').strip()
    model = request.form.get('model','').strip()
    year  = request.form.get('year')
    price = request.form.get('price')
    if not make or not model or not year:
        return jsonify({'error': 'make, model, year required'}), 400

    car_id = query(
        "INSERT INTO cars (make,model,year,mileage,price,body_type,fuel,transmission,colour,engine,reg,badge,description,status) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (make, model, int(year), request.form.get('mileage',''),
         float(price) if price else None,
         request.form.get('body_type',''), request.form.get('fuel','Petrol'),
         request.form.get('transmission','Automatic'), request.form.get('colour',''),
         request.form.get('engine',''), request.form.get('reg',''),
         request.form.get('badge',''), request.form.get('description',''), 'active'),
        commit=True
    )

    files = request.files.getlist('images')
    for i, f in enumerate(files):
        if f and allowed_file(f.filename):
            b64, err = file_to_b64(f)
            if b64:
                mime = f'image/{f.filename.rsplit(".",1)[1].lower()}'
                if mime == 'image/jpg': mime = 'image/jpeg'
                is_primary = 1 if i == 0 else 0
                query(
                    "INSERT INTO car_images (car_id, image_data, mime_type, is_primary, sort_order) VALUES (?,?,?,?,?)",
                    (car_id, b64, mime, is_primary, i), commit=True
                )

    c = query("SELECT * FROM cars WHERE id=?", (car_id,), one=True)
    return jsonify(car_with_image(c)), 201

@app.route('/api/admin/cars/<int:car_id>', methods=['PUT'])
@require_auth
def admin_update_car(car_id):
    # Support both JSON (fields only) and multipart (fields + new images)
    if request.content_type and 'multipart' in request.content_type:
        f = request.form
    else:
        f = request.get_json() or {}

    fields = {}
    mapping = {'make':'make','model':'model','year':'year','mileage':'mileage',
                'price':'price','body_type':'body_type','fuel':'fuel',
                'transmission':'transmission','colour':'colour','engine':'engine',
                'reg':'reg','badge':'badge','description':'description','status':'status'}
    for key, col in mapping.items():
        val = f.get(key) if hasattr(f, 'get') else f.get(key)
        if val is not None:
            if key in ('year',): val = int(val)
            elif key in ('price',): val = float(val) if val else None
            fields[col] = val

    if fields:
        set_clause = ', '.join(f"{k}=?" for k in fields)
        set_clause += ", updated_at=datetime('now')"
        query(f"UPDATE cars SET {set_clause} WHERE id=?", list(fields.values()) + [car_id], commit=True)

    # Handle new images if multipart
    if request.content_type and 'multipart' in request.content_type:
        files = request.files.getlist('images')
        if files and any(f2.filename for f2 in files):
            # Replace images if new ones provided
            query("DELETE FROM car_images WHERE car_id=?", (car_id,), commit=True)
            for i, f2 in enumerate(files):
                if f2 and allowed_file(f2.filename):
                    b64, err = file_to_b64(f2)
                    if b64:
                        mime = f'image/{f2.filename.rsplit(".",1)[1].lower()}'
                        if mime == 'image/jpg': mime = 'image/jpeg'
                        is_primary = 1 if i == 0 else 0
                        query(
                            "INSERT INTO car_images (car_id, image_data, mime_type, is_primary, sort_order) VALUES (?,?,?,?,?)",
                            (car_id, b64, mime, is_primary, i), commit=True
                        )

    c = query("SELECT * FROM cars WHERE id=?", (car_id,), one=True)
    if not c:
        return jsonify({'error': 'Not found'}), 404
    return jsonify(car_with_image(c))

@app.route('/api/admin/cars/<int:car_id>', methods=['DELETE'])
@require_auth
def admin_delete_car(car_id):
    query("DELETE FROM cars WHERE id=?", (car_id,), commit=True)
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# ADMIN — SUBMISSIONS
# ─────────────────────────────────────────────
@app.route('/api/admin/submissions', methods=['GET'])
@require_auth
def admin_get_submissions():
    status = request.args.get('status', '')
    sql = "SELECT * FROM sell_submissions WHERE 1=1"
    params = []
    if status:
        sql += " AND status=?"; params.append(status)
    sql += " ORDER BY submitted_at DESC"
    subs = query(sql, params)

    result = []
    for s in subs:
        s = dict(s)
        # Attach submission images
        imgs = query("SELECT image_data, mime_type FROM submission_images WHERE submission_id=? ORDER BY sort_order", (s['id'],))
        s['images'] = [image_to_data_url(i['image_data'], i['mime_type']) for i in imgs]
        result.append(s)
    return jsonify(result)

@app.route('/api/admin/submissions/<int:sub_id>/approve', methods=['POST'])
@require_auth
def approve_submission(sub_id):
    s = query("SELECT * FROM sell_submissions WHERE id=?", (sub_id,), one=True)
    if not s:
        return jsonify({'error': 'Not found'}), 404

    # Create car listing from submission
    car_id = query(
        "INSERT INTO cars (make,model,year,mileage,price,reg,description,status) VALUES (?,?,?,?,?,?,?,?)",
        (s['make'], s['model'], s['year'] or datetime.now().year,
         s['mileage'] or '', s['asking_price'] or 0, s['reg'] or '',
         s['notes'] or f"Submitted by {s['seller_name']} — {s['seller_phone']}", 'active'),
        commit=True
    )

    # Move submission images to car_images
    imgs = query("SELECT * FROM submission_images WHERE submission_id=? ORDER BY sort_order", (sub_id,))
    for i, img in enumerate(imgs):
        query(
            "INSERT INTO car_images (car_id, image_data, mime_type, is_primary, sort_order) VALUES (?,?,?,?,?)",
            (car_id, img['image_data'], img['mime_type'], 1 if i == 0 else 0, i), commit=True
        )

    query(
        "UPDATE sell_submissions SET status='approved', reviewed_at=datetime('now'), reviewed_by=? WHERE id=?",
        (g.current_user['id'], sub_id), commit=True
    )
    return jsonify({'ok': True, 'car_id': car_id})

@app.route('/api/admin/submissions/<int:sub_id>/reject', methods=['POST'])
@require_auth
def reject_submission(sub_id):
    query(
        "UPDATE sell_submissions SET status='rejected', reviewed_at=datetime('now'), reviewed_by=? WHERE id=?",
        (g.current_user['id'], sub_id), commit=True
    )
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# ADMIN — USERS (Super Admin only)
# ─────────────────────────────────────────────
@app.route('/api/admin/users', methods=['GET'])
@require_superadmin
def admin_get_users():
    users = query("SELECT id,name,username,role,whatsapp,receive_enquiries,created_at FROM admin_users ORDER BY id")
    return jsonify(users)

@app.route('/api/admin/users', methods=['POST'])
@require_superadmin
def admin_add_user():
    d = request.get_json()
    name     = (d.get('name') or '').strip()
    username = (d.get('username') or '').strip().lower()
    password = d.get('password') or ''
    role     = d.get('role', 'admin')
    whatsapp = d.get('whatsapp', '')
    receive  = 1 if d.get('receive_enquiries') else 0
    if not name or not username or not password:
        return jsonify({'error': 'name, username, password required'}), 400
    existing = query("SELECT id FROM admin_users WHERE username=?", (username,), one=True)
    if existing:
        return jsonify({'error': 'Username already exists'}), 409
    uid = query(
        "INSERT INTO admin_users (name,username,password_hash,role,whatsapp,receive_enquiries) VALUES (?,?,?,?,?,?)",
        (name, username, hash_password(password), role, whatsapp, receive), commit=True
    )
    return jsonify({'id': uid, 'name': name, 'username': username, 'role': role}), 201

@app.route('/api/admin/users/<int:user_id>', methods=['PUT'])
@require_superadmin
def admin_update_user(user_id):
    d = request.get_json()
    u = query("SELECT * FROM admin_users WHERE id=?", (user_id,), one=True)
    if not u:
        return jsonify({'error': 'Not found'}), 404
    name     = (d.get('name') or u['name']).strip()
    username = (d.get('username') or u['username']).strip().lower()
    role     = d.get('role', u['role'])
    whatsapp = d.get('whatsapp', u['whatsapp'])
    receive  = 1 if d.get('receive_enquiries') else 0
    password = d.get('password')
    if password:
        query("UPDATE admin_users SET name=?,username=?,role=?,whatsapp=?,receive_enquiries=?,password_hash=? WHERE id=?",
              (name, username, role, whatsapp, receive, hash_password(password), user_id), commit=True)
    else:
        query("UPDATE admin_users SET name=?,username=?,role=?,whatsapp=?,receive_enquiries=? WHERE id=?",
              (name, username, role, whatsapp, receive, user_id), commit=True)
    return jsonify({'ok': True})

@app.route('/api/admin/users/<int:user_id>', methods=['DELETE'])
@require_superadmin
def admin_delete_user(user_id):
    if user_id == g.current_user['id']:
        return jsonify({'error': 'Cannot delete yourself'}), 400
    query("DELETE FROM admin_users WHERE id=?", (user_id,), commit=True)
    return jsonify({'ok': True})

@app.route('/api/admin/users/change-password', methods=['POST'])
@require_auth
def change_password():
    d = request.get_json()
    old_pw = d.get('old_password','')
    new_pw = d.get('new_password','')
    if not new_pw or len(new_pw) < 6:
        return jsonify({'error': 'Password must be at least 6 characters'}), 400
    u = query("SELECT * FROM admin_users WHERE id=?", (g.current_user['id'],), one=True)
    if u['password_hash'] != hash_password(old_pw):
        return jsonify({'error': 'Current password incorrect'}), 400
    query("UPDATE admin_users SET password_hash=? WHERE id=?", (hash_password(new_pw), u['id']), commit=True)
    return jsonify({'ok': True})

# ─────────────────────────────────────────────
# ADMIN — DASHBOARD STATS
# ─────────────────────────────────────────────
@app.route('/api/admin/stats', methods=['GET'])
@require_auth
def admin_stats():
    active_cars = query("SELECT COUNT(*) as c FROM cars WHERE status='active'", one=True)['c']
    total_val   = query("SELECT COALESCE(SUM(price),0) as v FROM cars WHERE status='active'", one=True)['v']
    pending_subs= query("SELECT COUNT(*) as c FROM sell_submissions WHERE status='pending'", one=True)['c']
    total_users = query("SELECT COUNT(*) as c FROM admin_users", one=True)['c']
    sold_cars   = query("SELECT COUNT(*) as c FROM cars WHERE status='sold'", one=True)['c']
    enquiries   = query("SELECT COUNT(*) as c FROM enquiries", one=True)['c']
    return jsonify({
        'active_cars': active_cars, 'total_inventory_value': total_val,
        'pending_submissions': pending_subs, 'total_users': total_users,
        'sold_cars': sold_cars, 'total_enquiries': enquiries
    })

@app.route('/api/admin/enquiries', methods=['GET'])
@require_auth
def admin_get_enquiries():
    rows = query("""
        SELECT e.*, c.make, c.model, c.year FROM enquiries e
        LEFT JOIN cars c ON c.id = e.car_id
        ORDER BY e.created_at DESC LIMIT 50
    """)
    return jsonify(rows)

# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    print("🚀 PrestigeMotors UK server starting on http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
