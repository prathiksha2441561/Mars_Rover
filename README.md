# Autonomous Mars Rover — Propositional Logic Knowledge-Based Agent

**AI Specialization Project | Unit 3: Logical Agents / Propositional Logic**

---

## 1. Project Title

**Autonomous Mars Rover — Propositional Logic Knowledge-Based Agent**

A complete simulation of an autonomous rover navigating a 2D Mars grid using a real propositional logic Knowledge Base. Every movement decision is made by logical inference, not hard-coded pathfinding.

---

## 2. Scenario

A Mars rover is deployed on a 7×7 grid representing a section of the Martian surface. The grid contains safe terrain, hazard zones, radiation zones, unknown terrain, a start position, and a goal position.

The rover must autonomously navigate from start to goal while:
- Perceiving environmental information through sensors
- Updating its Knowledge Base (KB) with propositional facts
- Using propositional logic inference to determine what is safe
- Deciding whether movement to each neighbor is logically justified
- Moving only when logically permitted
- Logging the complete reasoning chain in real time

---

## 3. Problem Statement

Design a **Knowledge-Based Agent** that demonstrates propositional logic reasoning. The rover must not have direct access to the map — it builds knowledge through sensor perceptions and logical inference.

The central agent loop is:

```
PERCEIVE → TELL(KB) → INFER → ASK(KB) → DECIDE → ACT → SUCCESSOR STATE → UPDATE KB → REPEAT
```

---

## 4. Objectives

- Implement a real propositional Knowledge Base with TELL/ASK/RETRACT/INFER
- Implement resolution-based theorem proving (KB ⊨ α)
- Implement CNF conversion pipeline
- Implement forward chaining and backward reasoning
- Demonstrate Modus Ponens, Modus Tollens, and Disjunctive Syllogism
- Separate environment ground truth from rover knowledge
- Provide live console logs showing the complete reasoning chain
- Provide a visual Tkinter UI with KB log, info panel, and explanation panel

---

## 5. Technologies

| Component | Technology |
|---|---|
| Language | Python 3 |
| GUI | Tkinter (standard library) |
| Logic | Custom propositional logic engine |
| Inference | Resolution refutation + forward chaining |
| Storage | In-memory KB (no database) |

Run with:
```bash
python main.py
python main.py --random       # Random map
python main.py --no-ui        # Console only
python main.py --delay 500    # Step speed (ms)
```

---

