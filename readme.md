# Peewee & SQLite Performance Optimization

## Introduction

In my recent project, I was tasked with optimizing a highly parallelizable computing system that could be distributed across multiple machines. To manage the coordination, I designated one machine as the *coordinator*. This coordinator's role was to dispatch computing jobs to other machines, referred to as *workers*, aggregate the results, and provide an efficient querying interface.

Specifically, the task involved computing pairwise distances for a sample set of size $N$, approximately 2200, resulting in $N(N-1)/2$ sample pairs requiring calculations. Each sample was represented as a high-dimensional vector, and the distance calculation was computiationally intensive and for more complex than simple Euclidean distance. Fortunately, the inherently parallelizable nature of the task meant it could be distributed across multiple machines to achieve a feasible computation time.

Given the computationally intensive nature of the task, preserving the computed results was crucial. While tolerating minor data corruption is acceptable, the integrity of the majority of results must be ensured. Thus, using a robust database management system (DBMS) became necessary. After evaluating factors such as development speed, deployment cost, performance, data reliability and the existing code base, I selected **SQLite** as the storage backend for its balance of these attributes, and **Peewee** as the ORM framework for fast development.



## Database Schema

The database compromised 2 tables, `sample` and `result`.

Example rows in `sample`

| id   | path              |
| ---- | ----------------- |
| 1    | /dataset/xxxx.mat |
| 2    | /dataset/yyyy.mat |
| ...  | ...               |

- `id` was the self increasing primary key assigned by SQLite
- `path` was the path pointing to the sample file

Example rows in `result`

| a_id | b_id | val  |
| ---- | ---- | ---- |
| 1    | 2    | -1   |
| 1    | 3    | 3    |
| ...  | ...  | ...  |

- `a_id`, `b_id` were foreign keys referring table `sample` and they were also the primary key of `result`. To simplify coding, we stipulated that `a_id` should be smaller than `b_id` and the constraint, `a_id < b_id`, was defined at table creation.
- `val` was the calculation result, with the negitave value as special flags that -1 meant pending for distribution, and -2 meant beening distributed and waiting for a result.



## Benchmark Setup

During the project development, I noticed that Peewee and SQLite out of box yielded unsatisifying performance, but with some simple tricks, the performances boosted and the following bench mark was designed to quantify the performance gain.

I categorized operations with SQLite into 2 types: insertion and querying. More specific: 

- Insertion:  occured at task preparation, which inserted plenty of rows into the database to initialize the computing task. It could be further divide into 2 phases
    - sample insertion: register samples in the `sample` table
    - result allocation: pair samples one-by-one and insert the pair with `val = -1`into the `result` table
- Query: orrured at result analyzing, which query distance for a given list of sample pairs

The optimization tricks were:

- WAL: use journal mode of `WAL` instead of the default mode, `DELETE`
- TSC: wrap operations in a transaction
- BLK: insert/query rows in bulk with single SQL execution
- JSON: insert/query rows in bulk and transfer data in JSON instead of using lots of argument placeholder `?`
- SPC: problem specific tricks that leaverage problem structure and write raw SQL scripts to be executed natively in the SQLite to improve the performance. Usually, SPC tricks are hard to adapt to other problems, but could be extremely efficient 

One trick may be adopted in combination with other tricks to offer even higher performance. A specific combination was denoted as a *method*. The special method that includes no tricks was dentoed as `1b1`, which meant that it insert / query multiple rows one-by-one. Though the benchmark could not cover all possible methods, it made its best effort to be representative for common usage.

To quantify the performance, row per second (RPS) was selected as the metric. It is defined as the maximum number of rows involved (read/write) in 1 second. The higher RPS a method achieves, the better the performance is. RPS is calculate by timing the insertion/query duration at a series of operation scale. To prevent slow methods from congesting my computer, I also set a timeout for each test.

## RPS Results

Sample Insertion

