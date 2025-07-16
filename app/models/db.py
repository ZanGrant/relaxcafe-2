import psycopg2
import psycopg2.extras
from flask import g, current_app

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(
            dbname=current_app.config['DB_NAME'],
            user=current_app.config['DB_USER'],
            password=current_app.config['DB_PASSWORD'],
            host=current_app.config['DB_HOST']
        )
        # Biar jam nya konsisten WIB (Tidak mengikuti jam yang diset oleh DBMS)
        cur = g.db.cursor()
        cur.execute("SET TIME ZONE 'Asia/Jakarta'")
        cur.close()
    return g.db

def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    app.teardown_appcontext(close_db)
