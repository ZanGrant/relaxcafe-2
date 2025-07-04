from flask import Blueprint, render_template, request, redirect, url_for, session
from app.models.db import get_db

bp = Blueprint('menu', __name__, url_prefix='/menu')

@bp.route('/')
def index():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT kategori FROM menu ORDER BY kategori")
    kategori_list = [row[0] for row in cur.fetchall()]

    menu_kategori = {}
    for kategori in kategori_list:
        cur.execute("SELECT menu_id, nama, harga, stok FROM menu WHERE kategori = %s", (kategori,))
        menu_kategori[kategori] = [
            {'menu_id': row[0], 'nama': row[1], 'harga': row[2], 'stok': row[3]}
            for row in cur.fetchall()
        ]

    return render_template('menu.html', kategori_list=kategori_list, menu_kategori=menu_kategori)

@bp.route('/tambah', methods=['POST'])
def tambah_menu():
    nama = request.form['nama']
    harga = request.form['harga']
    kategori = request.form['kategori']
    kategori_baru = request.form.get('kategori_baru')

    conn = get_db()

    # Validasi kategori baru
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
    cur.execute("INSERT INTO menu (menu_id, nama, harga, kategori) VALUES (%s, %s, %s, %s)",
                (new_id, nama, harga, kategori))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('menu.index', toast="Menu berhasil ditambahkan."))

@bp.route('/hapus/<menu_id>', methods=['POST'])
def hapus_menu(menu_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM detail_transaksi WHERE menu_id = %s", (menu_id,))
    if cur.fetchone()[0] > 0:
        cur.close()
        conn.close()
        return redirect(url_for('menu.index'))

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

def validasi_kategori_menu(conn, nama_kategori):
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM menu WHERE LOWER(kategori) = LOWER(%s) LIMIT 1", (nama_kategori.strip().lower(),))
    exists = cur.fetchone() is not None
    cur.close()
    return exists




