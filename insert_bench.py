from datetime import datetime, timedelta
import pydantic
import db
import os
import os.path
import json

class InstOption(pydantic.BaseModel):
    sample_count: int = 50
    sample_path_fmt: str = "/tmp/sample-{}"
    test_db_path: str = "bench-insert.db"

## Sample Insertion bench
def time_sample_generation(opt = InstOption()):
    # meanless 
    sample_count = opt.sample_count
    sample_path_fmt = opt.sample_path_fmt

    st = datetime.now()
    for i in range(sample_count):
        path = sample_path_fmt.format(i)
    elapsed = datetime.now() - st
    print(f"Generated {sample_count} samples in {elapsed.microseconds} ms")

    return elapsed

def time_sample_inst_1b1(opt = InstOption()):
    sample_count = opt.sample_count
    sample_path_fmt = opt.sample_path_fmt
    test_db_path = opt.test_db_path

    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    db.open(test_db_path)
    st = datetime.now()
    for i in range(sample_count):
        path = sample_path_fmt.format(i)
        db.Sample.create(path=path)
    count = db.Sample.select().count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} samples in {elapsed}")

    return elapsed

def time_sample_inst_1b1_tsc(opt = InstOption()):
    sample_count = opt.sample_count
    sample_path_fmt = opt.sample_path_fmt
    test_db_path = opt.test_db_path

    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    db.open(test_db_path)
    st = datetime.now()
    with db.conn.atomic() as tsc:
        for i in range(sample_count):
            path = sample_path_fmt.format(i)
            db.Sample.create(path=path)
    count = db.Sample.select().count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} samples in {elapsed}")

    return elapsed

def time_sample_inst_1b1_wal(opt = InstOption()):
    sample_count = opt.sample_count
    sample_path_fmt = opt.sample_path_fmt
    test_db_path = opt.test_db_path

    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    db.open(test_db_path, wal=True)
    st = datetime.now()
    for i in range(sample_count):
        path = sample_path_fmt.format(i)
        db.Sample.create(path=path)
    count = db.Sample.select().count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} samples in {elapsed}")

    return elapsed

def time_sample_inst_1b1_wal_tsc(opt = InstOption()):
    sample_count = opt.sample_count
    sample_path_fmt = opt.sample_path_fmt
    test_db_path = opt.test_db_path

    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    db.open(test_db_path, wal=True)
    st = datetime.now()
    with db.conn.atomic() as tsc:
        for i in range(sample_count):
            path = sample_path_fmt.format(i)
            db.Sample.create(path=path)
    count = db.Sample.select().count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} samples in {elapsed}")

    return elapsed

def time_sample_inst_blk(opt = InstOption()):
    sample_count = opt.sample_count
    sample_path_fmt = opt.sample_path_fmt
    test_db_path = opt.test_db_path

    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    db.open(test_db_path)
    st = datetime.now()
    samples = []
    for i in range(sample_count):
        path = sample_path_fmt.format(i)
        samples.append({"path": path})
    db.Sample.insert_many(samples).execute()
    count = db.Sample.select().count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} samples in {elapsed}")

    return elapsed

def time_sample_inst_wal_blkjson(opt = InstOption()):
    sample_count = opt.sample_count
    sample_path_fmt = opt.sample_path_fmt
    test_db_path = opt.test_db_path

    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    db.open(test_db_path, wal=True)
    st = datetime.now()
    samples = []
    for i in range(sample_count):
        samples.append({"path": sample_path_fmt.format(i)})
    SQL = """
    INSERT INTO sample (path)
    SELECT j.value ->> '$.path'
    FROM json_each(?) AS j;
    """
    db.conn.execute_sql(SQL, (json.dumps(samples),))
    count = db.Sample.select().count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} samples in {elapsed}")

    return elapsed

## Result Insertion Bench
def time_rst_gen(opt = InstOption()):
    sample_count = opt.sample_count

    st = datetime.now()
    rst = [] # mock database insertion
    for i in range(sample_count):
        for j in range(i+1, sample_count):
            rst.append({"a": i, "b": j, "val": 0})
    elapsed = datetime.now() - st
    print(f"Generated {len(rst)} results in {elapsed}")
    return elapsed

def __before_rst_inst(opt: InstOption):
    test_db_path = opt.test_db_path
    sample_count = opt.sample_count
    sample_path_fmt = opt.sample_path_fmt

    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # use sample_inst_blkjson to insert samples
    time_sample_inst_wal_blkjson(opt)
    db.close()

def time_rst_inst_1b1(opt = InstOption()):
    __before_rst_inst(opt)

    test_db_path = opt.test_db_path
    sample_count = opt.sample_count
    
    db.open(test_db_path)
    st = datetime.now()
    for i in range(sample_count):
        for j in range(i+1, sample_count):
            db.Result.create(a=i, b=j, val=-1)
    count = db.Result.select(db.Result.a).count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} results in {elapsed}")

    return elapsed

def time_rst_inst_1b1_tsc(opt = InstOption()):
    __before_rst_inst(opt)

    test_db_path = opt.test_db_path
    sample_count = opt.sample_count
    
    db.open(test_db_path)
    st = datetime.now()
    with db.conn.atomic() as tsc:
        for i in range(sample_count):
            for j in range(i+1, sample_count):
                db.Result.create(a=i, b=j, val=-1)
    count = db.Result.select(db.Result.a).count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} results in {elapsed}")

    return elapsed

def time_rst_inst_1b1_wal(opt = InstOption()):
    __before_rst_inst(opt)

    test_db_path = opt.test_db_path
    sample_count = opt.sample_count
    
    db.open(test_db_path, wal=True)
    st = datetime.now()
    for i in range(sample_count):
        for j in range(i+1, sample_count):
            db.Result.create(a=i, b=j, val=-1)
    count = db.Result.select(db.Result.a).count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} results in {elapsed}")

    return elapsed

