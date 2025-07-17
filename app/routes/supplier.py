from flask import Blueprint, render_template, request, redirect, url_for, session
import psycopg2.extras
from app.models.db import get_db

bp = Blueprint('supplier', __name__, url_prefix='/supplier')

@bp.route('/list')
def index():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    keyword = request.args.get('keyword', '').strip()
    if keyword:
        cur.execute("""
            SELECT vendor_id, nama
            FROM vendor
            WHERE LOWER(nama) LIKE %s OR LOWER(vendor_id) LIKE %s
            ORDER BY nama
        """, (f"%{keyword.lower()}%", f"%{keyword.lower()}%"))
    else:
        cur.execute("SELECT vendor_id, nama, keterangan FROM vendor ORDER BY nama")
    vendors = cur.fetchall()
    cur.close()

    return render_template("vendor/supplier.html", vendors=vendors)


@bp.route('/tambah', methods=['POST'])
def tambah_supplier():
    db = get_db()
    nama = request.form['nama']
    keterangan = request.form.get('keterangan')

    # generate id vendor
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM vendor")
    count = cur.fetchone()[0] + 1
    vendor_id = f'VD{count:03}'

    cur.execute(
        "INSERT INTO vendor (vendor_id, nama, keterangan) VALUES (%s, %s, %s)",
        (vendor_id, nama, keterangan)
    )
    db.commit()
    cur.close()
    return redirect(url_for('supplier.index'))

@bp.route('/hapus/<vendor_id>', methods=['POST'])
def hapus_vendor(vendor_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """SELECT COUNT(*) FROM pembelian WHERE vendor_id = %s""",
        (vendor_id,))
    dependencies = cur.fetchall()

    if any(count[0] > 0 for count in dependencies):
        cur.close()
        return redirect(url_for('supplier.index', toast="Terdapat data pembelian", type="error"))
    cur.execute("DELETE FROM vendor WHERE vendor_id = %s", (vendor_id,))
    conn.commit()
    cur.close()
    return redirect(url_for('supplier.index', toast="Vendor berhasil dihapus", type="success"))

@bp.route('/detail/<vendor_id>')
def pembelian_by_vendor(vendor_id):
    conn = get_db()
    cur = conn.cursor()

    # Ambil data vendor
    cur.execute("SELECT nama, keterangan FROM vendor WHERE vendor_id = %s", (vendor_id,))
    vendor = cur.fetchone()

    # Ambil pembelian yang terkait
    cur.execute("""
        SELECT beli_id, tanggal, total, status, keterangan 
        FROM pembelian 
        WHERE vendor_id = %s 
        ORDER BY tanggal DESC
    """, (vendor_id,))
    pembelian_list = cur.fetchall()

    cur.close()
    return render_template("vendor/supplier_detail.html", vendor=vendor, pembelian_list=pembelian_list, vendor_id=vendor_id)

@bp.route('/hapus-pembelian/<beli_id>', methods=['POST'])
def hapus_pembelian(beli_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("DELETE FROM detail_pembelian WHERE beli_id = %s", (beli_id,))
    cur.execute("DELETE FROM pembelian WHERE beli_id = %s", (beli_id,))

    conn.commit()
    cur.close()

    return redirect(url_for('supplier.index', toast='Data pembelian berhasil dihapus', type='success'))