## 6. Knowledge-Based Agent Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      ROVER AGENT                            │
│                                                             │
│  ┌──────────┐   PERCEPTION   ┌──────────────────────────┐  │
│  │ SENSORS  │ ──────────────►│    KNOWLEDGE BASE (KB)   │  │
│  │          │                │                          │  │
│  │ Hazard   │   TELL(fact)   │  Facts: {Safe_2_3, ...}  │  │
│  │ Radiation│ ◄──────────────│  Rules: Hazard→¬Move     │  │
│  │ Terrain  │                │  CNF Clauses             │  │
│  │ Goal     │   ASK(query)   │                          │  │
│  └──────────┘ ──────────────►│  Resolution Engine       │  │
│                              │  Model Checker           │  │
│  ┌──────────┐   DECISION     │  Forward Chaining        │  │
│  │  ROVER   │ ◄──────────────│  Backward Reasoning      │  │
│  │  AGENT   │                └──────────────────────────┘  │
│  │          │                                              │
│  │  ACT     │   UPDATE KB                                  │
│  │  MOVE    │ ──────────────► At_x_y, Visited_x_y, ...    │
│  └──────────┘                                              │
│                                                             │
│  ENVIRONMENT (ground truth — NOT directly visible to KB)   │
└─────────────────────────────────────────────────────────────┘
```

The rover's KB is completely separate from the environment's ground truth. The rover only knows what its sensors have told it.

---

## 7. PEAS Framework

### Performance Measure
- Reach the goal safely
- Avoid hazards and radiation zones
- Minimize total path cost
- Minimize unnecessary movements
- Perform correct logical inference at every step

### Environment
- 7×7 Mars grid
- Safe terrain cells
- Unknown terrain (must be sensed)
- Hazard zones (block movement)
- Radiation zones (block entry)
- Goal cell

### Actuators
| Actuator | Effect |
|---|---|
| Move UP | Change position by (0,-1) |
| Move DOWN | Change position by (0,+1) |
| Move LEFT | Change position by (-1,0) |
| Move RIGHT | Change position by (+1,0) |
| Investigate | Sense unknown cell |

### Sensors
| Sensor | Detects |
|---|---|
| Hazard sensor | Hazard at adjacent cells |
| Radiation sensor | Radiation at adjacent cells |
| Terrain sensor | Safe/Unknown at adjacent cells |
| Goal sensor | Goal position |
| Adjacent-cell perception | All 4 neighbors simultaneously |

---

## 8. State-Space Formulation

```
State:        S = (x, y, KB, visited, perception_state)
Initial State: (0,0), initial KB facts, empty visited set
Actions:       UP, DOWN, LEFT, RIGHT, (INVESTIGATE on unknown)
Goal Test:     position == goal_pos  →  KB ⊨ MissionComplete
Path Cost:     1 per movement
```

---

## 9. Propositional Symbols

### Position Fluents
| Symbol | Meaning |
|---|---|
| `At_x_y` | Rover is currently at coordinate (x,y) |
| `Visited_x_y` | Rover has previously visited (x,y) |

### Terrain Propositions
| Symbol | Meaning |
|---|---|
| `Safe_x_y` | Cell (x,y) is safe terrain |
| `Hazard_x_y` | Cell (x,y) contains a hazard |
| `Radiation_x_y` | Cell (x,y) contains radiation |
| `Unknown_x_y` | Cell (x,y) is not yet surveyed |
| `Goal_x_y` | Cell (x,y) is the mission goal |

### Action/Decision Propositions
| Symbol | Meaning |
|---|---|
| `CanMove_x_y` | Rover is permitted to move to (x,y) |
| `MoveForward_x_y` | Action: move rover to (x,y) |
| `Enter_x_y` | Action: enter cell (x,y) |

### Perception Propositions
| Symbol | Meaning |
|---|---|
| `PerceiveHazard_x_y` | Hazard sensor fired for (x,y) |
| `PerceiveRadiation_x_y` | Radiation sensor fired for (x,y) |

### Goal/Mission Propositions
| Symbol | Meaning |
|---|---|
| `MissionComplete` | Rover has reached the goal |
| `Investigate_x_y` | Unknown cell should be investigated |

---

## 10. Logical Rules

| Rule | Propositional Form |
|---|---|
| Rule 1 — Hazard blocks movement | `Hazard_x_y → ¬MoveForward_x_y` |
| Rule 2 — Radiation blocks entry | `Radiation_x_y → ¬Enter_x_y` |
| Rule 3 — Safe terrain allows movement | `Safe_x_y ∧ ¬Hazard_x_y ∧ ¬Radiation_x_y → CanMove_x_y` |
| Rule 4 — Position enables movement | `At_x_y ∧ CanMove_x2_y2 → MoveTo_x2_y2` |
| Rule 5 — Goal reached | `At_goal → MissionComplete` |
| Rule 6 — Unknown needs investigation | `Unknown_x_y → Investigate_x_y` |
| Rule 7 — Hazard perception | `PerceiveHazard_x_y → Hazard_x_y` |
| Rule 8 — Radiation perception | `PerceiveRadiation_x_y → Radiation_x_y` |

---

## 11. CNF Conversion

All rules are converted to Conjunctive Normal Form for use in resolution.

### Steps (following AIMA):

1. **Biconditional Elimination**: `α ↔ β` → `(α → β) ∧ (β → α)`
2. **Implication Elimination**: `α → β` → `¬α ∨ β`
3. **Move Negations Inward (De Morgan's)**:
   - `¬(α ∧ β)` → `¬α ∨ ¬β`
   - `¬(α ∨ β)` → `¬α ∧ ¬β`
   - `¬¬α` → `α` (Double negation elimination)
4. **Distribute OR over AND**: `α ∨ (β ∧ γ)` → `(α ∨ β) ∧ (α ∨ γ)`
5. **Collect Clauses**: Each AND-separated disjunction is a clause

### Example — Rule 1:
```
Hazard_2_3 → ¬MoveForward_2_3
  Step 1: No biconditionals
  Step 2: ¬Hazard_2_3 ∨ ¬MoveForward_2_3
  Step 3: No negations to move
  Step 4: No distribution needed
  CNF:    {¬Hazard_2_3 ∨ ¬MoveForward_2_3}
