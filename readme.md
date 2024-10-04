# Peewee & SQLite Performance Optimization



<!-- more -->

## Introduction

In my recent project, I was tasked with optimizing a highly parallelizable computing system that could be distributed across multiple machines. To manage the coordination, I designated one machine as the *coordinator*. This coordinator's role was to dispatch computing jobs to other machines, referred to as *workers*, aggregate the results, and provide an efficient querying interface.

Specifically, the task involved computing pairwise distances for a sample set of size $N$, approximately 2200, resulting in $N(N-1)/2$ sample pairs requiring calculations. Each sample was represented as a high-dimensional vector, and the distance calculation was computiationally intensive and for more complex than simple Euclidean distance. Fortunately, the inherently parallelizable nature of the task meant it could be distributed across multiple machines to achieve a feasible computation time.

Given the computationally intensive nature of the task, preserving the computed results was crucial. While tolerating minor data corruption is acceptable, the integrity of the majority of results must be ensured. Thus, using a robust database management system (DBMS) became necessary. After evaluating factors such as development speed, deployment cost, performance, data reliability and the existing code base, I selected **SQLite** as the storage backend for its balance of these attributes, and **Peewee** as the ORM framework for fast development.

During the project development, I noticed that Peewee and SQLite out of box yielded unsatisifying performance, but with some simple tricks, the performances boosted and the following bench mark was designed to quantify the performance gain.

I categorized operations with SQLite into 2 types: insertion and querying. More specific: 

- Insertion:  occured at task preparation, which inserted plenty of rows into the database to initialize the computing task. It could be further divide into 2 phases
    - sample insertion: register samples in the `sample` table
    - result allocation: pair samples one-by-one and insert the pair with `val = -1`into the `result` table
- Query: orrured at result analyzing, which query distance for a given list of sample pairs

The optimization tricks were:

- WAL: use journal mode of `WAL` instead of the default mode, `DELETE`
- TSC: wrap operations in a transaction
- BLK: insert/query rows in bulk with single SQL execution with a lot of placeholders
- JSON: insert/query rows in bulk and transfer data in JSON instead of using lots of parameter placeholder `?`
- SPC: problem specific tricks that leaverage problem structure and write raw SQL scripts to be executed natively in the SQLite. Usually, SPC tricks are hard to adapt to other problems, but could be extremely efficient 

One trick may be adopted in combination with other tricks to offer even higher performance. A specific combination is denoted as a *method*. The special method that includes no tricks is dentoed as `1b1`, which means that it inserts / queries multiple rows one-by-one. Though the benchmark could not cover all possible methods, it made its best effort to be representative for common usage.

To quantify the performance, row per second (RPS) was selected as the metric. It is defined as the maximum number of rows involved (read/write) in 1 second. The higher RPS a method achieves, the better the performance is. RPS is calculate by timing the insertion/query duration at a series of operation scale. To prevent slow methods from congesting my computer, I set timeout for each test.



## Result & Findings

The following tables list the best performance acheived by different methods.

**RPS for insertions**:

| Tricks   | --               | WAL              | TSC           | TSC + WAL     |
| -------- | ---------------- | ---------------- | ------------- | ------------- |
| **1b1**  | 153.9 (1x)       | 497.4 (3x)       | 13875.0 (90x) | 13960.7 (90x) |
| **BLK**  | 54101.3 (352x)   | --               | --            | --            |
| **JSON** | 289494.5 (1881x) | --               | --            | --            |
| **SPC**  | 612193.6 (3978x) | 601393.5 (3908x) | --            | --            |

- `--` in the column header indicates that no special tricks were used
- `--` in cells means that the method was not tested
- The results are formatted as `absolute rps (speed relative to 1b1)`. For example, `497.4 (3x)` indicates that the method achieves 497.4 rows per seconds, and is 3 times faster than method `1b1`

Based on the results, I found the following primary causes to the poor performance:

