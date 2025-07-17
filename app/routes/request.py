from flask import Blueprint, render_template, request, redirect, url_for, session, jsonify
from app.models.db import get_db
import psycopg2.extras

bp = Blueprint('request', __name__, url_prefix='/request')

@bp.route('/list')
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT menu_id, nama FROM menu ORDER BY nama")
    menu_list = cur.fetchall()

    cur.execute("SELECT vendor_id, nama FROM vendor ORDER BY nama")
    vendor_list = cur.fetchall()

    cur.execute("""
        SELECT p.beli_id, p.tanggal, u.nama AS kasir, v.nama AS vendor, p.total, p.keterangan, p.status
        FROM pembelian p
        JOIN pengguna u ON p.user_id = u.user_id
        JOIN vendor v ON p.vendor_id = v.vendor_id
        ORDER BY p.tanggal DESC
    """)
    rows = cur.fetchall()

    # Pisah berdasarkan status
    data_by_status = {
        'pending': [],
        'accepted': [],
        'declined': []
    }

    for row in rows:
        data_by_status[row['status']].append(row)

    return render_template('manajemen/request.html',
        menu_list=menu_list,
        vendor_list=vendor_list,
        data_by_status=data_by_status
    )

@bp.route('/detail-json/<beli_id>')
def detail_json(beli_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    cur.execute("SELECT status FROM pembelian WHERE beli_id = %s", (beli_id,))
    status_row = cur.fetchone()
    status = status_row['status'] if status_row else 'unknown'

    cur.execute("""
        SELECT m.nama, dp.qty, dp.harga_beli, dp.qty * dp.harga_beli AS subtotal
        FROM detail_pembelian dp
        JOIN menu m ON dp.menu_id = m.menu_id
        WHERE dp.beli_id = %s
    """, (beli_id,))
    items = cur.fetchall()

    cur.close()
    conn.close()

    return jsonify({
        "items": [
            {"nama": i['nama'], "qty": i['qty'], "harga_beli": float(i['harga_beli']), "subtotal": float(i['subtotal'])}
            for i in items
        ]
    })

@bp.route('/ubah-status/<beli_id>/<new_status>', methods=['POST'])
def ubah_status(beli_id, new_status):
    if new_status not in ('accepted', 'declined'):
        return "Status tidak valid", 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE pembelian SET status = %s WHERE beli_id = %s", (new_status, beli_id))
    conn.commit()
    cur.close()
    conn.close()

    return redirect(url_for('request.index'))
