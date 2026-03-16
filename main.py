import sys
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from model import Network, Simulator, improvement
from gui   import NetworkCanvas, InputPanel, ResultsWindow

BG    = "#1a1a2e"
BG2   = "#16213e"
BG3   = "#0f3460"
GOLD  = "#ffd740"
FG    = "#e0e0e0"
FG_DIM = "#aaaaaa"


class App(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("Traffic Signal Optimizer")
        self.geometry("1180x750")
        self.configure(bg=BG)
        self.minsize(900, 580)

        self.network    = Network(rows=3, cols=3)
        self.sim_time   = 0          # live preview counter
        self._live      = False      # is live animation running?

        self._build_ui()

#UI construction

    def _build_ui(self):
        self._build_toolbar()
        self._build_main_area()
        self._build_status_bar()

    def _build_toolbar(self):
        tb = tk.Frame(self, bg=BG2, pady=6)
        tb.pack(fill="x")

        def lbl(text):
            tk.Label(tb, text=text, bg=BG2, fg=FG_DIM,
                     font=("Arial", 9)).pack(side="left", padx=(8, 2))

        def sep():
            ttk.Separator(tb, orient="vertical").pack(
                side="left", fill="y", padx=8, pady=4)

        # Grid size
        lbl("Grid:")
        lbl("Rows")
        self._rows = tk.IntVar(value=3)
        tk.Spinbox(tb, from_=1, to=6, textvariable=self._rows,
                   width=3, bg=BG3, fg=FG, font=("Arial", 10),
                   command=self._resize).pack(side="left", padx=2)
        lbl("Cols")
        self._cols = tk.IntVar(value=3)
        tk.Spinbox(tb, from_=1, to=6, textvariable=self._cols,
                   width=3, bg=BG3, fg=FG, font=("Arial", 10),
                   command=self._resize).pack(side="left", padx=2)

        sep()

        # Live preview button
        self._live_btn = tk.Button(tb, text="▶ Live Preview",
                                   command=self._toggle_live,
                                   bg=BG3, fg=FG, relief="flat",
                                   padx=10, pady=5, cursor="hand2",
                                   font=("Arial", 10),
                                   activebackground="#1a5276")
        self._live_btn.pack(side="left", padx=4)

        lbl("Speed:")
        self._speed = tk.IntVar(value=15)
        tk.Scale(tb, from_=1, to=60, variable=self._speed,
                 orient="horizontal", length=80, showvalue=False,
                 bg=BG2, fg=FG, troughcolor=BG3,
                 highlightthickness=0).pack(side="left")

        sep()

        # Run comparison button
        tk.Button(tb, text="⚡ Run Comparison",
                  command=self._run_comparison,
                  bg="#1565c0", fg="white", relief="flat",
                  padx=12, pady=5, cursor="hand2",
                  font=("Arial", 10, "bold"),
                  activebackground="#1976d2"
                  ).pack(side="left", padx=6)

        lbl("Duration:")
        self._duration = tk.IntVar(value=3600)
        ttk.Combobox(tb, textvariable=self._duration,
                     values=[300, 600, 1800, 3600, 7200],
                     width=6, font=("Arial", 9)
                     ).pack(side="left", padx=2)
        lbl("sec")

        sep()

        # Network analysis button
        tk.Button(tb, text="📊 Analysis",
                  command=self._show_analysis,
                  bg=BG3, fg=FG, relief="flat",
                  padx=8, pady=5, cursor="hand2",
                  font=("Arial", 10),
                  activebackground="#1a5276"
                  ).pack(side="left", padx=4)

        tk.Button(tb, text="↺ Reset",
                  command=self._reset,
                  bg=BG3, fg=FG, relief="flat",
                  padx=8, pady=5, cursor="hand2",
                  font=("Arial", 10),
                  activebackground="#1a5276"
                  ).pack(side="left", padx=4)

        # Live timer (right side)
        self._time_lbl = tk.Label(tb, text="t = 0 s",
                                  bg=BG2, fg=GOLD,
                                  font=("Courier", 10, "bold"))
        self._time_lbl.pack(side="right", padx=14)

    def _build_main_area(self):
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=6, pady=4)

        # Canvas (left)
        canvas_wrap = tk.Frame(main, bg=BG3, bd=1, relief="flat")
        canvas_wrap.pack(side="left", fill="both", expand=True, padx=(0, 4))

        self.canvas = NetworkCanvas(
            canvas_wrap, self.network,
            on_select=self._select_intersection
        )
        self.canvas.pack(fill="both", expand=True, padx=2, pady=2)

        # Input panel (right)
        right = tk.Frame(main, bg=BG2, width=240)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        self.panel = InputPanel(right, on_change=lambda: self.canvas.draw())
        self.panel.network = self.network
        self.panel.pack(fill="both", expand=True)

    def _build_status_bar(self):
        self._status = tk.StringVar(value="Ready — click an intersection to edit it.")
        self._progress = tk.DoubleVar(value=0)

        self._pbar = ttk.Progressbar(self, variable=self._progress, maximum=1.0)

        tk.Label(self, textvariable=self._status,
                 bg=BG3, fg=FG_DIM, font=("Arial", 9),
                 anchor="w", pady=3
                 ).pack(fill="x", side="bottom", padx=6, pady=(0, 4))

    #Event handlers

    def _select_intersection(self, r, c):
        inter = self.network.get(r, c)
        if inter:
            self.panel.load(inter)
            self._set_status(f"Editing intersection ({r}, {c})")

    def _resize(self):
        r, c = self._rows.get(), self._cols.get()
        self.network.resize(r, c)
        self.panel.network = self.network
        self.panel.clear()
        self.canvas.draw()
        self._set_status(f"Grid resized to {r} × {c}")

    def _toggle_live(self):
        if self._live:
            self._live = False
            self._live_btn.config(text="▶ Live Preview")
        else:
            self._live = True
            self._live_btn.config(text="⏹ Stop")
            self.network.apply_webster_all()
            self.network.reset_all()
            self.sim_time = 0
            threading.Thread(target=self._live_loop, daemon=True).start()

    def _live_loop(self):
        while self._live:
            self.network.tick_all(1.0)
            self.sim_time += 1
            self.after(0, self._live_frame)
            time.sleep(1.0 / max(self._speed.get(), 1))

    def _live_frame(self):
        self.canvas.draw()
        self._time_lbl.config(text=f"t = {self.sim_time} s")

    def _run_comparison(self):
        if self._live:
            self._toggle_live()
        duration = int(self._duration.get())
        self._set_status(f"Running simulation ({duration}s) …")
        self._pbar.pack(fill="x", padx=6, pady=2, before=self.winfo_children()[-1])

        def worker():
            sim = Simulator(self.network)
            u, w = sim.run_comparison(
                duration=duration,
                progress_cb=lambda p: self.after(0, lambda: self._progress.set(p))
            )
            self.after(0, lambda: self._done(u, w))

        threading.Thread(target=worker, daemon=True).start()

    def _done(self, u, w):
        self._pbar.pack_forget()
        tg, qr = improvement(u, w)
        self._set_status(
            f"Done — Webster gives {tg:+.1f}% throughput, {qr:+.1f}% queue change")
        ResultsWindow(self, u, w)

    def _show_analysis(self):
        lines = ["Webster Analysis per Intersection\n" + "="*50]
        for inter in self.network.all():
            C, g1, g2 = inter.compute_webster()
            y1, y2    = inter.flow_ratios()
            sat = " ⚠ OVERSATURATED" if (y1+y2) >= 0.95 else ""
            lines.append(
                f"({inter.row},{inter.col})  "
                f"C={C:.1f}s  NS={g1:.1f}s  EW={g2:.1f}s  "
                f"y_NS={y1:.3f}  y_EW={y2:.3f}{sat}"
            )
        win = tk.Toplevel(self)
        win.title("Network Analysis")
        win.configure(bg=BG)
        win.geometry("580x380")
        box = tk.Text(win, bg="#0a1628", fg="#00e676",
                      font=("Courier", 10), relief="flat")
        box.pack(fill="both", expand=True, padx=10, pady=10)
        box.insert("1.0", "\n".join(lines))
        box.config(state="disabled")

    def _reset(self):
        if self._live:
            self._toggle_live()
        self.network.reset_all()
        self.sim_time = 0
        self._time_lbl.config(text="t = 0 s")
        self.canvas.draw()
        self._set_status("Statistics reset.")

    def _set_status(self, msg):
        self._status.set(msg)


if __name__ == "__main__":
    App().mainloop()