```

---

## 12. Resolution

Resolution is the primary inference mechanism.

### Algorithm (Refutation):

To prove KB ⊨ α:
1. Add ¬α to the KB clauses
2. Apply the resolution rule repeatedly:
   - If C₁ = {P, ...} and C₂ = {¬P, ...}, derive (C₁ - {P}) ∪ (C₂ - {¬P})
3. If the **empty clause {}** is derived → **ENTAILED** (contradiction found)
4. If no new clauses can be derived → **NOT ENTAILED**

### Example:
```
QUERY: KB ⊨ ¬MoveForward_2_3 ?
NEGATED QUERY: MoveForward_2_3

KB Clauses:
  {Hazard_2_3}                           (known fact)
  {¬Hazard_2_3 ∨ ¬MoveForward_2_3}      (Rule 1 in CNF)
  {MoveForward_2_3}                      (negated query)

Resolution Step 1: {Hazard_2_3} + {¬Hazard_2_3 ∨ ¬MoveForward_2_3}
  → {¬MoveForward_2_3}

Resolution Step 2: {¬MoveForward_2_3} + {MoveForward_2_3}
  → {} (empty clause = contradiction)

CONCLUSION: ENTAILED
```

---

## 13. Model Checking

Model checking enumerates all possible truth assignments.

```
For n proposition symbols, there are 2^n models.
KB ⊨ α  iff  every model satisfying KB also satisfies α.
```

**Output format:**
```
MODEL CHECKING: KB ⊨ ¬MoveForward_2_3 ?
  Possible Models Checked:       8
  Models Satisfying KB:          3
  Models Entailing Query:        3
  CONCLUSION: ENTAILED
```

This is used as a **second verification mechanism** alongside resolution for academic completeness. It is limited to ≤14 local symbols for performance.

---

## 14. Forward Propagation

Forward chaining fires rules when all antecedents are known.

```
Initial fact:   Hazard_2_4
Rule:           Hazard_2_4 → ¬MoveForward_2_4
Inference:      ¬MoveForward_2_4  [Modus Ponens]

Initial facts:  Safe_3_3, ¬Hazard_3_3, ¬Radiation_3_3
Rule:           Safe ∧ ¬Hazard ∧ ¬Radiation → CanMove_3_3
Inference:      CanMove_3_3
```

This chain is logged in the console as:
```
FORWARD CHAIN: Safe_3_3 ∧ ¬Hazard_3_3 ∧ ¬Radiation_3_3 → CanMove_3_3 → INFER CanMove_3_3
  [Modus Ponens: Safe_3_3 ∧ ¬Hazard_3_3 ∧ ¬Radiation_3_3 → CanMove_3_3]
```

---

## 15. Backward Reasoning

When the rover queries whether it can move to a cell, it first performs backward reasoning to explain what is required:

```
GOAL: CanMove_2_4?
Supporting rule: Safe_2_4 ∧ ¬Hazard_2_4 ∧ ¬Radiation_2_4 → CanMove_2_4
Required conditions:
  Safe_2_4:       ✓ KNOWN
  ¬Hazard_2_4:    ✓ KNOWN
  ¬Radiation_2_4: ✗ UNKNOWN