| Sample Count | 1b1       | 1b1 + TSC   | 1b1 + WAL | 1b1 + TSC + WAL | BLK         | JSON+WAL     |
| ------------ | --------- | ----------- | --------- | --------------- | :---------- | :----------- |
| 100          | **153.9** | 6328.8      | 498.8     | 9793.2          | 12189.2     | 40469.4      |
| 1000         | TIMEOUT   | 12589.3     | 497.4     | 13482.8         | 54946.3     | 227241.7     |
| 10000        | TIMEOUT   | **13875.0** | TIMEOUT   | **13960.7**     | **91620.1** | **365874.2** |
| 100000       | TIMEOUT   | TIMEOUT     | TIMEOUT   | TIMEOUT         | 86441.1     | 332334.6     |

Result Allocation (Slow Methods)

| Result Count \ RPS | 1b1       | 1b1 + WAL | 1b1 + TSC   |
| ------------------ | --------- | --------- | :---------- |
| 45                 | **138.7** | 479.7     | 3845.6      |
| 435                | TIMEOUT   | 494.7     | 8805.7      |
| 1225               | TIMEOUT   | **494.8** | 9919.7      |
| 2415               | TIMEOUT   | TIMEOUT   | 9890.0      |
| 4005               | TIMEOUT   | TIMEOUT   | **10282.4** |

Result Allocation (Fast Methods)

| Result Count \ RPS | 1b1 + WAL + TSC | BLK         | JSON         |
| :----------------- | --------------- | ----------- | ------------ |
| 4950               | 10288.6         | 53335.5     | 224493.9     |
| 11175              | **10347.7**     | 52545.4     | 265938.5     |
| 19900              | 10334.3         | **54101.3** | 280637.4     |
| 31125              | TIMEOUT         | 52797.5     | **289494.5** |
| 44850              | TIMEOUT         | 51066.5     | 283312.1     |
| 61075              | TIMEOUT         | 48488.1     | 274972.9     |
| 79800              | TIMEOUT         | 50185.3     | 266527.4     |
| 101025             | TIMEOUT         | ERROR       | 281844.1     |
| 124750             | TIMEOUT         | ERROR       | 278266.0     |
| 150975             | TIMEOUT         | ERROR       | 273094.7     |
| 179700             | TIMEOUT         | ERROR       | 274961.6     |
| 210925             | TIMEOUT         | ERROR       | 278077.0     |
| 244650             | TIMEOUT         | ERROR       | 270197.4     |
| 280875             | TIMEOUT         | ERROR       | 271831.2     |
| 319600             | TIMEOUT         | ERROR       | 272458.6     |
| 360825             | TIMEOUT         | ERROR       | 197347.6     |
| 404550             | TIMEOUT         | ERROR       | 165734.0     |
| 450775             | TIMEOUT         | ERROR       | TIMEOUT      |
| 499500             | TIMEOUT         | ERROR       | TIMEOUT      |

Result Allocation (Problem Specific Methods)

| Result Count \ RPS | SPEC         | SPEC + WAL   |
| :----------------- | :----------- | :----------- |
| 4950               | 357721.0     | 412520.6     |
| 19900              | 528827.8     | 575986.8     |
| 44850              | 559723.8     | **590546.5** |
| 79800              | 588323.8     | 461939.8     |
| 124750             | **590647.2** | 441803.4     |
| 179700             | 577026.1     | 443655.9     |
| 244650             | 587358.6     | 406527.8     |
| 319600             | 571786.0     | 466168.8     |
| 404550             | 248933.3     | 237537.2     |
| 499500             | 192533.9     | 182234.1     |
| 604450             | 164139.3     | 153316.0     |
| 719400             | 145623.2     | 134333.1     |
| 844350             | 132828.9     | 119996.4     |



## Raw Results

### Sample Insertion

| scale <br />(sample_count) | 1b1     | 1b1 + TSC | 1b1 + WAL | 1b1 + TSC + WAL | BLK     | JSON + WAL |
| -------------------------- | ------- | --------- | --------- | --------------- | ------- | ---------- |
| 100                        | 0.649 s | 0.016 s   | 0.200 s   | 0.010 s         | 0.008 s | 0.002 s    |
| 1000                       | TIMEOUT | 0.079 s   | 2.010 s   | 0.074 s         | 0.018 s | 0.004 s    |
| 10000                      | TIMEOUT | 0.721 s   | TIMEOUT   | 0.716 s         | 0.109 s | 0.027 s    |
| 100000                     | TIMEOUT | TIMEOUT   | TIMEOUT   | TIMEOUT         | 1.157 s | 0.301 s    |

