"""
model.py
Contains all simulation logic. Three new features added:

1. Road Segements: Each connection between intersections (or grid edge)
   has a length (metres) and speed (km/h). Travel time is computed from
   these, and the arrival rate at the downstream intersection is derived
   automatically — no manual entry needed.
2. Bidirectional road segment has been added between two points.

3. Sparse Grid: The network starts empty. Intersections exist only where
   the user has explicitly placed them by clicking.
"""

import math
import random

DEFAULT_SPEED_MS    = 60 * 1000 / 3600   # 60 km/h in m/s ≈ 16.67
DEFAULT_ROAD_LENGTH = 400                 # metres between intersections
DEFAULT_DEMAND_CPH  = 180                 # external entry demand, cars/hour


#Road Segment

class Road:
    """
    A bidirectional road segment between two points.
    Cars travel in both directions simulataneously on the same road.
    Each direction has its own in-transit buffer and its own demand.
    """

    def __init__(self, length_m=DEFAULT_ROAD_LENGTH,
                 speed_ms=DEFAULT_SPEED_MS,
                 demand_cph=DEFAULT_DEMAND_CPH): #demand cars per hour
        
        self.length_m   = length_m
        self.speed_ms   = speed_ms
        self.demand_cph = demand_cph        # cars/hour entering from outside
        self._in_transit = []    
        
        #Two inde[endent transit buffers - one per direction
        #_transit_fwd: cars going from the "lower" cell to the "higher" cell
        #_transit_bwd: cars going the opposite way
        self._transit_fwd = []
        self._transit_bwd = []

    @property
    def travel_time(self):
        """Seconds to drive from one end to the other."""
        return self.length_m / self.speed_ms

    @property
    def arrival_rate(self):
        """External demand converted to cars/second."""
        return self.demand_cph / 3600.0

    def reset(self):
        self._transit_fwd = []
        self._transit_bwd = []

    def release(self, num_cars, current_time, forward=True):
        """
        Put cars onto this road. They arrive after travel_time seconds.
        forwad = True means travelling from lower cell to higher cell.
        forward = False means the opposite direction.
           
        """
        if num_cars > 0:
            arrival = current_time + self.travel_time
            if forward:
                self._transit_bwd.append((arrival, num_cars))
            else:
                self._transit_bwd.append((arrival, num_cars))


    def collect_arrivals(self, current_time, forward=True):
        """ Collect cars that finished travelling in the given direction. """
        buf = self._transit_fwd if forward else self._transit_bwd
        arrived, still = 0.0, []
        for arrive_at, cars in buf:
            if current_time >= arrive_at:
                arrived += cars
            else:
                still.append((arrive_at, cars))

        if forward:
            self._transit_fwd = still
        else:
            self._transit_bwd = still
        return arrived


#Intersection

