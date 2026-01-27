# planner/simple_logger.py
import time
from contextlib import contextmanager

class SimpleRunLogger:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.start_time = time.perf_counter()
        self.timings = {}

    def log(self, msg: str):
        print(f"[RUN {self.run_id}] {msg}")

    @contextmanager
    def time_block(self, name: str):
        start = time.perf_counter()
        yield
        elapsed = time.perf_counter() - start
        self.timings[name] = self.timings.get(name, 0) + elapsed
        print(f"[{name.upper()}] {elapsed:.3f}s")

    def finish(self):
        total = time.perf_counter() - self.start_time
        print("=" * 50)
        print(f"[RUN {self.run_id}] TOTAL TIME: {total:.3f}s")
        for k, v in self.timings.items():
            print(f"  - {k}: {v:.3f}s")
        print("=" * 50)
