"""
model.py
Contains: Intersection, Network, Simulator, Webster formula.
"""

import math
import random


#  INTERSECTION

class Intersection:
    """
    One signalized intersection where two roads cross.

    Phase 0 = North-South has green
    Phase 1 = East-West has green

    Each direction has:
      arrival_rate  — cars arriving per second (lambda)
      lanes         — number of lanes (affects how many cars can leave per second)
    """

    # Saturation flow: cars per second that can pass per lane during green
    SAT_FLOW = 0.5

    def __init__(self, row, col):
        self.row = row
        self.col = col

        # Traffic parameters
        # Order: [North, South, East, West]
        self.arrival_rate = [0.3, 0.3, 0.3, 0.3]
        self.lanes        = [1,   1,   1,   1  ]

        # Signal state
        self.green_times  = [30.0, 30.0]  # seconds of green per phase (Uniform)
        self.yellow_time  = 3.0
        self.current_phase = 0
        self.phase_timer   = 0.0
        self.in_yellow     = False

        # Queues: cars waiting per direction
        self.queue = [0.0, 0.0, 0.0, 0.0]

        # Stats
        self.cars_passed = 0.0
        self.queue_sum   = 0.0
        self.ticks       = 0

    #Webster formula

    def flow_ratios(self):
        """
        y1 = critical flow ratio for NS phase
        y2 = critical flow ratio for EW phase
        Flow ratio = arrival_rate / saturation_flow
        """
        s_ns = self.SAT_FLOW * max(self.lanes[0], self.lanes[1])
        s_ew = self.SAT_FLOW * max(self.lanes[2], self.lanes[3])
        lambda_ns = self.arrival_rate[0] + self.arrival_rate[1]
        lambda_ew = self.arrival_rate[2] + self.arrival_rate[3]
        y1 = lambda_ns / s_ns if s_ns > 0 else 0
        y2 = lambda_ew / s_ew if s_ew > 0 else 0
        return y1, y2

    def compute_webster(self):
        """
        Webster's optimal cycle formula:
            C = (1.5L + 5) / (1 - Y)
            gi = (C - L) * (yi / Y)

        L = total lost time per cycle (2 phases x 3s each = 6s) 
        Y = y1 + y2
        Returns (cycle, green_ns, green_ew) all in seconds.
        """
        L = 6.0
        y1, y2 = self.flow_ratios()
        Y = min(y1 + y2, 0.95)  # cap at 0.95 to avoid blow-up

        C = (1.5 * L + 5) / (1 - Y)
        C = max(20.0, min(C, 120.0))  # clamp to sensible range

        effective_green = C - L
        if Y == 0:
            g1 = g2 = effective_green / 2
        else:
            g1 = effective_green * (y1 / Y)
            g2 = effective_green * (y2 / Y)

        # Each phase needs at least 5s
        g1 = max(5.0, min(g1, C - 10))
        g2 = max(5.0, min(g2, C - 10))
        return C, g1, g2

    def apply_webster(self):
        _, g1, g2 = self.compute_webster()
        self.green_times = [g1, g2]

    def apply_uniform(self, green=30.0):
        self.green_times = [green, green]

    #Simulation tick

    def tick(self, dt=1.0):
        """Advance simulation by dt seconds."""
        # 1. Cars arrive (Poisson random process)
        for d in range(4):
            self.queue[d] += _poisson(self.arrival_rate[d] * dt)

        # 2. Cars depart on green directions
        if not self.in_yellow:
            green_dirs = [0, 1] if self.current_phase == 0 else [2, 3]
            for d in green_dirs:
                capacity = self.SAT_FLOW * self.lanes[d] * dt
                leaving = min(self.queue[d], capacity)
                self.queue[d] -= leaving
                self.cars_passed += leaving

        # 3. Accumulate queue for averaging
        self.queue_sum += sum(self.queue)
        self.ticks += 1

        # 4. Advance phase timer
        self.phase_timer += dt
        if not self.in_yellow:
            if self.phase_timer >= self.green_times[self.current_phase]:
                self.in_yellow = True
                self.phase_timer = 0.0
        else:
            if self.phase_timer >= self.yellow_time:
                self.in_yellow = False
                self.current_phase = 1 - self.current_phase
                self.phase_timer = 0.0

    #Helper

    def is_green(self, direction):
        if self.in_yellow:
            return False
        return direction in ([0, 1] if self.current_phase == 0 else [2, 3])

    def is_yellow(self, direction):
        if not self.in_yellow:
            return False
        return direction in ([0, 1] if self.current_phase == 0 else [2, 3])

    def reset(self):
        self.queue       = [0.0, 0.0, 0.0, 0.0]
        self.cars_passed = 0.0
        self.queue_sum   = 0.0
        self.ticks       = 0
        self.current_phase = 0
        self.phase_timer   = 0.0
        self.in_yellow     = False

    def avg_queue(self):
        return self.queue_sum / self.ticks if self.ticks > 0 else 0.0

    def throughput_per_hour(self, sim_seconds):
        return (self.cars_passed / sim_seconds) * 3600 if sim_seconds > 0 else 0