- Transaction overhead. Transaction overhead is the time consumed for creating, commiting or rollbacking transactions. It was the primary causes of the poor performance. Simply switching the journal mechanism from `DELETE`, which is the default mode of SQLite, to `WAL` speeded RPS 3 times. The trick has no side effect and is recommended for everyone. It could be done as simple as:

    ``` python
    from peewee import SqliteDatabase
    conn = SqliteDatabase(path, pragmas={'journal_mode': 'wal'}) # Enable WAL
    ```

    To acquire a better performace, wrapping operations in a single transaction when possible gives a huge acceleration, 90 times faster than the `1b1` method. Here is the code for the method `1b1 + TSC`:

    ``` python
    # File: db.py
    class Sample(peewee.Model):
        id = peewee.AutoField()
        path = peewee.TextField(unique=True)
        # ...
    # File: insert_bench.py
    with db.conn.atomic() as tsc: # Wrap writes into a transaction
        for i in range(sample_count):
            path = sample_path_fmt.format(i)
            db.Sample.create(path=path)
    ```

- Binding overhead. Binding overhead is typical introduced by the higher-level librariy, i.e. the Peewee in this benchmark. The bindings adds a lot of overhead to each statement, and slows down the overall performance. For example, in the code of `1b1 + TSC`, each call of `db.Sample.create(path=path)` invokes a SQL execution and adds the unwanted binding overhead. 

    An intuitive optimization is to batch a lot of operations into a single SQL execution, such as `BLK`:

    ``` python
    samples = []
    for i in range(sample_count):
        path = sample_path_fmt.format(i)
        samples.append({"path": path})       # instead of executing SQL in the loop
    db.Sample.insert_many(samples).execute() # batch them into one SQL and execute here
    ```

    It generates SQL like:
    
    ``` SQL
    INSERT INTO sample (path)
    VALUES (?), (?), (?), ..., (?);
    ```
    
    Compared with `1b1 + TSC`, `BLK` method was about 4 times faster.
    
    But for extremely large amount of insertion, the number of parameters, the number of `?` in the SQL, may exceed the SQLite limitation, so transfering data in JSON format is a better option. Here is the cods for `JSON` method:
    
    ``` python
    SQL = """
    INSERT INTO sample (path)
    SELECT j.value ->> '$.path'
    FROM json_each(?) AS j;
    """
    samples = []
    for i in range(sample_count):
        samples.append({"path": sample_path_fmt.format(i)})
    db.conn.execute_sql(SQL, (json.dumps(samples),))
    ```
    
    From the benchmark result, `JSON` method was about 5 times faster than `BLK`. It was the fastest method without leveraging the problem specific structure.

Above methods are universal that could be used in other scenarios. But for this benchmark, the fastest method `SPC` should make use of the problem structure:

``` python
SQL = """
INSERT INTO result
SELECT s1.id, s2.id, -1
FROM sample AS s1 JOIN sample AS s2
ON s1.id < s2.id;
"""
db.conn.execute_sql(SQL)
```

It avoids the third type of overhead, data transfering. It is the overhead for transferring data between Python and SQLite. `SPC` is 2 times faster than `JSON`. Though performant, the method is not as universal as previous methods, as it requires that the information could be directly computed from an existing table, which is not a common situation.



**RPS for query**:

| Tricks   | --             | WAL            |
| -------- | -------------- | -------------- |
| **1b1**  | 4217.2 (1x)    | 5065.9 (1.2x)  |
| **JSON** | 99220.8 (24x)  | 98848.6 (23x)  |
| **SPC**  | 221999.2 (52x) | 217852.7 (52x) |

Query optimization is similar to insertion optimization, but different in terms of transaction overhead, which has far less impact on performance. Querying rows one-by-one gave the RPS of 4217.2, which is quite faster than the insertion. 

To optimize the query performance, we should minimize the binding overhead, but `BLK` trick is not usable. Here is the code of `BLK` method for query:

``` Python
qry_pairs = __gen_qry_pair(opt)
conditions = [
    (db.Result.a == a) & (db.Result.b == b)
    for a, b in qry_pairs
]
conditions = reduce(lambda a, b: a | b, conditions)
qry = db.Result.select().where(conditions)
```

In the benchmark, it quickly ran into error at querying about 60 results. I was not sure if the restriction is posed by Peewee or SQLite, and quicky switched to `JSON` method:

``` Python
SQL = """
SELECT r.a_id, r.b_id, r.val 
FROM result AS r JOIN json_each(?) AS j
WHERE r.a_id = (j.value ->> '$.a') AND r.b_id = (j.value ->> '$.b');
"""
ary_list = []
for a, b in qry_pairs:
    ary_list.append({"a": a, "b": b})
rst = db.conn.execute_sql(SQL, (json.dumps(ary_list),))
```

`JSON` method is 24 times faster than `1b1` and universal for most applications.

