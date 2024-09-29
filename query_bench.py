from datetime import datetime, timedelta
import pydantic
import db
import os
import os.path
import json
import random
from peewee import fn
from functools import reduce
from math import ceil

class QryOption(pydantic.BaseModel):
    sample_count: int = 1000
    sample_path_fmt: str = "/tmp/sample-{}"
    test_db_path: str = "bench-query.db"

    qry_count: int = 100
    
    bench_id: str = str(random.randint(0, 1000000))
    wal: bool = False


def __prepare_db(opt: QryOption):
    recreate = True
    if os.path.exists(opt.test_db_path):
        db.open(opt.test_db_path, wal=True)
        bench_id = (
            db.Attachment.select(db.Attachment.val)
            .where(db.Attachment.key == "bench_id").get_or_none()
        )
        db.close()
        if bench_id is None: bench_id = None
        else: bench_id = bench_id.val
        # print(f"(opt) {opt.bench_id} ?= {bench_id} (db)")
        if bench_id != opt.bench_id:
            recreate = True
            os.remove(opt.test_db_path)
        else:
            recreate = False
    
    if recreate:
        db.open(opt.test_db_path, wal=True)
        with db.conn.atomic():
            # insert Samples
            samples = []
            for i in range(opt.sample_count):
                path = opt.sample_path_fmt.format(i)
                samples.append({"path": path})
            db.Sample.insert_many(samples).execute()
            count = db.Sample.select().count()
            assert count == opt.sample_count

            # insert results
            SQL = """
            INSERT INTO result
            SELECT s1.id, s2.id, ABS(cast((RANDOM() % 1000) as float)) / 1000
            FROM sample AS s1 JOIN sample AS s2
            ON s1.id < s2.id;
            """
            db.conn.execute_sql(SQL)
            count = db.Result.select().count()
            assert count == opt.sample_count * (opt.sample_count - 1) / 2

            # set benchid
            db.Attachment.insert(
                key="bench_id", val=opt.bench_id
            ).on_conflict_replace().execute()

        db.close()


def __gen_qry_pair(opt: QryOption):
    """
    RANDOMLY and UNIFORMLY sample qry_count (a, b) pairs from 
    strict upper triangle part of the region [0, sample_count] x [0, sample_count].
    """
    qry_count = opt.qry_count
    pairs = []
    for i in range(qry_count):
        a = random.randint(1, opt.sample_count - 1)
        b = random.randint(a + 1, opt.sample_count)
        pairs.append((a, b))
    return pairs


def time_qry_1b1(opt = QryOption()):
    __prepare_db(opt)

    qry_pairs = __gen_qry_pair(opt)
    db.open(opt.test_db_path, wal = opt.wal)
    st = datetime.now()

    valmap = {}
    for a, b in qry_pairs:
        if a >= b:
            raise ValueError(f"Invalid query pair: {a}, {b}")
        val = db.Result.get((db.Result.a == a) & (db.Result.b == b)).val
        valmap[a] = valmap.get(a, {})
        valmap[a][b] = val

    elapsed = datetime.now() - st
    print(f"Donw in {elapsed}")

    return elapsed


def time_qry_blkcnd(opt = QryOption()):
    __prepare_db(opt)

    qry_pairs = __gen_qry_pair(opt)
    db.open(opt.test_db_path, wal = opt.wal)
    
    st = datetime.now()
    conditions = [
        (db.Result.a == a) & (db.Result.b == b)
        for a, b in qry_pairs
    ]
    conditions = reduce(lambda a, b: a | b, conditions)
    qry = db.Result.select().where(conditions)
    valmap = {}
    for r in qry:
        a = r.a
        b = r.b
        valmap[a] = valmap.get(a, {})
        valmap[a][b] = r.val
    
    elapsed = datetime.now() - st
    print(f"Donw in {elapsed}")
    return elapsed


def time_qry_blkjson(opt = QryOption()):
    __prepare_db(opt)

    qry_pairs = __gen_qry_pair(opt)
    db.open(opt.test_db_path, wal = opt.wal)

    SQL = """
    SELECT r.a_id, r.b_id, r.val 
    FROM result AS r JOIN json_each(?) AS j
    WHERE r.a_id = (j.value ->> '$.a') AND r.b_id = (j.value ->> '$.b');
    """

    st = datetime.now()
    ary_list = []
    for a, b in qry_pairs:
        ary_list.append({"a": a, "b": b})
    rst = db.conn.execute_sql(SQL, (json.dumps(ary_list),))
    valmap = {}
    for a, b, val in rst:
        valmap[a] = valmap.get(a, {})
        valmap[a][b] = val
    
    elapsed = datetime.now() - st
    db.close()
    print(f"Donw in {elapsed}")
    return elapsed

def time_qry_idset(opt = QryOption()):
    __prepare_db(opt)

    qry_sz = opt.qry_count
    idset_sz = ceil((1 + (1 + 8 * qry_sz) ** 0.5) / 2) # then idset_sz * (idset_sz - 1) / 2 ~ qry_sz
    idset = [random.randint(0, opt.sample_count - 1) for _ in range(idset_sz)]
    
    SQL = """
    WITH pair AS (
        SELECT DISTINCT
        CASE
            WHEN s1.value < s2.value THEN s1.value
            ELSE s2.value
        END as aid,
        CASE
            WHEN s1.value < s2.value THEN s2.value
            ELSE s1.value
        END as bid
        FROM json_each(?) as s1, json_each(?) as s2
    )
    SELECT aid, bid, r.val
    FROM pair
    JOIN result AS r
    ON r.a_id = pair.aid AND r.b_id = pair.bid;
    """

    db.open(opt.test_db_path, wal = opt.wal)

    st = datetime.now()
    cur = db.conn.execute_sql(SQL, (json.dumps(idset), json.dumps(idset)))
    valmap = {}
    for a, b, val in cur:
        valmap[a] = valmap.get(b, {})
        valmap[a][b] = val
    
    elapsed = datetime.now() - st
    db.close()

    print(f"Donw in {elapsed}")
    return elapsed


## Benchmark
from utils import bench
def bench_qry():
    funcs = [
        time_qry_1b1,
        # time_qry_blkcnd,
        time_qry_blkjson,
        time_qry_idset,
    ]

    bench_id = str(random.randint(0, 1000000))
    __prepare_db(QryOption(bench_id=bench_id))

    opt_list = [
        QryOption(bench_id=bench_id,
                  qry_count=n)
        for n in [
            100, 1000, 2000, 4000, 8000, 10000,
            11000, 12000, 13000, 14000
        ]
    ]

    bench(
        "Result Query", funcs, opt_list,
        timeout=5, repeat=5, hint=lambda x: f"qry_count = {x.qry_count}"
    )


if __name__ == "__main__":
    bench_qry()

