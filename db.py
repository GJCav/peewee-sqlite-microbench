import peewee
from peewee import (
    Model, SqliteDatabase, CompositeKey, DatabaseProxy,
    Check
)

# Enable dynamic connection
# Anotate it as SqliteDatabase for better IDE hint
conn: SqliteDatabase = DatabaseProxy()

class Sample(Model):
    id = peewee.AutoField()
    path = peewee.TextField(unique=True)

    class Meta:
        database = conn

class Result(Model):
    # To simplify coding, we stipulate that a.id < b.id
    a = peewee.ForeignKeyField(Sample)
    b = peewee.ForeignKeyField(Sample)

    val = peewee.FloatField(default=-1) # -1 means not calculated yet

    class Meta:
        database = conn
        primary_key = CompositeKey('a', 'b')
        constraints = [Check('a_id < b_id')]

class Attachment(Model):
    key = peewee.CharField(64, primary_key=True)
    val = peewee.CharField()

    class Meta:
        database = conn

def open(path: str, wal = False):
    if wal:
        conn.initialize(SqliteDatabase(path, pragmas={
            'journal_mode': 'wal'
        }))
    else:
        conn.initialize(SqliteDatabase(path, pragmas={
            'journal_mode': 'DELETE'
        }))
    with conn.atomic():
        conn.create_tables([Sample, Result, Attachment])

def close():
    # A little hack to check if db_conn was initialized
    if getattr(conn, 'obj', None):
        conn.close()