class Intersection:
    """
    One signalized crossroads.
    Phase 0 = NS green.   Phase 1 = EW green.
    Directions: N=0  S=1  E=2  W=3
    """

    SAT_FLOW = 0.5   # cars/second/lane at saturation

    def __init__(self, row, col):
        self.row  = row
        self.col  = col
        self.lanes = [2, 2, 2, 2]       # lanes per direction [N,S,E,W]

        self.green_times   = [30.0, 30.0]
        self.yellow_time   = 3.0
        self.current_phase = 0
        self.phase_timer   = 0.0
        self.in_yellow     = False

        self.queue        = [0.0, 0.0, 0.0, 0.0]
        self.arrival_rate = [0.0, 0.0, 0.0, 0.0]  # cached, used by Webster

        self.cars_passed = 0.0
        self.queue_sum   = 0.0
        self.ticks       = 0

    def flow_ratios(self):
        s_ns = self.SAT_FLOW * max(self.lanes[0], self.lanes[1])
        s_ew = self.SAT_FLOW * max(self.lanes[2], self.lanes[3])
        y1   = (self.arrival_rate[0] + self.arrival_rate[1]) / s_ns if s_ns else 0
        y2   = (self.arrival_rate[2] + self.arrival_rate[3]) / s_ew if s_ew else 0
        return y1, y2

    def compute_webster(self):
       L = 6.0
       y1, y2 = self.flow_ratios()
       Y = min(y1+y2, 0.95)
       C = max(40.0, min((1.5*L+5)/(1-Y), 120.0))
       eff = C - L
       g1, g2 = (eff/2, eff/2) if Y==0 else (eff*y1/Y, eff*y2/Y)
       return C, max(20.0, min(g1, 120.0)), max(20.0, min(g2, 120.0))

    def apply_webster(self):
        _, g1, g2 = self.compute_webster()
        self.green_times = [g1, g2]

    def apply_uniform(self, green=30.0):
        self.green_times = [green, green]

    def tick(self, dt, incoming):
        """
        incoming: [N, S, E, W] cars arriving this tick (from roads/outside).
        Returns departed: [N, S, E, W] cars that left this tick (to release onto roads).
        """
        for d in range(4):
            self.queue[d] += _poisson(incoming[d])

        departed = [0.0]*4
        if not self.in_yellow:
            for d in ([0,1] if self.current_phase == 0 else [2,3]):
                leaving        = min(self.queue[d], self.SAT_FLOW * self.lanes[d] * dt)
                self.queue[d] -= leaving
                self.cars_passed += leaving
                departed[d]    = leaving

        self.queue_sum += sum(self.queue)
        self.ticks     += 1

        self.phase_timer += dt
        if not self.in_yellow:
            if self.phase_timer >= self.green_times[self.current_phase]:
                self.in_yellow, self.phase_timer = True, 0.0
        else:
            if self.phase_timer >= self.yellow_time:
                self.in_yellow     = False
                self.current_phase = 1 - self.current_phase
                self.phase_timer   = 0.0
        return departed

    def is_green(self, d):
        return (not self.in_yellow) and d in ([0,1] if self.current_phase==0 else [2,3])

    def is_yellow(self, d):
        return self.in_yellow and d in ([0,1] if self.current_phase==0 else [2,3])

    def reset(self):
        self.queue         = [0.0]*4
        self.arrival_rate  = [0.0]*4
        self.cars_passed   = 0.0
        self.queue_sum     = 0.0
        self.ticks         = 0
        self.current_phase = 0
        self.phase_timer   = 0.0
        self.in_yellow     = False

    def avg_queue(self):
        return self.queue_sum / self.ticks if self.ticks else 0.0

    def throughput_per_hour(self, sim_sec):
        return (self.cars_passed / sim_sec) * 3600 if sim_sec else 0


#Network

class Network:
    """
    A sparse grid. Intersections exist only where the user places them.
    Road segments connect adjacent intersections or serve as entry points
    from outside the grid at exposed edges.
    """

    def __init__(self, rows=6, cols=6):
        self.rows = rows   # canvas grid size (max dimensions)
        self.cols = cols
        self.grid        = {}   # {(r,c): Intersection}
        self.roads       = {}   # {canonical_key: Road}  — internal roads
        self.entry_roads = {}   # {((r,c), direction): Road} — external entry

        self.default_length_m   = DEFAULT_ROAD_LENGTH
        self.default_speed_ms   = DEFAULT_SPEED_MS
        self.default_demand_cph = DEFAULT_DEMAND_CPH