def time_rst_inst_1b1_wal_tsc(opt = InstOption()):
    __before_rst_inst(opt)

    test_db_path = opt.test_db_path
    sample_count = opt.sample_count
    
    db.open(test_db_path, wal=True)
    st = datetime.now()
    with db.conn.atomic() as tsc:
        for i in range(sample_count):
            for j in range(i+1, sample_count):
                db.Result.create(a=i, b=j, val=-1)
    count = db.Result.select(db.Result.a).count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} results in {elapsed}")

    return elapsed

def time_rst_inst_blk(opt = InstOption()):
    __before_rst_inst(opt)

    test_db_path = opt.test_db_path
    sample_count = opt.sample_count
    
    db.open(test_db_path)
    st = datetime.now()
    results = []
    for i in range(sample_count):
        for j in range(i+1, sample_count):
            results.append({"a": i, "b": j, "val": 0})
    db.Result.insert_many(results).execute()
    count = db.Result.select(db.Result.a).count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} results in {elapsed}")

    return elapsed

def time_rst_inst_blkjson(opt = InstOption()):
    __before_rst_inst(opt)

    test_db_path = opt.test_db_path
    sample_count = opt.sample_count

    # TODO: add a helper function to build the query automatically for a given model
    SQL = f"""
    INSERT INTO result (a_id, b_id, val)
    SELECT j.value ->> '$[0]', j.value ->> '$[1]', j.value ->> '$[2]'
    FROM json_each(?) AS j;
    """

    db.open(test_db_path)
    st = datetime.now()
    arr = []
    for i in range(sample_count):
        for j in range(i+1, sample_count):
            arr.append([i, j, 0])
    db.conn.execute_sql(SQL, (json.dumps(arr),))
    count = db.Result.select(db.Result.a).count()
    elapsed = datetime.now() - st
    db.close()
    print(f"Inserted {count} results in {elapsed}")

    return elapsed

def time_rst_inst_sql(opt = InstOption()):
    st = datetime.now()
    __before_rst_inst(opt)
    print(f"Preparation done in {datetime.now() - st}")

    test_db_path = opt.test_db_path
    SQL = """
    INSERT INTO result
    SELECT s1.id, s2.id, -1
    FROM sample AS s1 JOIN sample AS s2
    ON s1.id < s2.id;
    """
    db.open(test_db_path)

    import time
    # st = datetime.now()
    st = time.perf_counter()
    db.conn.execute_sql(SQL)
    count = db.Result.select(db.Result.a).count()
    # elapsed = datetime.now() - st
    elapsed = timedelta(seconds=time.perf_counter() - st)
    class Elapsed:
        def __init__(self, elapsed):
            self.elapsed = elapsed
        def total_seconds(self):
            return self.elapsed
    db.close()
    print(f"Inserted {count} results in {elapsed}")

    return elapsed

def time_rst_inst_sql_wal(opt = InstOption()):
    st = datetime.now()
    __before_rst_inst(opt)
    print(f"Preparation done in {datetime.now() - st}")

    test_db_path = opt.test_db_path
    SQL = """
    INSERT INTO result
    SELECT s1.id, s2.id, -1
    FROM sample AS s1 JOIN sample AS s2
    ON s1.id < s2.id;
    """
    db.open(test_db_path, wal=True)
    import time
    # st = datetime.now()
    st = time.perf_counter()
    db.conn.execute_sql(SQL)
    count = db.Result.select(db.Result.a).count()
    # elapsed = datetime.now() - st
    elapsed = timedelta(seconds=time.perf_counter() - st)
    db.close()
    print(f"Inserted {count} results in {elapsed}")

    return elapsed


## Benchmarking
from utils import bench

def bench_sample_inst():
    funcs = [
        time_sample_generation,
        time_sample_inst_1b1,
        time_sample_inst_1b1_tsc,
        time_sample_inst_1b1_wal,
        time_sample_inst_1b1_wal_tsc,
        time_sample_inst_blk,
        time_sample_inst_wal_blkjson
    ]

    opt_list = [
        InstOption(sample_count=10**n) 
        for n in range(2, 6)
    ]

    bench("Sample Insertion", funcs, opt_list, timeout=3, repeat=5)


def bench_rst_inst_slow():
    funcs = [
        time_rst_inst_1b1,
        time_rst_inst_1b1_tsc,
        time_rst_inst_1b1_wal,
    ]

    opt_list = [
        InstOption(sample_count=n)
        for n in range(10, 101, 20)
    ]

    bench("Result Insertion Slow", funcs, opt_list, timeout=3, repeat=5)


def bench_rst_inst_fast():
    funcs = [
        time_rst_gen,
        time_rst_inst_1b1_wal_tsc,
        time_rst_inst_blk,
        time_rst_inst_blkjson
    ]

    opt_list = [
        InstOption(sample_count=n)
        for n in range(100, 1001, 50)
    ]

    bench("Result Insertion Fast", funcs, opt_list, timeout=3, repeat=5)


def bench_rst_inst_sql():
    funcs = [
        # time_rst_gen,
        time_rst_inst_sql,
        time_rst_inst_sql_wal
    ]

    opt_list = [
        InstOption(
            sample_count=n * 100,
            # test_db_path=":memory:",
        )
        for n in range(1, 14)
    ]

    bench("Result Insertion SQL", funcs, opt_list, timeout=10, repeat=5)


if __name__ == "__main__":
    bench_rst_inst_sql()