- timeout limit = 3 s



### Result Insertion

Note that the operation scale here equals to $N(N-1)/2$, where $N$ is `sample_count`

**Slow Methods**

| sample_count | 1b1     | 1b1 + TSC | 1b1 + WAL |
| ------------ | ------- | --------- | --------- |
| 10           | 0.324 s | 0.012 s   | 0.094 s   |
| 30           | TIMEOUT | 0.049 s   | 0.879 s   |
| 50           | TIMEOUT | 0.123 s   | 2.475 s   |
| 70           | TIMEOUT | 0.244 s   | TIMEOUT   |
| 90           | TIMEOUT | 0.390 s   | TIMEOUT   |

- Timeout limit = 3 s



**Fast Methods**

| sample_count | 1b1 + TSC + WAL | BLK     | JSON    |
| ------------ | --------------- | ------- | ------- |
| 100          | 0.481 s         | 0.093 s | 0.022 s |
| 200          | 1.926 s         | 0.368 s | 0.071 s |
| 300          | TIMEOUT         | 0.878 s | 0.158 s |
| 400          | TIMEOUT         | 1.590 s | 0.299 s |
| 500          | TIMEOUT         | ERROR   | 0.448 s |
| 600          | TIMEOUT         | ERROR   | 0.654 s |
| 700          | TIMEOUT         | ERROR   | 0.905 s |
| 800          | TIMEOUT         | ERROR   | 1.173 s |
| 900          | TIMEOUT         | ERROR   | 2.441 s |
| 1000         | TIMEOUT         | ERROR   | TIMEOUT |



**SPC Methods**



### Result Query

| qry_count | 1b1     | JSON    | SPC     | 1b1 + WAL | JSON + WAL | SPC + WAL |
| --------- | ------- | ------- | ------- | --------- | ---------- | --------- |
| 100       | 0.025 s | 0.002 s | 0.001 s | 0.021 s   | 0.002 s    | 0.001 s   |
| 1000      | 0.245 s | 0.011 s | 0.006 s | 0.197 s   | 0.012 s    | 0.006 s   |
| 2000      | 0.486 s | 0.022 s | 0.011 s | 0.399 s   | 0.021 s    | 0.010 s   |
| 4000      | 1.007 s | 0.042 s | 0.019 s | 0.809 s   | 0.042 s    | 0.018 s   |
| 8000      | 1.985 s | 0.083 s | 0.038 s | 1.601 s   | 0.082 s    | 0.037 s   |
| 10000     | 2.448 s | 0.101 s | 0.045 s | 1.993 s   | 0.104 s    | 0.048 s   |
| 11000     | 2.697 s | 0.111 s | 0.050 s | 2.191 s   | 0.112 s    | 0.052 s   |
| 12000     | 2.898 s | 0.122 s | 0.058 s | 2.381 s   | 0.123 s    | 0.058 s   |
| 13000     | 3.127 s | 0.132 s | 0.062 s | 2.574 s   | 0.132 s    | 0.062 s   |
| 14000     | 3.320 s | 0.142 s | 0.066 s | 2.863 s   | 0.143 s    | 0.064 s   |





## Typical Test Codes

In this section, I listed typical test code for some methods for readers to better understand the tricks and the underlying details. For all codes, readers could check the benchmark repository.

### Database Definition

``` python
# File: db.py
conn: SqliteDatabase = DatabaseProxy()

class Sample(Model): # Model = peewee.Model
    id = peewee.AutoField()
    path = peewee.TextField(unique=True)

    class Meta:
        database = conn
        
class Result(Model):
    a = peewee.ForeignKeyField(Sample)
    b = peewee.ForeignKeyField(Sample)
    val = peewee.FloatField(default=-1)

    class Meta:
        database = conn
        primary_key = CompositeKey('a', 'b')
        constraints = [Check('a_id < b_id')]

def open(path: str, wal = False):
    # open a SQLite database
```

These are the core of `db.py`

- `DatabaseProxy` is chosen because I need to open different database file at runtime
- `open` initializes `conn` with `SqliteDatabase` and set WAL according to the `wal` argument



### Insertion Test

**sample_inst_1b1**

