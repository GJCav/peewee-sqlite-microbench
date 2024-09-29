import multiprocessing as mp
import pydantic
import time
from typing import Any
from datetime import datetime, timedelta
import os
import sys
import json

class RunRst(pydantic.BaseModel):
    rtn: Any = None
    err: str = None
    timeout: bool = False

def run_wrapper(func, args, kwargs, que):
    err = None
    rst = None
    try:
        sys.stdout = open(os.devnull, 'w')
        rst = func(*args, **kwargs)
    except Exception as e:
        err = str(e)
    que.put((rst, err))

def run_with_timeout(func, args=(), kwargs={}, timeout: float = 5) -> RunRst:
    que = mp.Queue()
    p = mp.Process(target=run_wrapper, args=(func, args, kwargs, que))
    p.start()
    p.join(timeout)

    rst = RunRst()
    if p.is_alive():
        rst.timeout = True

        # Ensure the process is terminated
        p.terminate()
        try: p.join(timeout)
        except: raise RuntimeError("Failed to terminate the process")
    
    try: 
        (rtn, err) = que.get_nowait()
        rst.rtn = rtn
        rst.err = err
    except: 
        pass

    return rst


def bench(name, funcs, opt_list, repeat=1, timeout=5, hint=lambda x: f"sample_count = {x.sample_count}"):
    print(f"Start benchmarking {name}")
    print(f"Funcs: ")
    for f in funcs:
        print(f"- {f.__name__}")

    print(f"Options: ")
    for opt in opt_list:
        print(f"- {opt}")
    
    records = {}
    records["options"] = [opt.dict() for opt in opt_list]
    records["results"] = {} # records["results"][fn_name][opt_idx][rpt_idx]

    print("Progress: ")
    for f in funcs:
        fn = f.__name__
        records["results"][fn] = []   
        for opt_idx, opt in enumerate(opt_list):
            rpt_rcds = []
            for r in range(1, repeat + 1):
                print(f"- ({r}/{repeat}) Running {f.__name__}, {hint(opt)}... ", end="")
                rst = run_with_timeout(f, args=(opt,), timeout=timeout)
                if rst.timeout:
                    print("Timeout")
                    rpt_rcds.append(None)
                elif rst.err:
                    print(f"Error: {rst.err}")
                    rpt_rcds.append(-1)
                else:
                    print(f"Done in {rst.rtn}")
                    rpt_rcds.append(rst.rtn.total_seconds())
            records["results"][fn].append(rpt_rcds)
    print("Benchmarking done")

    # Digest
    records["digest"] = {} # records["digest"][fn_name][opt_idx] -> avg time
    for f in funcs:
        fn = f.__name__
        records["digest"][fn] = []
        for opt_idx, opt in enumerate(opt_list):
            rpt_rcds = records["results"][fn][opt_idx]
            rpt_rcds = [r for r in rpt_rcds if r is not None]
            avg_time = sum(rpt_rcds) / len(rpt_rcds) if rpt_rcds else None
            records["digest"][fn].append(avg_time)

    with open(f"data/{name}.json", "w") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)