#  NETWORK  (grid of intersections)

class Network:
    def __init__(self, rows=3, cols=3):
        self.rows = rows
        self.cols = cols
        self.grid = {}
        self._build()

    def _build(self):
        self.grid = {
            (r, c): Intersection(r, c)
            for r in range(self.rows)
            for c in range(self.cols)
        }

    def resize(self, rows, cols):
        old = self.grid.copy()
        self.rows, self.cols = rows, cols
        self.grid = {}
        for r in range(rows):
            for c in range(cols):
                self.grid[(r, c)] = old.get((r, c), Intersection(r, c))

    def get(self, r, c):
        return self.grid.get((r, c))

    def all(self):
        return list(self.grid.values())

    def tick_all(self, dt=1.0):
        for inter in self.all():
            inter.tick(dt)

    def reset_all(self):
        for inter in self.all():
            inter.reset()

    def apply_webster_all(self):
        for inter in self.all():
            inter.apply_webster()

    def apply_uniform_all(self, green=30.0):
        for inter in self.all():
            inter.apply_uniform(green)

    def total_cars(self):
        return sum(i.cars_passed for i in self.all())

    def avg_queue(self):
        lst = self.all()
        return sum(i.avg_queue() for i in lst) / len(lst) if lst else 0


#  SIMULATOR

class SimResult:
    """Stores the outcome of one simulation run."""
    def __init__(self, name):
        self.name              = name
        self.throughput_hr     = 0.0
        self.avg_queue         = 0.0
        self.total_cars        = 0.0
        self.history_cars      = []   # (time_s, cumulative_cars)
        self.history_queue     = []   # (time_s, avg_queue)
        self.per_intersection  = {}   # (r,c) -> dict


class Simulator:
    def __init__(self, network: Network):
        self.network = network

    def run(self, scenario="webster", duration=3600, progress_cb=None):
        """
        Run one simulation scenario.
        scenario: "uniform" or "webster"
        progress_cb: optional function(0.0–1.0) for progress bar
        """
        if scenario == "webster":
            self.network.apply_webster_all()
        else:
            self.network.apply_uniform_all(30.0)
        self.network.reset_all()

        result = SimResult("Webster Optimized" if scenario == "webster"
                           else "Uniform (30s green)")

        # Record ~300 data points regardless of duration
        record_every = max(1, duration // 300)

        for t in range(1, duration + 1):
            self.network.tick_all(1.0)
            if t % record_every == 0:
                result.history_cars.append((t, self.network.total_cars()))
                result.history_queue.append((t, self.network.avg_queue()))
            if progress_cb and t % 50 == 0:
                progress_cb(t / duration)

        result.total_cars    = self.network.total_cars()
        result.throughput_hr = result.total_cars / duration * 3600
        result.avg_queue     = self.network.avg_queue()

        for inter in self.network.all():
            _, g1, g2 = inter.compute_webster()
            result.per_intersection[(inter.row, inter.col)] = {
                "green_ns": inter.green_times[0],
                "green_ew": inter.green_times[1],
                "cars":     inter.cars_passed,
                "tph":      inter.throughput_per_hour(duration),
                "queue":    inter.avg_queue(),
            }
        return result

    def run_comparison(self, duration=3600, progress_cb=None):
        """Run both scenarios and return (uniform, webster)."""
        def cb1(p): progress_cb and progress_cb(p * 0.5)
        def cb2(p): progress_cb and progress_cb(0.5 + p * 0.5)
        uniform = self.run("uniform",  duration, cb1)
        webster = self.run("webster",  duration, cb2)
        return uniform, webster


#  UTILITIES

def _poisson(lam):
    """Generate a Poisson-distributed random integer."""
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(random.gauss(lam, math.sqrt(lam))))
    L, k, p = math.exp(-lam), 0, 1.0
    while p > L:
        p *= random.random()
        k += 1
    return k - 1


def improvement(uniform: SimResult, webster: SimResult):
    """Return (throughput_gain_pct, queue_reduction_pct)."""
    tg = ((webster.throughput_hr - uniform.throughput_hr)
          / uniform.throughput_hr * 100) if uniform.throughput_hr else 0
    qr = ((uniform.avg_queue - webster.avg_queue)
          / uniform.avg_queue * 100) if uniform.avg_queue else 0
    return tg, qr
