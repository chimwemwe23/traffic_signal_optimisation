
import tkinter as tk
from tkinter import ttk

try:
    import matplotlib
    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

from model import Intersection, Network, improvement

# Palette
BG       = "#1a1a2e"
BG2      = "#16213e"
BG3      = "#0f3460"
GREEN    = "#00e676"
RED      = "#ff1744"
YELLOW   = "#a89d23"
BLUE     = "#29b6f6"
GOLD     = "#ffd740"
FG       = "#e0e0e0"
FG_DIM   = "#aaaaaa"


#Network Canvas

class NetworkCanvas(tk.Canvas):
    """Draws the road grid. Click an intersection to select it."""

    R_INTER = 18   # intersection circle radius
    R_LIGHT = 6    # traffic light dot radius

    def __init__(self, parent, network: Network, on_select=None, **kw):
        super().__init__(parent, bg=BG, highlightthickness=0, **kw)
        self.network   = network
        self.on_select = on_select
        self.selected  = None
        self.margin    = 55
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Button-1>",  self._click)

    #Layout helpers

    def _cell(self):
        w, h = self.winfo_width(), self.winfo_height()
        cw = (w - 2 * self.margin) / max(self.network.cols, 1)
        ch = (h - 2 * self.margin) / max(self.network.rows, 1)
        return cw, ch

    def _pos(self, r, c):
        cw, ch = self._cell()
        x = self.margin + c * cw + cw / 2
        y = self.margin + r * ch + ch / 2
        return x, y

    #Events

    def _click(self, event):
        best, best_d = None, 9999
        for r in range(self.network.rows):
            for c in range(self.network.cols):
                ix, iy = self._pos(r, c)
                d = ((event.x - ix)**2 + (event.y - iy)**2)**0.5
                if d < best_d:
                    best_d, best = d, (r, c)
        if best_d < self.R_INTER * 3:
            self.selected = best
            self.draw()
            if self.on_select:
                self.on_select(*best)

    #Drawing

    def draw(self):
        self.delete("all")
        if self.winfo_width() < 10:
            return
        self._draw_roads()
        self._draw_intersections()
        self._draw_axis_labels()

    def _draw_roads(self):
        cw, ch = self._cell()
        rw = max(4, int(min(cw, ch) * 0.07))
        for r in range(self.network.rows):
            for c in range(self.network.cols):
                ix, iy = self._pos(r, c)
                if c < self.network.cols - 1:
                    nx, _ = self._pos(r, c + 1)
                    self.create_line(ix, iy, nx, iy, fill="#555", width=rw)
                if r < self.network.rows - 1:
                    _, ny = self._pos(r + 1, c)
                    self.create_line(ix, iy, ix, ny, fill="#555", width=rw)

    def _draw_intersections(self):
        ri, rl = self.R_INTER, self.R_LIGHT
        for r in range(self.network.rows):
            for c in range(self.network.cols):
                inter = self.network.get(r, c)
                ix, iy = self._pos(r, c)

                # selection ring
                if self.selected == (r, c):
                    self.create_oval(ix-ri-6, iy-ri-6, ix+ri+6, iy+ri+6,
                                     fill="", outline=GOLD, width=3)

                # intersection circle
                self.create_oval(ix-ri, iy-ri, ix+ri, iy+ri,
                                 fill=FG, outline="#888", width=1)

                # traffic light dots: N S E W
                for d, (lx, ly) in enumerate([
                    (ix,        iy-ri-rl-3),   # N
                    (ix,        iy+ri+rl+3),   # S
                    (ix+ri+rl+3, iy         ),  # E
                    (ix-ri-rl-3, iy         ),  # W
                ]):
                    if inter.is_yellow(d):
                        col = YELLOW
                    elif inter.is_green(d):
                        col = GREEN
                    else:
                        col = RED
                    self.create_oval(lx-rl, ly-rl, lx+rl, ly+rl,
                                     fill=col, outline="")

                # queue bars (small cyan lines showing queue length)
                self._draw_queue(inter, ix, iy, ri)

                # label
                self.create_text(ix, iy, text=f"{r},{c}",
                                 fill="#333", font=("Arial", 7, "bold"))

    def _draw_queue(self, inter, ix, iy, ri):
        max_q   = 20.0
        bar_len = ri * 1.4
        # (direction, start_x, start_y, dx, dy)
        cfg = [
            (0, ix - ri - 10, iy - ri,      0,       -bar_len),
            (1, ix + ri + 6,  iy + ri,      0,        bar_len),
            (2, ix + ri,      iy - ri - 10, bar_len,  0      ),
            (3, ix - ri,      iy + ri + 6, -bar_len,  0      ),
        ]
        for d, bx, by, dx, dy in cfg:
            frac = min(inter.queue[d], max_q) / max_q
            if frac > 0.01:
                self.create_line(bx, by,
                                 bx + dx * frac,
                                 by + dy * frac,
                                 fill=BLUE, width=4, capstyle=tk.ROUND)

    def _draw_axis_labels(self):
        for c in range(self.network.cols):
            ix, _ = self._pos(0, c)
            self.create_text(ix, self.margin - 20,
                             text=f"Col {c}", fill=FG_DIM, font=("Arial", 9))
        for r in range(self.network.rows):
            _, iy = self._pos(r, 0)
            self.create_text(self.margin - 22, iy,
                             text=f"Row {r}", fill=FG_DIM, font=("Arial", 9))