In the project mentioned in the introduction, my need was to query the results of any pairs between two sample sets, and it inspired the method denoted as `SPC` in the table. The code is listed bellow:

``` python
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
rst = db.conn.execute_sql(SQL, (json.dumps(idset1), json.dumps(idset2)))
```

It is both convenient and performant, ideal for my project, but may not be used in other applicatons.



## Optimization Advices

1. Enable `WAL` mode in any situation
2. Wrap writes into a single transaction
3. Combine mutiple SQL execution into one execution. The relavent data could be done by either
    1. SQL parameters, more compatible with ORM frameworks
    2. JSON function, more performant but may need to write SQL manually

4. Inspect the problem, and find optimization methods based on the problem structure



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



## RPS Results

### Insertion RPS

Sample Insertion

| Sample Count | 1b1               | 1b1 + TSC           | 1b1 + WAL         | 1b1 + WAL + TSC     | BLK                 | JSON                 |
| :----------- | ----------------- | ------------------- | ----------------- | ------------------- | ------------------- | -------------------- |
| 100          | **153.9** (0.6 s) | 6328.8 (0.0 s)      | 498.8 (0.2 s)     | 9793.2 (0.0 s)      | 12189.2 (0.0 s)     | 40469.4 (0.0 s)      |
| 1000         | TIMEOUT           | 12589.3 (0.1 s)     | **497.4** (2.0 s) | 13482.8 (0.1 s)     | 54946.3 (0.0 s)     | 227241.7 (0.0 s)     |
| 10000        | TIMEOUT           | **13875.0** (0.7 s) | TIMEOUT           | **13960.7** (0.7 s) | **91620.1** (0.1 s) | **365874.2** (0.0 s) |
| 100000       | TIMEOUT           | TIMEOUT             | TIMEOUT           | TIMEOUT             | 86441.1 (1.2 s)     | 332334.6 (0.3 s)     |



Result Allocation (Slow Methods)

| Result Count | 1b1               | 1b1 + WAL         | 1b1 + TSC           |
| :----------- | ----------------- | ----------------- | ------------------- |
| 45           | **138.7** (0.3 s) | 479.7 (0.1 s)     | 3845.6 (0.0 s)      |
| 435          | TIMEOUT           | 494.7 (0.9 s)     | 8805.7 (0.0 s)      |
| 1225         | TIMEOUT           | **494.8** (2.5 s) | 9919.7 (0.1 s)      |
| 2415         | TIMEOUT           | TIMEOUT           | 9890.0 (0.2 s)      |
| 4005         | TIMEOUT           | TIMEOUT           | **10282.4** (0.4 s) |



Result Allocation (Fast Methods)

| Result Count | BLK                 | 1b1 + WAL + TSC     | JSON                 |
| :----------- | ------------------- | ------------------- | -------------------- |
| 4950         | 53335.5 (0.1 s)     | 10288.6 (0.5 s)     | 224493.9 (0.0 s)     |
| 11175        | 52545.4 (0.2 s)     | **10347.7** (1.1 s) | 265938.5 (0.0 s)     |
| 19900        | **54101.3** (0.4 s) | 10334.3 (1.9 s)     | 280637.4 (0.1 s)     |
| 31125        | 52797.5 (0.6 s)     | TIMEOUT             | **289494.5** (0.1 s) |
| 44850        | 51066.5 (0.9 s)     | TIMEOUT             | 283312.1 (0.2 s)     |
| 61075        | 48488.1 (1.3 s)     | TIMEOUT             | 274972.9 (0.2 s)     |
| 79800        | 50185.3 (1.6 s)     | TIMEOUT             | 266527.4 (0.3 s)     |
| 101025       | TIMEOUT             | TIMEOUT             | 281844.1 (0.4 s)     |
| 124750       | TIMEOUT             | TIMEOUT             | 278266.0 (0.4 s)     |
| 150975       | TIMEOUT             | TIMEOUT             | 273094.7 (0.6 s)     |
| 179700       | TIMEOUT             | TIMEOUT             | 274961.6 (0.7 s)     |
| 210925       | TIMEOUT             | TIMEOUT             | 278077.0 (0.8 s)     |
| 244650       | TIMEOUT             | TIMEOUT             | 270197.4 (0.9 s)     |
| 280875       | TIMEOUT             | TIMEOUT             | 271831.2 (1.0 s)     |
| 319600       | TIMEOUT             | TIMEOUT             | 272458.6 (1.2 s)     |
| 360825       | TIMEOUT             | TIMEOUT             | 197347.6 (1.8 s)     |
| 404550       | TIMEOUT             | TIMEOUT             | 165734.0 (2.4 s)     |
| 450775       | TIMEOUT             | TIMEOUT             | TIMEOUT              |
| 499500       | TIMEOUT             | TIMEOUT             | TIMEOUT              |



