import os
import sqlite3
import datetime
import time
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'kunci-rahasia-pencatat-kerja-super-aman'

# Absolute path untuk keamanan di PythonAnywhere
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

# Konfigurasi Upload Foto
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)  # Buat folder otomatis jika belum ada
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def init_db():
    """Membuat tabel dan otomatis migrasi kolom baru (user_id & foto)."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS kegiatan (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tanggal TEXT,
                waktu TEXT,
                deskripsi TEXT,
                user_id INTEGER,
                foto TEXT
            )
        ''')

        # Migrasi otomatis jika tabel lama belum memiliki kolom user_id atau foto
        try:
            conn.execute('ALTER TABLE kegiatan ADD COLUMN user_id INTEGER')
        except sqlite3.OperationalError:
            pass
        
        try:
            conn.execute('ALTER TABLE kegiatan ADD COLUMN foto TEXT')
        except sqlite3.OperationalError:
            pass

init_db()

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        with sqlite3.connect(DB_PATH) as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()

        if user and check_password_hash(user[2], password):
            session['user_id'] = user[0]
            session['username'] = user[1]
            return redirect(url_for('index'))
        else:
            error = 'Username atau password salah!'

    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('index'))

    error = None
    if request.method == 'POST':
        username = request.form.get('username').strip()
        password = request.form.get('password')

        if not username or not password:
            error = 'Username dan password wajib diisi!'
        else:
            hashed_pw = generate_password_hash(password)
            with sqlite3.connect(DB_PATH) as conn:
                try:
                    cursor = conn.cursor()
                    count_users = cursor.execute('SELECT COUNT(*) FROM users').fetchone()[0]

                    cursor.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, hashed_pw))
                    new_user_id = cursor.lastrowid

                    # JIKA INI AKUN PERTAMA: Ikat semua data lama ke akun pertama ini
                    if count_users == 0:
                        cursor.execute('UPDATE kegiatan SET user_id = ? WHERE user_id IS NULL', (new_user_id,))

                    conn.commit()
                    return redirect(url_for('login'))
                except sqlite3.IntegrityError:
                    error = 'Username sudah digunakan, silakan pilih yang lain.'

    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/', methods=['GET', 'POST'])
@login_required
def index():
    user_id = session['user_id']

    # 1. TANGANI PENYIMPANAN DATA BARU (POST)
    if request.method == 'POST':
        tanggal = request.form.get('tanggal')
        waktu = request.form.get('waktu')
        deskripsi = request.form.get('deskripsi')
        
        foto_filename = None
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '' and allowed_file(file.filename):
                # Buat nama file unik memakai timestamp agar tidak bentrok
                nama_aman = secure_filename(file.filename)
                foto_filename = f"{int(time.time())}_{nama_aman}"
                file.save(os.path.join(UPLOAD_FOLDER, foto_filename))

        if tanggal and waktu and deskripsi:
            with sqlite3.connect(DB_PATH) as conn:
                conn.execute(
                    'INSERT INTO kegiatan (tanggal, waktu, deskripsi, user_id, foto) VALUES (?, ?, ?, ?, ?)',
                    (tanggal, waktu, deskripsi, user_id, foto_filename)
                )
        return redirect(url_for('index'))

    # 2. TANGANI FILTER PENCARIAN (GET)
    filter_bulan = request.args.get('bulan', '')
    filter_tahun = request.args.get('tahun', '')

    query = "SELECT * FROM kegiatan WHERE user_id = ?"
    params = [user_id]

    if filter_tahun and filter_bulan:
        query += " AND tanggal LIKE ?"
        params.append(f"{filter_tahun}-{filter_bulan}-%")
    elif filter_tahun:
        query += " AND tanggal LIKE ?"
        params.append(f"{filter_tahun}-%")
    elif filter_bulan:
        query += " AND tanggal LIKE ?"
        params.append(f"%-{filter_bulan}-%")

    query += " ORDER BY tanggal DESC, waktu DESC, id DESC"

    tahun_sekarang = datetime.datetime.now().year
    pilihan_tahun = range(2026, tahun_sekarang + 5)

    with sqlite3.connect(DB_PATH) as conn:
        kegiatan = conn.execute(query, params).fetchall()

    return render_template(
        'index.html',
        kegiatan=kegiatan,
        filter_bulan=filter_bulan,
        filter_tahun=filter_tahun,
        pilihan_tahun=pilihan_tahun,
        username=session.get('username')
    )

@app.route('/edit/<int:id>', methods=['POST'])
@login_required
def edit(id):
    user_id = session['user_id']
    tanggal = request.form.get('tanggal')
    waktu = request.form.get('waktu')
    deskripsi = request.form.get('deskripsi')
    
    with sqlite3.connect(DB_PATH) as conn:
        # Cek data lama untuk keamanan dan foto sebelumnya
        data_lama = conn.execute('SELECT foto FROM kegiatan WHERE id = ? AND user_id = ?', (id, user_id)).fetchone()
        if not data_lama:
            return redirect(url_for('index'))
            
        foto_filename = data_lama[0]
        
        # Jika ada foto baru diunggah, ganti dengan foto baru
        if 'foto' in request.files:
            file = request.files['foto']
            if file and file.filename != '' and allowed_file(file.filename):
                nama_aman = secure_filename(file.filename)
                foto_filename = f"{int(time.time())}_{nama_aman}"
                file.save(os.path.join(UPLOAD_FOLDER, foto_filename))
        
        conn.execute(
            'UPDATE kegiatan SET tanggal = ?, waktu = ?, deskripsi = ?, foto = ? WHERE id = ? AND user_id = ?',
            (tanggal, waktu, deskripsi, foto_filename, id, user_id)
        )
    return redirect(url_for('index'))

@app.route('/delete/<int:id>')
@login_required
def delete(id):
    user_id = session['user_id']
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute('DELETE FROM kegiatan WHERE id = ? AND user_id = ?', (id, user_id))
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)