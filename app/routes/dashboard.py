from flask import Blueprint, render_template, request, redirect, session, url_for
import psycopg2
from flask import g, current_app
from app.models.db import get_db

bp = Blueprint('dashboard', __name__)

@bp.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT user_id, nama, role FROM pengguna WHERE username = %s AND password = %s", (username, password))
        user = cur.fetchone()

        cur.close()
        conn.close()

        if user:
            session['user'] = {
                'user_id': user['user_id'],
                'nama': user['nama'],
                'role': user['role']
            }
            if user['role'] == 'kasir':
                return redirect(url_for('transaksi.index'))
            else:
                return redirect(url_for('dashboard.main'))
        else:
            return render_template('index.html', error='Username atau password salah')

    return render_template('index.html')


@bp.route('/dashboard')
def main():
    if 'user' not in session:
        return redirect(url_for('dashboard.login'))
    return render_template('dashboard/dashboard.html', user=session['user'])

@bp.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('dashboard.login'))