``` python
import db

class InstOption(pydantic.BaseModel):
    sample_count: int = 50
    sample_path_fmt: str = "/tmp/sample-{}"
    test_db_path: str = "bench-insert.db"

def time_sample_inst_1b1(opt = InstOption()):
    sample_count = opt.sample_count
    sample_path_fmt = opt.sample_path_fmt
    test_db_path = opt.test_db_path
    
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
```

- `sample_count` defines the operation scale in the sample insertion operation
- function name `time_sample_inst_1b1` indicates that it is a test for sample insertion operation without any trick (the `1b1` suffix)
- `1b1` is implied by the `for` loop in the code. Each `db.Sample.create` invokes a SQL execution and inserts 1 row into the the table. The samples are inserted one-by-one, thus the abbreviation `1b1`



**sample_inst_1b1_tsc**

``` python
def time_sample_inst_1b1_tsc(opt = InstOption()):
    # ...
    with db.conn.atomic() as tsc:
        for i in range(sample_count):
            path = sample_path_fmt.format(i)
            db.Sample.create(path=path)
    # ...
```

- `with db.conn.atomic() as tsc` opens a transaction and commits it at the exit of the context



**sample_inst_1b1_wal**

Compared with `sample_inst_1b1`, it only differs in one line:

``` python
# in time_sample_inst_1b1
db.open(test_db_path)
# in time_sample_inst_1b1_wal
db.open(test_db_path, wal=True)
```



**sample_inst_blk**

``` python
def time_sample_inst_blk(opt = InstOption()):
    # ...
    samples = []
    for i in range(sample_count):
        path = sample_path_fmt.format(i)
        samples.append({"path": path})
    
    db.Sample.insert_many(samples).execute()
    # ...
```

`db.Sample.insert_many` generates and executes SQL like

``` SQL
INSERT INTO sample (path)
VALUES (?), (?), (?), ..., (?);
```

Note that SQLite limits the number of arguments, the number of `?` in SQL, so this method fails at inserting extremely large bulk of data.



**sample_inst_wal_blkjson**

``` python
def time_sample_inst_wal_blkjson(opt = InstOption()):
    # ...
    samples = []
    for i in range(sample_count):
        samples.append({"path": sample_path_fmt.format(i)})
    SQL = """
    INSERT INTO sample (path)
    SELECT j.value ->> '$.path'
    FROM json_each(?) AS j;
    """
    db.conn.execute_sql(SQL, (json.dumps(samples),))
    # ...
```

It sends data in JSON and thus avoid the limit of argument number. Through benchmark, it is also faster than BLK.



**time_rst_inst_sql**

``` python
def time_rst_inst_sql(opt = InstOption()):
 	# ...
    SQL = """
    INSERT INTO result
    SELECT s1.id, s2.id, -1
    FROM sample AS s1 JOIN sample AS s2
    ON s1.id < s2.id;
    """
    db.conn.execute_sql(SQL)
    # ...
```

- `rst_inst_sql` indicates that the function test result allocation with SPC method
- The `sql` suffix means SPC method. When writing the code, I named it as `sql` because I wrote raw SQL commands  to allocate results.  At writing this report, I found SPC a better name but left my code unchanged



### Query Test

**time_qry_blkcnd**

``` python
def time_qry_blkcnd(opt = QryOption()):
    # ...
    conditions = [
        (db.Result.a == a) & (db.Result.b == b)
        for a, b in qry_pairs
    ]
    conditions = reduce(lambda a, b: a | b, conditions)
    qry = db.Result.select().where(conditions)
    # ...
```

- The `cnd` in function name indicates that arguments are passed to `WHERE` clause



**time_qry_blkjson**

``` python
def time_qry_blkjson(opt = QryOption()):
    # ...
    SQL = """
    SELECT r.a_id, r.b_id, r.val 
    FROM result AS r JOIN json_each(?) AS j
    WHERE r.a_id = (j.value ->> '$.a') AND r.b_id = (j.value ->> '$.b');
    """
    ary_list = []
    for a, b in qry_pairs:
        ary_list.append({"a": a, "b": b})
    qry = db.conn.execute_sql(SQL, (json.dumps(ary_list),))
    # ...
```