→ CANNOT YET CONCLUDE: CanMove_2_4
```

This is used as an **explanation mechanism** (not as the primary inference engine).

---

## 16. TELL / ASK

The KB API uses the standard logical agent terminology:

```python
kb.tell("Safe_2_3")          # Assert Safe_2_3 is TRUE
kb.tell("Hazard_2_3", False) # Assert Hazard_2_3 is FALSE
kb.ask("CanMove_2_3")        # Query: KB ⊨ CanMove_2_3 ?
kb.retract("Visited_1_1")    # Remove a fact
kb.infer_forward()           # Run forward chaining
```

---

## 17. Entailment

```
KB ⊨ α
```

Means: "α is true in every model where the KB is true."

Used throughout the project:
- Console: `KB ⊨ CanMove_3_3 — ACCEPTED`
- UI: ASK/RESULT panel shows entailment status
- Code: `kb.ask(symbol)` returns `(bool, explanation)`

---

## 18. Models

A **model** is a possible truth assignment to all proposition symbols.

```
MODEL 1: Safe_2_2=True, Hazard_2_2=False, Radiation_2_2=False
MODEL 2: Safe_2_2=False, Hazard_2_2=True, Radiation_2_2=False
```

The model checker:
- Enumerates all 2^n models for n local symbols
- Counts models satisfying KB
- Counts models entailing query
- KB ⊨ query iff (satisfying == entailing)

---

## 19. Soundness

```
If KB ⊢ α  then  KB ⊨ α
```

The resolution inference system is **sound**: it does not derive false conclusions from valid premises. Every fact derived by forward chaining or resolution is logically entailed by the KB.

---

## 20. Completeness

```
If KB ⊨ α  then  KB ⊢ α
```

Propositional resolution is **complete**: if α is entailed, resolution will eventually derive it (given enough steps). The model checker is also complete for the symbol set it evaluates.

---

## 21. Satisfiability

A proposition is **satisfiable** if there is at least one model in which it is true.

Example: `Safe_2_3 ∧ Hazard_2_3` is **unsatisfiable** (a cell cannot be both safe and a hazard). The KB maintains consistency by retracting complements on TELL.

---

## 22. Validity

A proposition is **valid** (tautology) if it is true in every possible model.

Example: `P ∨ ¬P` is valid (always true). The CNFConverter drops tautological clauses automatically.

---

## 23. Fluents

A **fluent** is a proposition whose value can change with actions.

| Fluent | Changes when |
|---|---|
| `At_x_y` | Rover moves |
| `Visited_x_y` | Rover enters a cell |
| `CanMove_x_y` | New terrain information is perceived |
| `MissionComplete` | Rover reaches goal |

---

## 24. Successor States

After each action, the KB is updated to reflect the new world state:

```
CURRENT STATE:   At_2_3
ACTION:          MoveRight
SUCCESSOR STATE: At_2_4

KB UPDATED:
  TELL: At_2_4
  TELL: Visited_2_4
  TELL: Visited_2_3
```

---

## 25. Simulation Workflow

```
1. Initialize environment (7×7 Mars grid)
2. Initialize KB (start position, goal rule)
3. For each step:
   a. PERCEIVE: Sensor reads all 4 neighbors
   b. TELL(KB): Assert all perception propositions
   c. INFER: Forward chaining derives new facts
   d. For each candidate direction:
      - Backward explain: what is needed for CanMove?
      - ASK(KB): KB ⊨ CanMove_{nx}_{ny} ?
      - RESOLUTION: refutation proof
      - Accept or reject candidate
   e. DECIDE: Accepted candidates sorted by Manhattan distance
   f. ACT: Move to chosen cell
   g. UPDATE KB: Successor state fluents
   h. Check goal