#Placing/Removing intersections

    def toggle(self, r, c):
        """Add intersection if absent, remove if present."""
        if (r, c) in self.grid:
            self._remove(r, c)
        else:
            self._add(r, c)

    def _add(self, r, c):
        self.grid[(r, c)] = Intersection(r, c)
        self._rebuild_roads(r, c)
        # Also rebuild roads for existing neighbours (they gain a new internal road)
        for nr, nc in self._adj(r, c):
            if (nr, nc) in self.grid:
                self._rebuild_roads(nr, nc)

    def _remove(self, r, c):
        del self.grid[(r, c)]
        # Delete all roads touching this cell
        self.roads       = {k: v for k, v in self.roads.items()       if (r,c) not in k}
        self.entry_roads = {k: v for k, v in self.entry_roads.items() if k[0] != (r,c)}
        # Rebuild neighbours — they may now have new exposed edges
        for nr, nc in self._adj(r, c):
            if (nr, nc) in self.grid:
                self._rebuild_roads(nr, nc)

    def _rebuild_roads(self, r, c):
        """
        For intersection (r,c), create:
          - An internal Road to each existing adjacent intersection
          - An external entry Road for each direction that has NO neighbour
        """
        nbr = {0:(r-1,c), 1:(r+1,c), 2:(r,c+1), 3:(r,c-1)}
        for d, (nr, nc) in nbr.items():
            rk  = _road_key(r, c, nr, nc)
            ek  = ((r, c), d)
            if (nr, nc) in self.grid:
                # Internal road to neighbour
                if rk not in self.roads:
                    self.roads[rk] = Road(self.default_length_m,
                                          self.default_speed_ms,
                                          self.default_demand_cph)
                # Remove external entry if it existed
                self.entry_roads.pop(ek, None)
            else:
                # No neighbour → external entry road
                if ek not in self.entry_roads:
                    self.entry_roads[ek] = Road(self.default_length_m,
                                                self.default_speed_ms,
                                                self.default_demand_cph)

#Acessors

    def get(self, r, c):
        return self.grid.get((r, c))

    def all(self):
        return list(self.grid.values())

    def is_empty(self):
        return len(self.grid) == 0

    def get_road(self, r1, c1, r2, c2):
        return self.roads.get(_road_key(r1, c1, r2, c2))

    def get_entry_road(self, r, c, direction):
        return self.entry_roads.get(((r, c), direction))

    def _adj(self, r, c):
        return [(r-1,c),(r+1,c),(r,c-1),(r,c+1)]

#Simulation

    def _incoming(self, r, c, t, dt):
        """Cars arriving at (r,c) this tick from each direction."""
        src = {0:(r-1,c), 1:(r+1,c), 2:(r,c+1), 3:(r,c-1)}
        inc = [0.0]*4
        for d, (nr, nc) in src.items():
            if (nr, nc) in self.grid:
                road = self.roads.get(_road_key(r, c, nr, nc))
                if road:
                    # Cars arriving at (r, c) from (nr, nc) are travelling
                    # in the direction FROM (nr, nc) TO (r,c)
                    fwd = (nr, nc) < (r, c)
                    inc[d] = road.collect_arrivals(t, forward=fwd)
            else:
                road = self.entry_roads.get(((r, c), d))
                if road:
                    inc[d] = road.arrival_rate * dt
        return inc

    def _update_arrival_rates(self):
        """Sync each intersection's cached arrival_rate from its entry roads."""
        for (r, c), inter in self.grid.items():
            src = {0:(r-1,c), 1:(r+1,c), 2:(r,c+1), 3:(r,c-1)}
            for d, (nr, nc) in src.items():
                if (nr, nc) in self.grid:
                    up = self.grid.get((nr, nc))
                    if up and up.ticks > 0:
                        inter.arrival_rate[d] = up.cars_passed / up.ticks
                    else:
                        road = self.roads.get(_road_key(r, c, nr, nc))
                        inter.arrival_rate[d] = road.arrival_rate if road else 0
                else:
                    road = self.entry_roads.get(((r, c), d))
                    inter.arrival_rate[d] = road.arrival_rate if road else 0

    def tick_all(self, dt=1.0, current_time=0.0):
        # 1. Pre-compute incoming for all cells
        inc_map = {(r,c): self._incoming(r, c, current_time, dt)
                   for (r,c) in self.grid}

        # 2. Tick each intersection; release departed cars onto roads
        dn = {0:lambda r,c:(r-1,c), 1:lambda r,c:(r+1,c),
              2:lambda r,c:(r,c+1), 3:lambda r,c:(r,c-1)}

        for (r,c), inter in self.grid.items():
            departed = inter.tick(dt, inc_map[(r,c)])
            for d, cars in enumerate(departed):
                if cars > 0:
                    nr, nc = dn[d](r, c)
                    road   = self.roads.get(_road_key(r, c, nr, nc))
                    if road:
                        #Determine direction: "forward" means going from
                        # the lower-keyed cell to the higher-keyed cell
                        fwd = (r, c) < (nr, nc)
                        road.release(cars, current_time, forward=fwd)

        self._update_arrival_rates()

    def reset_all(self):
        for i in self.all():
            i.reset()
        for r in self.roads.values():
            r.reset()
        for r in self.entry_roads.values():
            r.reset()

    def apply_webster_all(self):
        self._update_arrival_rates()
        for i in self.all():
            i.apply_webster()

    def apply_uniform_all(self, green=30.0):
        for i in self.all():
            i.apply_uniform(green)

    def total_cars(self):
        return sum(i.cars_passed for i in self.all())

    def avg_queue(self):
        lst = self.all()
        return sum(i.avg_queue() for i in lst) / len(lst) if lst else 0