Result Allocation (Problem Specific Methods)

| Result Count | SPC                  | SPC + WAL            |
| :----------- | -------------------- | -------------------- |
| 4950         | 354747.2 (0.0 s)     | 408807.1 (0.0 s)     |
| 19900        | 556475.2 (0.0 s)     | 571218.6 (0.0 s)     |
| 44850        | 555178.7 (0.1 s)     | **601393.5** (0.1 s) |
| 79800        | 600041.5 (0.1 s)     | 540840.9 (0.1 s)     |
| 124750       | **612193.6** (0.2 s) | 439438.8 (0.3 s)     |
| 179700       | 597780.5 (0.3 s)     | 456027.0 (0.4 s)     |
| 244650       | 610217.8 (0.4 s)     | 451484.7 (0.5 s)     |
| 319600       | 598742.0 (0.5 s)     | 432308.7 (0.7 s)     |
| 404550       | 261878.8 (1.5 s)     | 248389.2 (1.6 s)     |
| 499500       | 199371.1 (2.5 s)     | 186666.5 (2.7 s)     |
| 604450       | 169896.9 (3.6 s)     | 159021.0 (3.8 s)     |
| 719400       | 154525.9 (4.7 s)     | 141470.0 (5.1 s)     |
| 844350       | 141343.6 (6.0 s)     | 126209.7 (6.7 s)     |



### Query RPS

| Query Count | 1b1                | JSON                | SPC                  | 1b1 + WAL          | JSON + WAL          | SPC + WAL            |
| ----------: | :----------------- | :------------------ | :------------------- | :----------------- | :------------------ | :------------------- |
|         100 | 3936.8 (0.0 s)     | 49980.0 (0.0 s)     | 99147.3 (0.0 s)      | 4746.2 (0.0 s)     | 55549.4 (0.0 s)     | 71428.6 (0.0 s)      |
|        1000 | 4077.2 (0.2 s)     | 87725.5 (0.0 s)     | 166666.7 (0.0 s)     | **5065.9** (0.2 s) | 82861.0 (0.0 s)     | 166800.1 (0.0 s)     |
|        2000 | 4116.4 (0.5 s)     | 92591.7 (0.0 s)     | 188686.4 (0.0 s)     | 5009.2 (0.4 s)     | 94344.1 (0.0 s)     | 201373.4 (0.0 s)     |
|        4000 | 3973.5 (1.0 s)     | 94552.8 (0.0 s)     | 215070.0 (0.0 s)     | 4946.8 (0.8 s)     | 95553.0 (0.0 s)     | 223314.0 (0.0 s)     |
|        8000 | 4029.9 (2.0 s)     | 96619.1 (0.1 s)     | 208464.7 (0.0 s)     | 4996.4 (1.6 s)     | 97730.0 (0.1 s)     | 216231.4 (0.0 s)     |
|       10000 | 4084.7 (2.4 s)     | 98878.3 (0.1 s)     | **221999.2** (0.0 s) | 5017.7 (2.0 s)     | 96509.4 (0.1 s)     | 208531.4 (0.0 s)     |
|       11000 | 4078.2 (2.7 s)     | **99220.8** (0.1 s) | 220002.6 (0.0 s)     | 5020.6 (2.2 s)     | 97943.9 (0.1 s)     | 210575.5 (0.1 s)     |
|       12000 | 4141.0 (2.9 s)     | 98586.4 (0.1 s)     | 205541.4 (0.1 s)     | 5039.6 (2.4 s)     | 97616.7 (0.1 s)     | 207652.7 (0.1 s)     |
|       13000 | 4157.3 (3.1 s)     | 98206.0 (0.1 s)     | 210088.8 (0.1 s)     | 5050.9 (2.6 s)     | **98848.6** (0.1 s) | 208302.6 (0.1 s)     |
|       14000 | **4217.2** (3.3 s) | 98754.8 (0.1 s)     | 211585.2 (0.1 s)     | 4890.7 (2.9 s)     | 97996.7 (0.1 s)     | **217852.7** (0.1 s) |
