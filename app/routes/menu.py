from werkzeug.utils import secure_filename
from flask import Blueprint, render_template, request, redirect, url_for, session
import psycopg2.extras
from app.models.db import get_db
import os

bp = Blueprint('menu', __name__, url_prefix='/menu')

@bp.route('/list')
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    keyword = request.args.get('keyword', '').strip().lower()

    cur.execute("SELECT DISTINCT kategori FROM menu ORDER BY kategori")
    kategori_list = [row['kategori'] for row in cur.fetchall()]

    menu_kategori = {}
    for kategori in kategori_list:
        if keyword:
            cur.execute("""
                SELECT menu_id, nama, harga, stok, image_path 
                FROM menu 
                WHERE kategori = %s AND LOWER(nama) LIKE %s
            """, (kategori, f'%{keyword}%'))
        else:
            cur.execute("""
                SELECT menu_id, nama, harga, stok, image_path 
                FROM menu 
                WHERE kategori = %s
            """, (kategori,))
        
        items = cur.fetchall()
        if items:  # hanya simpan kategori yang ada hasilnya
            menu_kategori[kategori] = items

    return render_template('menu/menu.html',
                           kategori_list=kategori_list,
                           menu_kategori=menu_kategori)


@bp.route('/tambah', methods=['POST'])
def tambah_menu():
    nama = request.form['nama']
    harga = request.form['harga']
    kategori = request.form['kategori']
    kategori_baru = request.form.get('kategori_baru')
    file = request.files.get('gambar')  # ⬅️ bisa None

    conn = get_db()

    def normalisasi_kategori(k):
        return k.strip().capitalize()
    if kategori == '__new__' and kategori_baru:
        kategori = normalisasi_kategori(kategori_baru)
    else:
        kategori = normalisasi_kategori(kategori)
    if kategori_baru and validasi_kategori_menu(conn, kategori_baru):
        conn.close()
        return redirect(url_for('menu.index', toast="Kategori sudah ada!", type="error"))

    cur = conn.cursor()

    new_id = generate_menu_id(cur)
    image_path = None  # default None

    # Gambar diproses klo file ada dan tdk kosong
    if file and file.filename:
        if allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            filename = secure_filename(f"{new_id}.{ext}")
            path_abs = os.path.join(UPLOAD_FOLDER, filename)
            path_relative = f"/static/img/menu_upload/{filename}"
            file.save(path_abs)
            image_path = path_relative
        else:
            conn.close()
            return redirect(url_for('menu.index', toast='Format file tidak didukung.', type='error'))

    cur.execute(
        "INSERT INTO menu (menu_id, nama, harga, kategori, image_path) VALUES (%s, %s, %s, %s, %s)",
        (new_id, nama, harga, kategori, image_path)
    )
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('menu.index', toast="Menu berhasil ditambahkan.", type="success"))

@bp.route('/hapus/<menu_id>', methods=['POST'])
def hapus_menu(menu_id):
    conn = get_db()
    cur = conn.cursor()

    # Validasi constraint
    cur.execute("SELECT COUNT(*) FROM detail_transaksi WHERE menu_id = %s", (menu_id,))
    if cur.fetchone()[0] > 0:
        cur.close()
        conn.close()
        return redirect(url_for('menu.index',toast="Menu sudah memiliki detail transaksi",type="error"))

    cur.execute("SELECT COUNT(*) FROM stok_masuk WHERE menu_id = %s", (menu_id,))
    if cur.fetchone()[0] > 0:
        cur.close()
        conn.close()
        return redirect(url_for('menu.index', toast="Menu sudah memiliki data stok masuk",type="error"))

    cur.execute("DELETE FROM menu WHERE menu_id = %s", (menu_id,))
    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('menu.index'))

def generate_menu_id(cur):
    cur.execute("SELECT menu_id FROM menu WHERE menu_id LIKE 'MN%' ORDER BY menu_id DESC LIMIT 1")
    row = cur.fetchone()

    if row:
        number = int(row[0][2:]) + 1
    else:
        number = 1

    return f"MN{number:03d}"

# Validasi nama kategori biar tidak duplikasi nama (contoh: makanan, mAkanan, Makanan(dengan spasi), MAKANAN)
def validasi_kategori_menu(conn, nama_kategori):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM menu WHERE LOWER(kategori) = LOWER(%s) LIMIT 1", (nama_kategori.strip().lower(),))
    exists = cur.fetchone() is not None
    cur.close()
    return exists

# Upload gambar untuk menu
UPLOAD_FOLDER = 'app/static/img/menu_upload'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@bp.route('/upload-gambar/<menu_id>', methods=['POST'])
def upload_gambar(menu_id):
    file = request.files.get('gambar')
    if not file or file.filename == '':
        return redirect(url_for('menu.index', toast='File tidak valid.', type='error'))

    if allowed_file(file.filename):
        ext = file.filename.rsplit('.', 1)[1].lower()
        filename = secure_filename(f"{menu_id}.{ext}")
        path_abs = os.path.join(UPLOAD_FOLDER, filename)
        path_relative = f"/static/img/menu_upload/{filename}"
        file.save(path_abs)

        conn = get_db()
        cur = conn.cursor()
        cur.execute("UPDATE menu SET image_path = %s WHERE menu_id = %s", (path_relative, menu_id))
        conn.commit()
        cur.close()
        conn.close()

        return redirect(url_for('menu.index', toast='Gambar berhasil diunggah.', type='success'))

    return redirect(url_for('menu.index', toast='Format file tidak didukung.', type='error'))