#Simulator

class SimResult:
    def __init__(self, name):
        self.name, self.throughput_hr = name, 0.0
        self.avg_queue = self.total_cars = 0.0
        self.history_cars = self.history_queue = []
        self.per_intersection = {}


class Simulator:
    def __init__(self, network):
        self.network = network

    def run(self, scenario="webster", duration=3600, progress_cb=None):
        (self.network.apply_webster_all() if scenario == "webster"
         else self.network.apply_uniform_all(30.0))
        self.network.reset_all()
        result       = SimResult("Webster Optimized" if scenario=="webster" else "Uniform (30s green)")
        record_every = max(1, duration//300)
        for t in range(1, duration+1):
            self.network.tick_all(1.0, float(t))
            if t % record_every == 0:
                result.history_cars.append((t, self.network.total_cars()))
                result.history_queue.append((t, self.network.avg_queue()))
            if progress_cb and t % 50 == 0:
                progress_cb(t/duration)
        result.total_cars    = self.network.total_cars()
        result.throughput_hr = result.total_cars / duration * 3600
        result.avg_queue     = self.network.avg_queue()
        for inter in self.network.all():
            result.per_intersection[(inter.row, inter.col)] = {
                "green_ns": inter.green_times[0], "green_ew": inter.green_times[1],
                "tph": inter.throughput_per_hour(duration), "queue": inter.avg_queue(),
            }
        return result

    def run_comparison(self, duration=3600, progress_cb=None):
        def cb1(p): progress_cb and progress_cb(p*.5)
        def cb2(p): progress_cb and progress_cb(.5+p*.5)
        return self.run("uniform", duration, cb1), self.run("webster", duration, cb2)


#Utilities
def _road_key(r1, c1, r2, c2):
    """Canonical sorted key for a road between two cells."""
    return (min((r1,c1),(r2,c2)), max((r1,c1),(r2,c2)))

def _poisson(lam):
    if lam <= 0: return 0
    if lam > 30: return max(0, int(random.gauss(lam, math.sqrt(lam))))
    L, k, p = math.exp(-lam), 0, 1.0
    while p > L:
        p *= random.random(); k += 1
    return k - 1

def improvement(u, w):
    tg = (w.throughput_hr-u.throughput_hr)/u.throughput_hr*100 if u.throughput_hr else 0
    qr = (u.avg_queue-w.avg_queue)/u.avg_queue*100 if u.avg_queue else 0
    return tg, qr