#Input Panel
class InputPanel(tk.Frame):
    """Edit arrival rates and lane counts for the selected intersection."""

    def __init__(self, parent, on_change=None, **kw):
        super().__init__(parent, bg=BG2, **kw)
        self.on_change = on_change
        self.inter: Intersection = None
        self.network: Network    = None
        self._rate_vars = []
        self._lane_vars = []
        self.DIR_NAMES  = ["North", "South", "East", "West"]
        self._build()

    def _lbl(self, parent, text, size=10, bold=False, color=FG):
        font = ("Arial", size, "bold") if bold else ("Arial", size)
        return tk.Label(parent, text=text, bg=BG2, fg=color, font=font)

    def _build(self):
        self._lbl(self, "Intersection Editor", 12, bold=True, color=GOLD).pack(pady=(12, 4))
        self._id_lbl = self._lbl(self, "Click an intersection", color=FG_DIM)
        self._id_lbl.pack()
        ttk.Separator(self).pack(fill="x", padx=8, pady=6)

        # Arrival rates
        self._lbl(self, "Arrival Rates (cars/sec)", bold=True, color=BLUE).pack(anchor="w", padx=10)
        for name in self.DIR_NAMES:
            row = tk.Frame(self, bg=BG2)
            row.pack(fill="x", padx=14, pady=2)
            self._lbl(row, f"{name}:", 10).pack(side="left", padx=(0, 6))
            var = tk.DoubleVar(value=0.3)
            self._rate_vars.append(var)
            e = tk.Entry(row, textvariable=var, width=6,
                         bg=BG3, fg=FG, insertbackground="white", font=("Arial", 10))
            e.pack(side="left")
            e.bind("<FocusOut>", self._changed)
            e.bind("<Return>",   self._changed)
            self._lbl(row, " cars/s", color=FG_DIM).pack(side="left")

        ttk.Separator(self).pack(fill="x", padx=8, pady=6)

        # Lanes
        self._lbl(self, "Lanes per Direction", bold=True, color=BLUE).pack(anchor="w", padx=10)
        for name in self.DIR_NAMES:
            row = tk.Frame(self, bg=BG2)
            row.pack(fill="x", padx=14, pady=2)
            self._lbl(row, f"{name}:", 10).pack(side="left", padx=(0, 6))
            var = tk.IntVar(value=1)
            self._lane_vars.append(var)
            tk.Spinbox(row, from_=1, to=4, textvariable=var, width=3,
                       bg=BG3, fg=FG, buttonbackground=BG3,
                       font=("Arial", 10), command=self._changed).pack(side="left")

        ttk.Separator(self).pack(fill="x", padx=8, pady=6)

        # Webster preview
        self._lbl(self, "Webster Preview", bold=True, color=BLUE).pack(anchor="w", padx=10)
        self._preview = tk.Text(self, height=6, width=26,
                                bg="#0a1628", fg=GREEN,
                                font=("Courier", 9), state="disabled", relief="flat")
        self._preview.pack(padx=10, pady=4, fill="x")

        ttk.Separator(self).pack(fill="x", padx=8, pady=6)

        # Presets
        self._lbl(self, "Quick Presets", bold=True, color=BLUE).pack(anchor="w", padx=10)
        pf = tk.Frame(self, bg=BG2)
        pf.pack(fill="x", padx=10, pady=4)
        presets = [
            ("Light",  [0.15]*4),
            ("Medium", [0.30]*4),
            ("Heavy",  [0.50]*4),
            ("Asym",   [0.50, 0.50, 0.15, 0.15]),
        ]
        for i, (name, rates) in enumerate(presets):
            tk.Button(pf, text=name,
                      command=lambda r=rates: self._preset(r),
                      bg=BG3, fg=FG, relief="flat",
                      activebackground="#1a5276", padx=6, pady=3
                      ).grid(row=i//2, column=i%2, padx=3, pady=3, sticky="ew")
        pf.columnconfigure(0, weight=1)
        pf.columnconfigure(1, weight=1)

        # Apply to all
        ttk.Separator(self).pack(fill="x", padx=8, pady=6)
        tk.Button(self, text="Apply to ALL Intersections",
                  command=self._apply_all,
                  bg="#1565c0", fg="white", relief="flat",
                  font=("Arial", 10, "bold"), pady=6,
                  activebackground="#1976d2"
                  ).pack(fill="x", padx=10, pady=4)

    def load(self, inter: Intersection):
        self.inter = inter
        self._id_lbl.config(text=f"Editing: ({inter.row}, {inter.col})")
        for i, v in enumerate(self._rate_vars):
            v.set(round(inter.arrival_rate[i], 3))
        for i, v in enumerate(self._lane_vars):
            v.set(inter.lanes[i])
        self._update_preview()

    def _changed(self, _=None):
        if not self.inter:
            return
        try:
            for i, v in enumerate(self._rate_vars):
                self.inter.arrival_rate[i] = max(0.0, min(float(v.get()), 2.0))
            for i, v in enumerate(self._lane_vars):
                self.inter.lanes[i] = max(1, min(int(v.get()), 4))
        except (ValueError, tk.TclError):
            return
        self._update_preview()
        if self.on_change:
            self.on_change()

    def _preset(self, rates):
        if not self.inter:
            return
        for i, v in enumerate(self._rate_vars):
            v.set(rates[i])
        self._changed()

    def _apply_all(self):
        if not self.inter or not self.network:
            return
        for inter in self.network.all():
            inter.arrival_rate = self.inter.arrival_rate.copy()
            inter.lanes        = self.inter.lanes.copy()
        if self.on_change:
            self.on_change()

    def _update_preview(self):
        if not self.inter:
            return
        C, g1, g2 = self.inter.compute_webster()
        y1, y2    = self.inter.flow_ratios()
        saturated = (y1 + y2) >= 0.95
        txt = (f"Cycle   : {C:.1f} s\n"
               f"NS green: {g1:.1f} s\n"
               f"EW green: {g2:.1f} s\n"
               f"y_NS    : {y1:.3f}\n"
               f"y_EW    : {y2:.3f}\n"
               f"Status  : {'⚠ OVER-SAT' if saturated else 'OK'}")
        self._preview.config(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.insert("1.0", txt)
        self._preview.config(state="disabled")

    def clear(self):
        self.inter = None
        self._id_lbl.config(text="Click an intersection")
        self._preview.config(state="normal")
        self._preview.delete("1.0", "end")
        self._preview.config(state="disabled")


#Results Window

class ResultsWindow(tk.Toplevel):
    """Popup showing comparison charts and stats table."""

    def __init__(self, parent, uniform, webster):
        super().__init__(parent)
        self.title("Results — Uniform vs Webster")
        self.configure(bg=BG)
        self.geometry("860x640")
        self.u, self.w = uniform, webster
        self._build()

    def _build(self):
        #header bar
        tk.Label(self, text="Simulation Comparison Results",
                 bg=BG, fg=GOLD, font=("Arial", 14, "bold")).pack(pady=(12, 4))

        tg, qr = improvement(self.u, self.w)

        stats_bar = tk.Frame(self, bg=BG3, pady=8)
        stats_bar.pack(fill="x", padx=12, pady=6)
        for label, value, color in [
            ("Uniform Throughput",  f"{self.u.throughput_hr:.0f} cars/hr", FG),
            ("Webster Throughput",  f"{self.w.throughput_hr:.0f} cars/hr", FG),
            ("Throughput Gain",     f"{tg:+.1f}%",  GREEN if tg >= 0 else RED),
            ("Queue Reduction",     f"{qr:+.1f}%",  GREEN if qr >= 0 else RED),
        ]:
            col = tk.Frame(stats_bar, bg=BG3)
            col.pack(side="left", expand=True)
            tk.Label(col, text=label,  bg=BG3, fg=FG_DIM, font=("Arial", 9)).pack()
            tk.Label(col, text=value,  bg=BG3, fg=color,  font=("Arial", 13, "bold")).pack()

        #tabs
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=12, pady=6)

        # Tab 1: throughput chart
        t1 = tk.Frame(nb, bg=BG); nb.add(t1, text="Throughput")
        if HAS_MPL:
            self._chart(t1,
                        self.u.history_cars, self.w.history_cars,
                        "Cumulative Cars Passed", "Cars")
        else:
            tk.Label(t1, text="pip install matplotlib for charts",
                     bg=BG, fg=RED, font=("Arial", 12)).pack(expand=True)

        # Tab 2: queue chart
        t2 = tk.Frame(nb, bg=BG); nb.add(t2, text="Queue Length")
        if HAS_MPL:
            self._chart(t2,
                        self.u.history_queue, self.w.history_queue,
                        "Avg Queue Length per Intersection", "Cars waiting")

        # Tab 3: per-intersection table
        t3 = tk.Frame(nb, bg=BG); nb.add(t3, text="Per Intersection")
        self._table(t3)

        # Tab 4: text summary
        t4 = tk.Frame(nb, bg=BG); nb.add(t4, text="Summary Text")
        self._text_summary(t4)

    def _chart(self, parent, u_data, w_data, title, ylabel):
        fig = Figure(figsize=(7.5, 3.4), dpi=96, facecolor=BG)
        ax  = fig.add_subplot(111)
        ax.set_facecolor(BG3)

        if u_data:
            ts = [t / 3600 for t, _ in u_data]
            ax.plot(ts, [v for _, v in u_data], color="#ff6b6b",
                    lw=2, label="Uniform (30s)")
        if w_data:
            ts = [t / 3600 for t, _ in w_data]
            ax.plot(ts, [v for _, v in w_data], color=GREEN,
                    lw=2, label="Webster")

        ax.set_xlabel("Time (hours)", color=FG_DIM)
        ax.set_ylabel(ylabel, color=FG_DIM)
        ax.set_title(title, color=GOLD)
        ax.tick_params(colors=FG_DIM)
        for spine in ax.spines.values():
            spine.set_color("#555")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(facecolor=BG2, labelcolor=FG)
        ax.grid(True, alpha=0.15, color="#555")
        fig.tight_layout(pad=1.5)

        FigureCanvasTkAgg(fig, master=parent).get_tk_widget().pack(
            fill="both", expand=True, padx=4, pady=4)

    def _table(self, parent):
        headers = ["Intersection", "NS Green", "EW Green",
                   "Throughput\nUniform", "Throughput\nWebster", "Gain"]
        hf = tk.Frame(parent, bg=BG3)
        hf.pack(fill="x", padx=6, pady=(6, 0))
        for i, h in enumerate(headers):
            tk.Label(hf, text=h, bg=BG3, fg=GOLD,
                     font=("Arial", 9, "bold"), width=13,
                     wraplength=90, anchor="center").grid(row=0, column=i, padx=2, pady=4)

        # Scrollable rows
        outer = tk.Frame(parent, bg=BG)
        outer.pack(fill="both", expand=True, padx=6, pady=4)
        cv   = tk.Canvas(outer, bg=BG, highlightthickness=0)
        sb   = ttk.Scrollbar(outer, orient="vertical", command=cv.yview)
        body = tk.Frame(cv, bg=BG)
        body.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.create_window((0, 0), window=body, anchor="nw")
        cv.configure(yscrollcommand=sb.set)
        cv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        for row_i, key in enumerate(sorted(self.w.per_intersection)):
            wi = self.w.per_intersection[key]
            ui = self.u.per_intersection.get(key, {})
            gain = ((wi["tph"] - ui.get("tph", 0)) / ui["tph"] * 100
                    if ui.get("tph") else 0)
            bg_row = "#1e2d4a" if row_i % 2 == 0 else BG2
            vals = [
                f"({key[0]},{key[1]})",
                f"{wi['green_ns']:.1f}s",
                f"{wi['green_ew']:.1f}s",
                f"{ui.get('tph', 0):.0f}",
                f"{wi['tph']:.0f}",
                f"{gain:+.1f}%",
            ]
            for ci, val in enumerate(vals):
                color = (GREEN if gain >= 0 else RED) if ci == 5 else FG
                tk.Label(body, text=val, bg=bg_row, fg=color,
                         font=("Arial", 9), width=13, anchor="center"
                         ).grid(row=row_i, column=ci, padx=2, pady=2, sticky="ew")

    def _text_summary(self, parent):
        tg, qr = improvement(self.u, self.w)
        txt = (
            "=" * 44 + "\n"
            "    TRAFFIC SIGNAL OPTIMIZATION RESULTS\n"
            "=" * 44 + "\n\n"
            f"UNIFORM (30s green each direction)\n"
            f"  Throughput : {self.u.throughput_hr:.0f} cars/hr\n"
            f"  Avg queue  : {self.u.avg_queue:.2f} cars/intersection\n\n"
            f"WEBSTER OPTIMIZED\n"
            f"  Throughput : {self.w.throughput_hr:.0f} cars/hr\n"
            f"  Avg queue  : {self.w.avg_queue:.2f} cars/intersection\n\n"
            f"IMPROVEMENT\n"
            f"  Throughput gain  : {tg:+.1f}%\n"
            f"  Queue reduction  : {qr:+.1f}%\n\n"
            "Webster allocates green time proportionally\n"
            "to each direction's traffic demand, reducing\n"
            "unnecessary waiting on low-traffic approaches.\n"
            "=" * 44
        )
        box = tk.Text(parent, bg="#0a1628", fg=GREEN,
                      font=("Courier", 10), wrap="word", relief="flat")
        box.pack(fill="both", expand=True, padx=10, pady=10)
        box.insert("1.0", txt)
        box.config(state="disabled")
