from flask import Blueprint, render_template, request, redirect, url_for
from datetime import datetime
from app.models.db import get_db

bp = Blueprint('stok', __name__, url_prefix='/stok')

def render_stok_page(selected_menu_id=None):
    conn = get_db()
    cur = conn.cursor()

    # menu_list (tuple style karena template expect item[0], item[1], item[2])
    cur.execute("SELECT menu_id, nama, stok FROM menu ORDER BY nama")
    menu_list = cur.fetchall()

    # riwayat_stok
    cur.execute("""
        SELECT sm.tanggal, m.nama, sm.jumlah, sm.keterangan
        FROM stok_masuk sm
        JOIN menu m ON sm.menu_id = m.menu_id
        ORDER BY sm.tanggal DESC
        LIMIT 50
    """)
    riwayat_stok = [
        {'tanggal': row[0], 'nama': row[1], 'jumlah': row[2], 'keterangan': row[3]}
        for row in cur.fetchall()
    ]

    cur.close()
    conn.close()

    return render_template('stok.html',
        menu_list=menu_list,
        riwayat_stok=riwayat_stok,
        selected_menu_id=selected_menu_id
    )

@bp.route('/')
def index():
    return render_stok_page()

@bp.route('/tambah', methods=['GET'])
def dari_halaman_menu():
    selected_menu_id = request.args.get('menu_id')
    return render_stok_page(selected_menu_id=selected_menu_id)

@bp.route('/tambah', methods=['POST'])
def tambah_stok():
    menu_id = request.form['menu_id']
    jumlah = int(request.form['jumlah'])
    keterangan = request.form.get('keterangan', '')
    timestamp_str = request.form.get('timestamp')
    try:
        timestamp = datetime.fromisoformat(timestamp_str)
    except Exception:
        timestamp = datetime.now()

    conn = get_db()
    cur = conn.cursor()

    # Generate stok_id
    cur.execute("SELECT stok_id FROM stok_masuk WHERE stok_id LIKE 'SM%' ORDER BY stok_id DESC LIMIT 1")
    row = cur.fetchone()
    if row:
        next_num = int(row[0][2:]) + 1
    else:
        next_num = 1
    stok_id = f'SM{next_num:03d}'

    # Insert ke stok_masuk
    cur.execute("""
        INSERT INTO stok_masuk (stok_id, menu_id, jumlah, tanggal, keterangan)
        VALUES (%s, %s, %s, %s, %s)
    """, (stok_id, menu_id, jumlah, timestamp, keterangan))

    # Update stok di tabel menu
    cur.execute("UPDATE menu SET stok = stok + %s WHERE menu_id = %s", (jumlah, menu_id))

    conn.commit()
    cur.close()
    conn.close()
    return redirect(url_for('stok.index'))