4. Display metrics
```

---

## 26. Performance Metrics

| Metric | Description |
|---|---|
| Execution Time | Total wall-clock time |
| Moves | Number of movement actions |
| Path Cost | Sum of movement costs (1 per move) |
| Cells Visited | Distinct cells explored |
| Inference Operations | Forward chaining rule firings |
| Resolution Operations | Resolution step count |
| Unsafe Actions Rejected | Moves blocked by KB inference |

---

## 27. Complexity Analysis

### Model Checking
- **Time**: O(2^n) where n = number of proposition symbols
- Enumerates all truth assignments
- **Mitigation**: Limited to ≤14 local symbols in this implementation

### Resolution
- **Worst case**: Exponential (clause growth can be exponential)
- **In practice**: Very fast for small propositional symbol sets
- **Safety limit**: 5000 clauses maximum per query

### Observed Performance (default map)
- Typically completes in < 1 second
- ~14-20 steps to reach goal
- ~37+ inference operations

---

## 28. How to Run

```bash
cd Mars_Rover
python main.py                  # Full UI
python main.py --no-ui          # Console only
python main.py --random         # Random map
python main.py --delay 500      # Faster (500ms/step)
python main.py --delay 2000     # Slower (2s/step)

# Run tests
set PYTHONIOENCODING=utf-8
python tests/test_logic.py
python tests/test_rover.py
```

---

## 29. Example Console Output

```
==================================================
  ROVER STEP 07
==================================================
  CURRENT STATE: At_2_3

  [STEP 1] PERCEIVE
    HAZARD SENSOR: Hazard detected at (2,4)
    TERRAIN SENSOR: Safe terrain at (3,3)

  [STEP 2] TELL(KB)
    TELL: Hazard_2_4
    RULE ADDED: Hazard_2_4 → ¬MoveForward_2_4

  [STEP 3] FORWARD CHAINING
    FORWARD CHAIN: Hazard_2_4 → ¬MoveForward_2_4 → INFER ¬MoveForward_2_4
    [Modus Ponens: Hazard_2_4 → ¬MoveForward_2_4]

  [STEP 4] EVALUATE CANDIDATES
    CANDIDATE: DOWN → (2,4)
    RULE ACTIVATED: Hazard_2_4 → ¬MoveForward_2_4
    RESULT: NOT ENTAILED — REJECTED: HAZARD at (2,4)

    CANDIDATE: RIGHT → (3,3)
    RESULT: KB ⊨ CanMove_3_3 — ACCEPTED

  [STEP 5] DECISION: MOVE RIGHT → (3,3)
  [STEP 6] SUCCESSOR STATE: At_3_3
  PATH COST: 7.0
==================================================
```

---

## 30. Limitations and Future Improvements

- **Sensors are perfect**: Real sensors would have noise/uncertainty
- **No FOL**: The project uses propositional logic only (as required for Unit 3)
- **Backtracking**: Simple path-reversal backtrack; more sophisticated would use BFS over safe cells
- **Cycle detection**: The Manhattan heuristic can cause revisits in complex maps
- **Future**: DPLL-based solver, FOL extension, noisy sensors, planning horizon

---

## Project Structure

```
Mars_Rover/
├── main.py           Entry point
├── environment.py    Mars grid (ground truth, separate from KB)
├── rover.py          RoverAgent: KB agent loop
├── knowledge_base.py KnowledgeBase: TELL/ASK/RETRACT/INFER
├── logic.py          Literal, Clause, CNFConverter
├── resolution.py     Resolution engine (KB ⊨ α)
├── model_checker.py  Model checking (truth-table enumeration)
├── sensors.py        SensorSystem: environment → propositions
├── simulation.py     Simulation controller
├── metrics.py        Performance metrics
├── ui.py             Tkinter visual interface
├── tests/
│   ├── test_logic.py Logic, CNF, resolution tests
│   └── test_rover.py Rover, sensor, simulation tests
├── README.md
├── SUMMARY_TEMPLATE.md
└── requirements.txt
```
