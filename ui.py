"""
ui.py
=====
Tkinter interface for the Autonomous Mars Rover.

Layout::

    ┌───────────────────────────────────────────────────────────────┐
    │  header                                                       │
    ├──────────────────────────┬────────────────────────────────────┤
    │  Mars grid               │  Rover status & metrics            │
    │  (KB view / ground truth)│  Knowledge base: TELL / ASK / INFER│
    │                          │  Why did the rover act?            │
    ├──────────────────────────┴────────────────────────────────────┤
    │  live reasoning log (mirror of the terminal console)          │
    ├───────────────────────────────────────────────────────────────┤
    │  START | STEP | PAUSE | RESET | view toggle | speed           │
    └───────────────────────────────────────────────────────────────┘

Two design points worth noting
------------------------------
**Grid view.**  By default the grid shows what the rover *believes*, read
straight out of the knowledge base — unperceived cells are blank, and a
cell only turns red once ``Hazard_x_y`` is entailed.  The "Ground Truth"
toggle reveals the real map for comparison.  Watching the belief view fill
in as the rover explores is the clearest evidence that it is not reading
the map.

**Threading.**  Auto-run is driven by ``after()`` on the Tk event loop, not
a worker thread.  Tkinter is not thread-safe, and stepping the agent from a
background thread while its callbacks touch widgets is a real source of
hangs; keeping everything on the main loop removes the problem entirely.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from typing import Dict, List, Optional, Tuple

import console
from environment import CellType
from knowledge_base import KnowledgeBase
from logic import Literal
from metrics import Metrics
from rover import DecisionRecord, RoverAgent
from simulation import SimState, Simulation

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------

COLORS = {
    "bg_main":        "#150a04",
    "bg_panel":       "#241208",
    "bg_panel2":      "#1b0d05",
    "bg_header":      "#3a1c08",
    "bg_log":         "#0d0603",

    "cell_unperceived": "#241a14",
    "cell_unknown":     "#4a4438",
    "cell_safe":        "#16351b",
    "cell_visited":     "#123434",
    "cell_hazard":      "#6e0f0f",
    "cell_radiation":   "#7a4a00",
    "cell_goal":        "#5a4d00",
    "cell_rover":       "#0b3f6b",

    "text_primary":   "#ff9a40",
    "text_secondary": "#cc7a35",
    "text_dim":       "#8a5a2c",
    "text_white":     "#f0e6dc",
    "text_safe":      "#5ce65c",
    "text_hazard":    "#ff6b6b",
    "text_radiation": "#ffab3d",
    "text_unknown":   "#c9bfae",
    "text_visited":   "#5cd0d0",
    "text_goal":      "#ffe14d",
    "text_rover":     "#5cb3ff",

    "grid_line":      "#4a2a10",
    "border_rover":   "#33bbff",
    "border_goal":    "#ffd633",

    "btn_start":      "#0f4d16", "btn_start_fg": "#5cff7a",
    "btn_step":       "#0d2c52", "btn_step_fg":  "#5cb3ff",
    "btn_pause":      "#4d3d05", "btn_pause_fg": "#ffcc33",
    "btn_reset":      "#4d0d0d", "btn_reset_fg": "#ff6b6b",

    "tag_tell":     "#5cff9e",
    "tag_ask":      "#8fc9ff",
    "tag_result":   "#ffe14d",
    "tag_infer":    "#e88fff",
    "tag_rule":     "#9cff9c",
    "tag_decision": "#ffb066",
    "tag_perceive": "#7fd8ff",
    "tag_retract":  "#ff9c9c",
    "tag_step":     "#ff9a40",
}

CELL_SIZE = 74
CELL_PAD = 2
MAX_LOG_LINES = 900        # trim the in-app log so it cannot grow unbounded


class MarsRoverUI(tk.Tk):
    """Main application window."""

    def __init__(self, simulation: Simulation):
        super().__init__()

        self.simulation = simulation
        self.env = simulation.environment
        self.kb: KnowledgeBase = simulation.kb
        self.rover: RoverAgent = simulation.rover

        self.simulation.on_step_complete = self._on_step_complete
        self.simulation.on_state_change = self._on_state_change
        self.simulation.on_mission_complete = self._on_mission_complete

        self._auto_job: Optional[str] = None      # pending after() id
        self._show_truth = tk.BooleanVar(value=False)
        self._log_lines = 0

        self.title("Autonomous Mars Rover — Propositional Logic "
                   "Knowledge-Based Agent")
        self.configure(bg=COLORS["bg_main"])
        self.minsize(1180, 760)

        self._setup_fonts()
        self._build_ui()

        self._cell_items: Dict[Tuple[int, int], List[int]] = {}

        self._draw_grid()
        self._update_info_panel()
        self._show_initial_kb_panel()

        # Mirror the terminal reasoning log into the window, so one screen
        # recording captures the grid and the live console together.
        console.add_listener(self._on_log_line)

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # Fonts
    # ------------------------------------------------------------------

    def _setup_fonts(self) -> None:
        self.font_header   = tkfont.Font(family="Segoe UI", size=13,
                                         weight="bold")
        self.font_sub      = tkfont.Font(family="Segoe UI", size=8)
        self.font_section  = tkfont.Font(family="Segoe UI", size=9,
                                         weight="bold")
        self.font_small    = tkfont.Font(family="Segoe UI", size=8)
        self.font_btn      = tkfont.Font(family="Segoe UI", size=9,
                                         weight="bold")
        self.font_mono     = tkfont.Font(family="Consolas", size=8)
        self.font_mono_sm  = tkfont.Font(family="Consolas", size=7)
        self.font_cell     = tkfont.Font(family="Consolas", size=7)
        self.font_cell_big = tkfont.Font(family="Segoe UI", size=9,
                                         weight="bold")

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        self._build_header()

        content = tk.Frame(self, bg=COLORS["bg_main"])
        content.pack(fill="both", expand=True, padx=6, pady=(4, 0))

        left = tk.Frame(content, bg=COLORS["bg_main"])
        left.pack(side="left", fill="y")
        self._build_grid_panel(left)

        right = tk.Frame(content, bg=COLORS["bg_main"])
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))
        self._build_info_panel(right)
        self._build_kb_panel(right)
        self._build_explain_panel(right)

        self._build_log_panel()
        self._build_controls()

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=COLORS["bg_header"], pady=5)
        header.pack(fill="x")
        tk.Label(header,
                 text="AUTONOMOUS MARS ROVER  —  PROPOSITIONAL LOGIC "
                      "KNOWLEDGE-BASED AGENT",
                 font=self.font_header, fg=COLORS["text_primary"],
                 bg=COLORS["bg_header"]).pack()
        tk.Label(header,
                 text="Unit 3: Logical Agents   |   PERCEIVE → TELL(KB) → "
                      "INFER → ASK(KB) → DECIDE → ACT → SUCCESSOR STATE",
                 font=self.font_sub, fg=COLORS["text_secondary"],
                 bg=COLORS["bg_header"]).pack()

    def _build_grid_panel(self, parent) -> None:
        self.grid_frame = tk.LabelFrame(
            parent, text=" MARS GRID — ROVER'S KNOWLEDGE ",
            font=self.font_section, fg=COLORS["text_primary"],
            bg=COLORS["bg_panel"], bd=1, relief="ridge")
        self.grid_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            self.grid_frame,
            width=self.env.width * CELL_SIZE + 2,
            height=self.env.height * CELL_SIZE + 2,
            bg=COLORS["bg_main"], highlightthickness=0)
        self.canvas.pack(padx=5, pady=5)

        self._build_legend(self.grid_frame)

    def _build_legend(self, parent) -> None:
        legend = tk.Frame(parent, bg=COLORS["bg_panel"])
        legend.pack(fill="x", padx=5, pady=(0, 5))

        entries = [
            ("ROVER", "cell_rover"), ("SAFE", "cell_safe"),
            ("VISITED", "cell_visited"), ("UNKNOWN", "cell_unknown"),
            ("HAZARD", "cell_hazard"), ("RADIATION", "cell_radiation"),
            ("GOAL", "cell_goal"), ("UNPERCEIVED", "cell_unperceived"),
        ]
        for index, (label, color_key) in enumerate(entries):
            row, column = divmod(index, 4)
            cell = tk.Frame(legend, bg=COLORS["bg_panel"])
            cell.grid(row=row, column=column, sticky="w", padx=3, pady=1)
            tk.Canvas(cell, width=11, height=11, bg=COLORS[color_key],
                      highlightthickness=1,
                      highlightbackground=COLORS["grid_line"]
                      ).pack(side="left", padx=(0, 3))
            tk.Label(cell, text=label, font=self.font_small,
                     fg=COLORS["text_dim"], bg=COLORS["bg_panel"]
                     ).pack(side="left")

    def _build_info_panel(self, parent) -> None:
        frame = tk.LabelFrame(
            parent, text=" ROVER STATUS & PERFORMANCE METRICS ",
            font=self.font_section, fg=COLORS["text_primary"],
            bg=COLORS["bg_panel"], bd=1, relief="ridge")
        frame.pack(fill="x", pady=(0, 4))

        # Two columns of fields.
        left = tk.Frame(frame, bg=COLORS["bg_panel"])
        left.pack(side="left", fill="both", expand=True, padx=4, pady=3)
        right = tk.Frame(frame, bg=COLORS["bg_panel"])
        right.pack(side="left", fill="both", expand=True, padx=4, pady=3)

        left_fields = [
            ("Position", "text_rover"), ("Goal", "text_goal"),
            ("Status", "text_primary"), ("Perception", "text_secondary"),
            ("Decision", "text_safe"), ("Inference", "tag_infer"),
            ("Entailment", "tag_result"),
        ]
        right_fields = [
            ("KB Facts", "text_primary"), ("KB Rules", "text_primary"),
            ("KB Clauses", "text_secondary"), ("Moves", "text_white"),
            ("Path Cost", "text_white"), ("Investigations", "text_unknown"),
            ("Inferences", "text_white"), ("Resolutions", "text_white"),
            ("Model Checks", "text_white"), ("Rejected", "text_hazard"),
            ("Elapsed", "text_white"),
        ]

        self._info_vars: Dict[str, tk.StringVar] = {}
        for container, fields, width in ((left, left_fields, 11),
                                         (right, right_fields, 13)):
            for label, color_key in fields:
                row = tk.Frame(container, bg=COLORS["bg_panel"])
                row.pack(fill="x")
                tk.Label(row, text=f"{label}:", width=width, anchor="w",
                         font=self.font_small, fg=COLORS["text_dim"],
                         bg=COLORS["bg_panel"]).pack(side="left")
                var = tk.StringVar(value="—")
                tk.Label(row, textvariable=var, anchor="w",
                         font=self.font_mono, fg=COLORS[color_key],
                         bg=COLORS["bg_panel"]).pack(side="left", fill="x")
                self._info_vars[label] = var

    def _build_kb_panel(self, parent) -> None:
        frame = tk.LabelFrame(
            parent, text=" KNOWLEDGE BASE  —  TELL / ASK / INFER ",
            font=self.font_section, fg=COLORS["text_primary"],
            bg=COLORS["bg_panel2"], bd=1, relief="ridge")
        frame.pack(fill="both", expand=True, pady=(0, 4))

        self.kb_text = self._make_text(frame, height=13)

    def _build_explain_panel(self, parent) -> None:
        frame = tk.LabelFrame(
            parent, text=" WHY DID THE ROVER ACT THIS WAY? ",
            font=self.font_section, fg=COLORS["text_primary"],
            bg=COLORS["bg_panel"], bd=1, relief="ridge")
        frame.pack(fill="both", expand=True)

        self.explain_text = self._make_text(frame, height=11)

    def _build_log_panel(self) -> None:
        frame = tk.LabelFrame(
            self, text=" LIVE REASONING LOG  (mirrors the terminal console) ",
            font=self.font_section, fg=COLORS["text_primary"],
            bg=COLORS["bg_panel2"], bd=1, relief="ridge")
        frame.pack(fill="both", expand=True, padx=6, pady=4)

        self.log_text = self._make_text(frame, height=11, small=True)

    def _make_text(self, parent, height: int, small: bool = False) -> tk.Text:
        """Create a read-only, scrollable, tag-coloured text widget."""
        wrapper = tk.Frame(parent, bg=parent["bg"])
        wrapper.pack(fill="both", expand=True)

        scrollbar = tk.Scrollbar(wrapper, bg=COLORS["bg_panel"],
                                 troughcolor=COLORS["bg_panel2"], bd=0,
                                 highlightthickness=0)
        scrollbar.pack(side="right", fill="y")

        widget = tk.Text(
            wrapper, height=height,
            font=self.font_mono_sm if small else self.font_mono,
            bg=COLORS["bg_log"], fg=COLORS["text_white"],
            state="disabled", wrap="none", bd=0, padx=5, pady=4,
            yscrollcommand=scrollbar.set,
            selectbackground="#3a1a06", insertbackground=COLORS["text_primary"])
        widget.pack(side="left", fill="both", expand=True)
        scrollbar.configure(command=widget.yview)

        for tag in ("tell", "ask", "result", "infer", "rule", "decision",
                    "perceive", "retract", "step"):
            widget.tag_configure(tag, foreground=COLORS[f"tag_{tag}"])
        widget.tag_configure("dim", foreground=COLORS["text_dim"])
        widget.tag_configure("accepted", foreground=COLORS["tag_tell"])
        widget.tag_configure("rejected", foreground=COLORS["text_hazard"])
        widget.tag_configure("header", foreground=COLORS["text_primary"])
        return widget

    def _build_controls(self) -> None:
        bar = tk.Frame(self, bg=COLORS["bg_header"], pady=4)
        bar.pack(fill="x")

        style = dict(font=self.font_btn, bd=0, padx=11, pady=5,
                     cursor="hand2", relief="flat")

        self.btn_start = tk.Button(
            bar, text="START AUTONOMOUS MISSION", command=self._cmd_start,
            bg=COLORS["btn_start"], fg=COLORS["btn_start_fg"],
            activebackground="#1a6b23", activeforeground="#ffffff", **style)
        self.btn_start.pack(side="left", padx=4)

        self.btn_step = tk.Button(
            bar, text="STEP", command=self._cmd_step,
            bg=COLORS["btn_step"], fg=COLORS["btn_step_fg"],
            activebackground="#154a85", activeforeground="#ffffff", **style)
        self.btn_step.pack(side="left", padx=4)

        self.btn_pause = tk.Button(
            bar, text="PAUSE", command=self._cmd_pause, state="disabled",
            bg=COLORS["btn_pause"], fg=COLORS["btn_pause_fg"],
            activebackground="#7a6208", activeforeground="#ffffff", **style)
        self.btn_pause.pack(side="left", padx=4)

        self.btn_reset = tk.Button(
            bar, text="RESET", command=self._cmd_reset,
            bg=COLORS["btn_reset"], fg=COLORS["btn_reset_fg"],
            activebackground="#7a1414", activeforeground="#ffffff", **style)
        self.btn_reset.pack(side="left", padx=4)

        self.btn_metrics = tk.Button(
            bar, text="METRICS", command=self._cmd_metrics,
            bg=COLORS["btn_step"], fg=COLORS["btn_step_fg"],
            activebackground="#154a85", activeforeground="#ffffff", **style)
        self.btn_metrics.pack(side="left", padx=4)

        tk.Checkbutton(
            bar, text="Show Ground Truth", variable=self._show_truth,
            command=self._on_view_toggle, font=self.font_small,
            fg=COLORS["text_secondary"], bg=COLORS["bg_header"],
            activebackground=COLORS["bg_header"],
            activeforeground=COLORS["text_primary"],
            selectcolor=COLORS["bg_panel"],
            highlightthickness=0, bd=0).pack(side="left", padx=(14, 4))

        speed = tk.Frame(bar, bg=COLORS["bg_header"])
        speed.pack(side="right", padx=10)
        tk.Label(speed, text="Step delay:", font=self.font_small,
                 fg=COLORS["text_secondary"], bg=COLORS["bg_header"]
                 ).pack(side="left")
        self.speed_var = tk.IntVar(value=self.simulation.step_delay_ms)
        tk.Scale(speed, from_=150, to=3000, orient="horizontal",
                 variable=self.speed_var, command=self._on_speed_change,
                 bg=COLORS["bg_header"], fg=COLORS["text_primary"],
                 troughcolor=COLORS["bg_panel"], highlightthickness=0,
                 length=130, sliderlength=16, font=self.font_small
                 ).pack(side="left")
        tk.Label(speed, text="ms", font=self.font_small,
                 fg=COLORS["text_dim"], bg=COLORS["bg_header"]
                 ).pack(side="left")

        self.status_var = tk.StringVar(
            value="Ready — press START AUTONOMOUS MISSION, or STEP to "
                  "advance one reasoning cycle at a time.")
        tk.Label(self, textvariable=self.status_var, font=self.font_small,
                 fg=COLORS["text_secondary"], bg=COLORS["bg_header"],
                 anchor="w", padx=8, pady=3).pack(fill="x")

    # ==================================================================
    # Grid rendering
    # ==================================================================

    def _believed_status(self, x: int, y: int) -> str:
        """
        What does the rover *believe* about (x, y)?

        Read directly from the knowledge base, so the display can never
        show the rover knowledge it has not actually derived.
        """
        facts = self.kb
        if Literal(f"Hazard_{x}_{y}", True) in facts._facts:
            return "HAZARD"
        if Literal(f"Radiation_{x}_{y}", True) in facts._facts:
            return "RADIATION"
        if Literal(f"Unknown_{x}_{y}", True) in facts._facts:
            return "UNKNOWN"
        if Literal(f"Safe_{x}_{y}", True) in facts._facts:
            return "SAFE"
        return "UNPERCEIVED"

    def _truth_status(self, x: int, y: int) -> str:
        """Ground-truth terrain, for the comparison view."""
        cell = self.env.get_cell(x, y)
        if cell in (CellType.SAFE, CellType.START):
            return "SAFE"
        if cell == CellType.GOAL:
            return "GOAL"
        return cell.value

    def _cell_appearance(self, x: int, y: int) -> Tuple[str, str, str]:
        """Return (background, foreground, label) for one cell."""
        if (x, y) == self.rover.position:
            return COLORS["cell_rover"], COLORS["text_rover"], "ROVER"

        status = (self._truth_status(x, y) if self._show_truth.get()
                  else self._believed_status(x, y))

        if (x, y) == self.env.goal_pos:
            return COLORS["cell_goal"], COLORS["text_goal"], "GOAL"

        if status == "HAZARD":
            return COLORS["cell_hazard"], COLORS["text_hazard"], "HAZARD"
        if status == "RADIATION":
            return COLORS["cell_radiation"], COLORS["text_radiation"], "RAD"
        if status == "UNKNOWN":
            return COLORS["cell_unknown"], COLORS["text_unknown"], "UNKNOWN"
        if status == "SAFE":
            if (x, y) in self.rover.visited:
                return COLORS["cell_visited"], COLORS["text_visited"], "VISITED"
            return COLORS["cell_safe"], COLORS["text_safe"], "SAFE"

        return COLORS["cell_unperceived"], COLORS["text_dim"], "· · ·"

    def _draw_grid(self) -> None:
        """Redraw every cell."""
        self.canvas.delete("all")
        self._cell_items.clear()
        for y in range(self.env.height):
            for x in range(self.env.width):
                self._draw_cell(x, y)

    def _draw_cell(self, x: int, y: int) -> None:
        x1 = x * CELL_SIZE + CELL_PAD
        y1 = y * CELL_SIZE + CELL_PAD
        x2 = x1 + CELL_SIZE - CELL_PAD * 2
        y2 = y1 + CELL_SIZE - CELL_PAD * 2

        background, foreground, label = self._cell_appearance(x, y)

        if (x, y) == self.rover.position:
            border, width = COLORS["border_rover"], 3
        elif (x, y) == self.env.goal_pos:
            border, width = COLORS["border_goal"], 3
        else:
            border, width = COLORS["grid_line"], 1

        items = [self.canvas.create_rectangle(
            x1, y1, x2, y2, fill=background, outline=border, width=width)]

        centre_x = (x1 + x2) // 2
        items.append(self.canvas.create_text(
            centre_x, y1 + 11, text=f"({x},{y})",
            font=self.font_cell, fill=COLORS["text_dim"]))
        items.append(self.canvas.create_text(
            centre_x, (y1 + y2) // 2 + 2, text=label,
            font=self.font_cell_big, fill=foreground))

        # Mark the rover's own trail even under the ground-truth view.
        if (x, y) in self.rover.visited and (x, y) != self.rover.position:
            items.append(self.canvas.create_text(
                centre_x, y2 - 12, text="visited",
                font=self.font_cell, fill=COLORS["text_visited"]))

        self._cell_items[(x, y)] = items

    def _on_view_toggle(self) -> None:
        showing_truth = self._show_truth.get()
        self.grid_frame.configure(
            text=(" MARS GRID — GROUND TRUTH (environment) "
                  if showing_truth else " MARS GRID — ROVER'S KNOWLEDGE "))
        self._draw_grid()
        self.status_var.set(
            "Showing the true map — note the rover has not been told any "
            "of this." if showing_truth else
            "Showing the rover's knowledge base — blank cells have never "
            "been perceived.")

    # ==================================================================
    # Panel updates
    # ==================================================================

    def _update_info_panel(self, record: Optional[DecisionRecord] = None
                           ) -> None:
        metrics = self.rover.metrics
        rx, ry = self.rover.position
        gx, gy = self.env.goal_pos

        self._info_vars["Position"].set(f"({rx},{ry})")
        self._info_vars["Goal"].set(f"({gx},{gy})")

        state = self.simulation.state
        label = {SimState.COMPLETE: "MISSION COMPLETE",
                 SimState.STUCK: "BLOCKED — no provably safe route",
                 SimState.RUNNING: "RUNNING",
                 SimState.PAUSED: "PAUSED",
                 SimState.IDLE: "READY"}[state]
        self._info_vars["Status"].set(label)

        if record:
            perception = next(
                (p for p in record.perceptions
                 if "hazard" in p.lower() or "radiation" in p.lower()
                 or "reveals" in p.lower() or "confirms" in p.lower()),
                record.perceptions[0] if record.perceptions else "—")
            self._info_vars["Perception"].set(self._clip(perception, 44))

            if record.chosen_action:
                self._info_vars["Decision"].set(self._clip(
                    f"{record.chosen_action} → {record.chosen_target}", 30))
            else:
                self._info_vars["Decision"].set("no action")

            self._info_vars["Inference"].set(self._clip(
                ", ".join(record.forward_inferences) or "(fixed point)", 40))

            accepted = sum(1 for c in record.candidates_evaluated
                           if c["accepted"])
            self._info_vars["Entailment"].set(
                f"{accepted} entailed / {record.rejected_count} rejected")

        self._info_vars["KB Facts"].set(str(self.kb.fact_count))
        self._info_vars["KB Rules"].set(str(self.kb.rule_count))
        self._info_vars["KB Clauses"].set(str(self.kb.clause_count))
        self._info_vars["Moves"].set(str(metrics.moves))
        self._info_vars["Path Cost"].set(f"{metrics.path_cost:.1f}")
        self._info_vars["Investigations"].set(str(metrics.investigations))
        self._info_vars["Inferences"].set(str(self.kb.inference_count))
        self._info_vars["Resolutions"].set(str(self.kb.resolution_count))
        self._info_vars["Model Checks"].set(str(self.kb.model_check_count))
        self._info_vars["Rejected"].set(str(metrics.unsafe_actions_rejected))
        self._info_vars["Elapsed"].set(f"{metrics.execution_time_sec:.2f}s")

    def _show_initial_kb_panel(self) -> None:
        self._write(self.kb_text, [
            ("KNOWLEDGE BASE INITIALIZED\n", "header"),
            (f"  Start: TELL(Safe_{self.env.start_pos[0]}_"
             f"{self.env.start_pos[1]}), "
             f"TELL(At_{self.env.start_pos[0]}_{self.env.start_pos[1]})\n",
             "tell"),
            (f"  Goal:  TELL(Goal_{self.env.goal_pos[0]}_"
             f"{self.env.goal_pos[1]})\n", "tell"),
            (f"  Facts: {self.kb.fact_count}   Rules: {self.kb.rule_count}"
             f"   Clauses: {self.kb.clause_count}\n", "dim"),
            ("\n  8 propositional rule schemas are instantiated per cell\n",
             "rule"),
            ("  as the rover perceives it. Nothing else is known.\n", "dim"),
            ("\n  Press START or STEP to begin.\n", "dim"),
        ], clear=True)

    def _update_kb_panel(self, record: DecisionRecord) -> None:
        lines: List[Tuple[str, str]] = [
            (f"\n{'─' * 52}\n", "dim"),
            (f" STEP {record.step:02d}  at {record.position}\n", "step"),
            (f"{'─' * 52}\n", "dim"),
        ]

        for tell in record.kb_tells[:10]:
            lines.append((f"  {tell}\n", "tell"))
        if len(record.kb_tells) > 10:
            lines.append((f"  … {len(record.kb_tells) - 10} more TELLs\n",
                          "dim"))

        for inference in record.forward_inferences:
            lines.append((f"  INFER: {inference}   [Modus Ponens]\n", "infer"))

        for candidate in record.candidates_evaluated:
            tx, ty = candidate["target"]
            answer = candidate.get("ask_result")
            if candidate["accepted"]:
                mark, tag = "ENTAILED    ", "accepted"
            elif candidate["investigate"]:
                mark, tag = "UNCLASSIFIED", "result"
            else:
                mark, tag = "NOT ENTAILED", "rejected"
            lines.append((f"  ASK  KB ⊨ CanMove_{tx}_{ty} ?  → {mark}\n", tag))
            if answer is not None and answer.model_check:
                mc = answer.model_check
                lines.append((
                    f"       resolution {answer.resolution_ops} ops | "
                    f"models {mc['models_satisfying_kb']}/"
                    f"{mc['models_checked']} | agree: "
                    f"{'YES' if answer.consistent else 'NO'}\n", "dim"))

        if record.chosen_action:
            lines.append((f"  ► {record.action_type}: {record.chosen_action} "
                          f"→ {record.chosen_target}\n", "decision"))
        self._write(self.kb_text, lines)

    def _update_explain_panel(self, record: DecisionRecord) -> None:
        segments: List[Tuple[str, str]] = []
        for line in record.explanation.split("\n"):
            stripped = line.strip()
            if stripped.startswith("✓"):
                tag = "accepted"
            elif stripped.startswith("✗"):
                tag = "rejected"
            elif stripped.startswith("?"):
                tag = "result"
            elif stripped.startswith("►"):
                tag = "decision"
            elif stripped.startswith("WHY"):
                tag = "header"
            else:
                tag = "dim"
            segments.append((line + "\n", tag))
        self._write(self.explain_text, segments, clear=True)

    def _on_log_line(self, message: str, tag: str) -> None:
        """
        console listener — mirror one terminal line into the log panel.

        Called synchronously from the agent, which runs on the main thread,
        so it can touch widgets directly.
        """
        try:
            self._write(self.log_text, [(message + "\n", tag or "dim")])
            self._log_lines += 1
            if self._log_lines > MAX_LOG_LINES:
                self.log_text.configure(state="normal")
                self.log_text.delete("1.0", f"{MAX_LOG_LINES // 3}.0")
                self.log_text.configure(state="disabled")
                self._log_lines -= MAX_LOG_LINES // 3
        except tk.TclError:
            pass        # window is closing

    @staticmethod
    def _write(widget: tk.Text, segments: List[Tuple[str, str]],
               clear: bool = False) -> None:
        """Append tagged segments to a read-only text widget."""
        widget.configure(state="normal")
        if clear:
            widget.delete("1.0", "end")
        for text, tag in segments:
            widget.insert("end", text, tag)
        widget.see("end")
        widget.configure(state="disabled")

    @staticmethod
    def _clip(text: str, length: int) -> str:
        return text if len(text) <= length else text[:length - 1] + "…"

    # ==================================================================
    # Controls
    # ==================================================================

    def _cmd_start(self) -> None:
        if self.simulation.is_finished:
            return
        if self.simulation.state == SimState.PAUSED:
            self.simulation.resume()
        self.simulation.set_delay(self.speed_var.get())
        self.status_var.set("Autonomous mission running — the rover is "
                            "reasoning about every move.")
        self._schedule_auto(delay=0)

    def _cmd_step(self) -> None:
        """Advance exactly one agent cycle (the mode to use in a viva)."""
        self._cancel_auto()
        if self.simulation.state == SimState.RUNNING:
            self.simulation.pause()
        record = self.simulation.step()
        if record is None:
            self.status_var.set("Mission already finished — press RESET.")

    def _cmd_pause(self) -> None:
        if self._auto_job is not None:
            self._cancel_auto()
            self.simulation.pause()
            self.btn_pause.configure(text="RESUME")
            self.status_var.set("Paused — press STEP to advance one cycle, "
                                "or RESUME to continue.")
        else:
            self.btn_pause.configure(text="PAUSE")
            self._cmd_start()

    def _cmd_reset(self) -> None:
        self._cancel_auto()
        self.simulation.reset()
        self.btn_start.configure(state="normal")
        self.btn_step.configure(state="normal")
        self.btn_pause.configure(state="disabled", text="PAUSE")
        self._draw_grid()
        self._update_info_panel()
        self._show_initial_kb_panel()
        self._write(self.explain_text, [], clear=True)
        self._write(self.log_text, [], clear=True)
        self._log_lines = 0
        self.status_var.set("Reset — the rover is back at the start with an "
                            "empty knowledge base.")

    def _cmd_metrics(self) -> None:
        self._show_metrics_window(self.rover.metrics)

    def _on_speed_change(self, value) -> None:
        self.simulation.set_delay(int(float(value)))

    # ------------------------------------------------------------------
    # Auto-run, driven by the Tk event loop
    # ------------------------------------------------------------------

    def _schedule_auto(self, delay: Optional[int] = None) -> None:
        """Queue the next automatic step on the main loop."""
        self._cancel_auto()
        if self.simulation.is_finished:
            return
        wait = self.simulation.step_delay_ms if delay is None else delay
        self._auto_job = self.after(max(1, wait), self._auto_tick)

    def _auto_tick(self) -> None:
        """One automatic step, then re-queue."""
        self._auto_job = None
        if self.simulation.is_finished:
            return
        self.simulation.step()
        if not self.simulation.is_finished:
            self._schedule_auto()

    def _cancel_auto(self) -> None:
        if self._auto_job is not None:
            try:
                self.after_cancel(self._auto_job)
            except tk.TclError:
                pass
            self._auto_job = None

    # ==================================================================
    # Simulation callbacks (main thread — no marshalling needed)
    # ==================================================================

    def _on_step_complete(self, record: DecisionRecord) -> None:
        self._draw_grid()
        self._update_info_panel(record)
        self._update_kb_panel(record)
        self._update_explain_panel(record)

        if record.chosen_action:
            self.status_var.set(
                f"Step {record.step}: {record.action_type} "
                f"{record.chosen_action} → {record.chosen_target}   |   "
                f"KB {self.kb.fact_count} facts, {self.kb.clause_count} "
                f"clauses   |   {record.rejected_count} action(s) rejected "
                f"by the KB this cycle")
        self.update_idletasks()

    def _on_state_change(self, state: SimState) -> None:
        if state == SimState.RUNNING:
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="normal", text="PAUSE")
        elif state == SimState.PAUSED:
            self.btn_start.configure(state="normal")
        elif state.is_finished:
            self._cancel_auto()
            self.btn_start.configure(state="disabled")
            self.btn_pause.configure(state="disabled")
            self.btn_step.configure(state="disabled")
            metrics = self.rover.metrics
            if state == SimState.COMPLETE:
                self.status_var.set(
                    f"MISSION COMPLETE — {metrics.moves} moves, path cost "
                    f"{metrics.path_cost:.1f}, "
                    f"{metrics.unsafe_actions_rejected} unsafe actions "
                    f"rejected, {metrics.inference_ops} inferences.")
            else:
                self.status_var.set(
                    "MISSION BLOCKED — the rover could not prove any "
                    "remaining action safe. Press RESET.")

    def _on_mission_complete(self, metrics: Metrics) -> None:
        self._draw_grid()
        self._update_info_panel()
        self.after(200, lambda: self._show_metrics_window(metrics))

    # ------------------------------------------------------------------
    # Metrics window
    # ------------------------------------------------------------------

    def _show_metrics_window(self, metrics: Metrics) -> None:
        window = tk.Toplevel(self)
        window.title("Performance Metrics")
        window.configure(bg=COLORS["bg_panel"])
        window.geometry("560x620")
        window.transient(self)

        heading = ("MISSION COMPLETE" if metrics.mission_success
                   else "MISSION METRICS")
        tk.Label(window, text=heading,
                 font=tkfont.Font(family="Segoe UI", size=15, weight="bold"),
                 fg=COLORS["text_goal"], bg=COLORS["bg_panel"]).pack(pady=10)

        text = tk.Text(window, font=tkfont.Font(family="Consolas", size=9),
                       bg=COLORS["bg_log"], fg=COLORS["text_white"], bd=0,
                       padx=12, pady=8, wrap="none")
        text.pack(fill="both", expand=True, padx=10)
        text.insert("end", metrics.format_final_report())

        statistics = self.kb.get_clause_statistics()
        text.insert("end", "\n\n" + "=" * 60)
        text.insert("end", "\n              KNOWLEDGE BASE CLAUSE TYPES\n")
        text.insert("end", "=" * 60 + "\n")
        text.insert("end", f"  Total clauses:      {statistics['total']}\n")
        text.insert("end", f"  Unit clauses:       {statistics['unit']}  "
                           f"(atomic facts)\n")
        text.insert("end", f"  Definite clauses:   {statistics['definite']}  "
                           f"(exactly one positive literal)\n")
        text.insert("end", f"  Horn clauses:       {statistics['horn']}  "
                           f"(at most one positive literal)\n")
        text.insert("end", f"  Goal clauses:       {statistics['goal']}  "
                           f"(no positive literal)\n")
        text.insert("end", f"  Non-Horn clauses:   {statistics['non_horn']}\n")
        text.insert("end", "\n  Every rule the rover TELLs its KB is a "
                           "definite clause, which is\n"
                           "  why forward chaining with Modus Ponens "
                           "suffices to derive its\n"
                           "  conclusions, and why resolution settles each "
                           "query so cheaply.\n")
        text.configure(state="disabled")

        tk.Button(window, text="Close", command=window.destroy,
                  font=self.font_btn, bg=COLORS["btn_reset"],
                  fg=COLORS["btn_reset_fg"], bd=0, padx=18, pady=6
                  ).pack(pady=10)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------

    def _on_close(self) -> None:
        self._cancel_auto()
        console.remove_listener(self._on_log_line)
        self.destroy()
