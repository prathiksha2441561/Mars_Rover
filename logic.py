"""
logic.py
========
Core propositional logic data structures and CNF conversion.

Implements:
  - Literal: an atomic proposition with optional negation
  - Clause: a disjunction of literals (CNF clause)
  - CNFConverter: converts logical expressions to CNF form
    Steps: Biconditional → Implication Elimination → Move ¬ inward
           (De Morgan's, double negation) → Distributivity → Clauses

This module supports the Resolution Engine and Knowledge Base.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import FrozenSet, List, Set, Tuple, Union


# ---------------------------------------------------------------------------
# Literal
# ---------------------------------------------------------------------------

@dataclass(frozen=True, order=True)
class Literal:
    """
    A propositional literal: an atomic symbol with a polarity.

    Examples:
        Literal("Safe_2_3", positive=True)  → Safe_2_3
        Literal("Safe_2_3", positive=False) → ¬Safe_2_3
    """
    symbol: str
    positive: bool = True

    def __str__(self) -> str:
        return self.symbol if self.positive else f"¬{self.symbol}"

    def __repr__(self) -> str:
        return str(self)

    def negate(self) -> "Literal":
        """Return the complement of this literal."""
        return Literal(self.symbol, not self.positive)

    def is_complement_of(self, other: "Literal") -> bool:
        """True if this literal is the negation of other."""
        return self.symbol == other.symbol and self.positive != other.positive


# ---------------------------------------------------------------------------
# Clause
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Clause:
    """
    A disjunction of literals — a single CNF clause.

    Example:
        ¬Hazard_2_3 ∨ ¬MoveForward_2_3

    An empty clause {} represents a contradiction (False).
    A clause with a single literal is a unit clause.
    """
    literals: FrozenSet[Literal]

    def __init__(self, literals: Union[FrozenSet[Literal], Set[Literal], List[Literal]]):
        object.__setattr__(self, "literals", frozenset(literals))

    def __str__(self) -> str:
        if not self.literals:
            return "{}"  # Empty clause = contradiction
        return " ∨ ".join(str(lit) for lit in sorted(self.literals))

    def __repr__(self) -> str:
        return f"Clause({str(self)})"

    def __len__(self) -> int:
        return len(self.literals)

    def __iter__(self):
        return iter(self.literals)

    def is_empty(self) -> bool:
        """Empty clause = contradiction derived."""
        return len(self.literals) == 0

    def is_tautology(self) -> bool:
        """A clause is a tautology if it contains both P and ¬P."""
        symbols_positive = {lit.symbol for lit in self.literals if lit.positive}
        symbols_negative = {lit.symbol for lit in self.literals if not lit.positive}
        return bool(symbols_positive & symbols_negative)

    def is_unit(self) -> bool:
        """A unit clause contains exactly one literal (an atomic fact)."""
        return len(self.literals) == 1

    # ------------------------------------------------------------------
    # Clause taxonomy
    #
    # These classifiers are used by the KB's clause-statistics report and
    # by the README's explanation of clause types.  Resolution itself
    # works on *general* clauses, so it never depends on these — but the
    # rover's rules happen to all be definite clauses, which is why
    # forward chaining (Modus Ponens) is able to derive everything the
    # rover needs without a full resolution search.
    # ------------------------------------------------------------------

    def positive_literal_count(self) -> int:
        """Number of non-negated literals in the clause."""
        return sum(1 for lit in self.literals if lit.positive)

    def is_horn(self) -> bool:
        """
        Horn clause: at most ONE positive literal.

            ¬A ∨ ¬B ∨ C     (Horn — one positive literal C)
            ¬A ∨ ¬B         (Horn — no positive literal)
            A ∨ B           (NOT Horn — two positive literals)

        Horn clauses are important because entailment for Horn KBs can be
        decided in linear time by forward chaining, instead of the
        potentially exponential cost of general resolution.
        """
        return self.positive_literal_count() <= 1

    def is_definite(self) -> bool:
        """
        Definite clause: exactly ONE positive literal.

            ¬Safe_2_3 ∨ Hazard_2_3 ∨ Radiation_2_3 ∨ CanMove_2_3

        Equivalent to the implication
            Safe_2_3 ∧ ¬Hazard_2_3 ∧ ¬Radiation_2_3 → CanMove_2_3
        Every rule the rover TELLs its KB is a definite clause.
        """
        return self.positive_literal_count() == 1

    def is_goal_clause(self) -> bool:
        """
        Goal clause (negative clause): NO positive literals.

            ¬CanMove_2_4

        Resolution by refutation works by adding the *negation* of the
        query to the KB.  When the query is a positive literal, that
        negation is exactly a goal clause — which is why the refutation
        procedure is sometimes described as "resolving against the goal".
        """
        return len(self.literals) > 0 and self.positive_literal_count() == 0

    def as_implication(self) -> str:
        """
        Render a definite clause in its equivalent implication form.

        ``¬A ∨ ¬B ∨ C``  →  ``A ∧ B → C``
        Returns the plain disjunction string for non-definite clauses.
        """
        if not self.is_definite():
            return str(self)
        head = next(lit for lit in self.literals if lit.positive)
        body = sorted(lit for lit in self.literals if not lit.positive)
        if not body:
            return str(head)
        antecedent = " ∧ ".join(str(lit.negate()) for lit in body)
        return f"{antecedent} → {head}"


def classify_clauses(clauses: List["Clause"]) -> dict:
    """
    Summarise a clause set by clause type.

    Used by the KB statistics panel and by the README to show, with real
    numbers, that the rover's knowledge base is a *definite* (and hence
    Horn) clause set.
    """
    return {
        "total": len(clauses),
        "unit": sum(1 for c in clauses if c.is_unit()),
        "horn": sum(1 for c in clauses if c.is_horn()),
        "definite": sum(1 for c in clauses if c.is_definite()),
        "goal": sum(1 for c in clauses if c.is_goal_clause()),
        "non_horn": sum(1 for c in clauses if not c.is_horn()),
    }


# ---------------------------------------------------------------------------
# Logical Expression AST
# ---------------------------------------------------------------------------

# We represent logical expressions as nested tuples/lists:
#   ("atom", symbol)
#   ("not", expr)
#   ("and", expr, expr)
#   ("or", expr, expr)
#   ("implies", expr, expr)
#   ("iff", expr, expr)

Expr = Union[Tuple, str]  # type alias


def atom(symbol: str) -> Expr:
    """Create an atomic proposition expression."""
    return ("atom", symbol)


def neg(expr: Expr) -> Expr:
    """Create a NOT expression."""
    return ("not", expr)


def conj(a: Expr, b: Expr) -> Expr:
    """Create an AND expression."""
    return ("and", a, b)


def disj(a: Expr, b: Expr) -> Expr:
    """Create an OR expression."""
    return ("or", a, b)


def impl(a: Expr, b: Expr) -> Expr:
    """Create an IMPLIES expression (a → b)."""
    return ("implies", a, b)


def iff(a: Expr, b: Expr) -> Expr:
    """Create a BICONDITIONAL expression (a ↔ b)."""
    return ("iff", a, b)


# ---------------------------------------------------------------------------
# CNF Converter
# ---------------------------------------------------------------------------

class CNFConverter:
    """
    Converts logical expressions to Conjunctive Normal Form (CNF).

    Pipeline (following AIMA standard):
      1. Eliminate biconditionals (↔)
      2. Eliminate implications (→)
      3. Move negations inward (De Morgan's laws, double negation)
      4. Distribute OR over AND
      5. Collect clauses

    Each step is traceable for educational demonstration.
    """

    def convert(self, expr: Expr) -> List[Clause]:
        """
        Convert a logical expression to a list of CNF clauses.

        Returns a list of Clause objects. The conjunction of all clauses
        is logically equivalent to the original expression.
        """
        step1 = self._eliminate_biconditionals(expr)
        step2 = self._eliminate_implications(step1)
        step3 = self._move_negation_inward(step2)
        step4 = self._distribute_or_over_and(step3)
        clauses = self._collect_clauses(step4)
        return clauses

    def convert_with_steps(self, expr: Expr) -> Tuple[List[Clause], List[str]]:
        """
        Convert and return both clauses and a step-by-step trace.
        Useful for educational display and console logging.
        """
        steps = []
        steps.append(f"Original: {self._expr_str(expr)}")

        step1 = self._eliminate_biconditionals(expr)
        steps.append(f"After biconditional elimination: {self._expr_str(step1)}")

        step2 = self._eliminate_implications(step1)
        steps.append(f"After implication elimination: {self._expr_str(step2)}")

        step3 = self._move_negation_inward(step2)
        steps.append(f"After moving ¬ inward (De Morgan's): {self._expr_str(step3)}")

        step4 = self._distribute_or_over_and(step3)
        steps.append(f"After distribution (OR over AND): {self._expr_str(step4)}")

        clauses = self._collect_clauses(step4)
        steps.append(f"CNF Clauses: {[str(c) for c in clauses]}")
        return clauses, steps

    # ------------------------------------------------------------------
    # Step 1: Eliminate biconditionals
    # α ↔ β  →  (α → β) ∧ (β → α)
    # ------------------------------------------------------------------
    def _eliminate_biconditionals(self, expr: Expr) -> Expr:
        if not isinstance(expr, tuple):
            return expr
        op = expr[0]
        if op == "atom":
            return expr
        elif op == "iff":
            a = self._eliminate_biconditionals(expr[1])
            b = self._eliminate_biconditionals(expr[2])
            # (α → β) ∧ (β → α)
            return conj(impl(a, b), impl(b, a))
        elif op in ("not", "and", "or", "implies"):
            return (op,) + tuple(self._eliminate_biconditionals(sub) for sub in expr[1:])
        return expr

    # ------------------------------------------------------------------
    # Step 2: Eliminate implications
    # α → β  →  ¬α ∨ β
    # ------------------------------------------------------------------
    def _eliminate_implications(self, expr: Expr) -> Expr:
        if not isinstance(expr, tuple):
            return expr
        op = expr[0]
        if op == "atom":
            return expr
        elif op == "implies":
            a = self._eliminate_implications(expr[1])
            b = self._eliminate_implications(expr[2])
            # ¬α ∨ β
            return disj(neg(a), b)
        elif op in ("not", "and", "or"):
            return (op,) + tuple(self._eliminate_implications(sub) for sub in expr[1:])
        return expr

    # ------------------------------------------------------------------
    # Step 3: Move negations inward
    # ¬(α ∧ β)  →  ¬α ∨ ¬β  (De Morgan's)
    # ¬(α ∨ β)  →  ¬α ∧ ¬β  (De Morgan's)
    # ¬¬α       →  α         (Double negation)
    # ------------------------------------------------------------------
    def _move_negation_inward(self, expr: Expr) -> Expr:
        if not isinstance(expr, tuple):
            return expr
        op = expr[0]
        if op == "atom":
            return expr
        elif op == "not":
            inner = expr[1]
            if not isinstance(inner, tuple):
                return expr
            inner_op = inner[0]
            if inner_op == "atom":
                return expr  # ¬atom stays
            elif inner_op == "not":
                # Double negation: ¬¬α → α
                return self._move_negation_inward(inner[1])
            elif inner_op == "and":
                # De Morgan: ¬(α ∧ β) → ¬α ∨ ¬β
                return self._move_negation_inward(
                    disj(neg(inner[1]), neg(inner[2]))
                )
            elif inner_op == "or":
                # De Morgan: ¬(α ∨ β) → ¬α ∧ ¬β
                return self._move_negation_inward(
                    conj(neg(inner[1]), neg(inner[2]))
                )
        elif op in ("and", "or"):
            return (op,) + tuple(self._move_negation_inward(sub) for sub in expr[1:])
        return expr

    # ------------------------------------------------------------------
    # Step 4: Distribute OR over AND
    # α ∨ (β ∧ γ)  →  (α ∨ β) ∧ (α ∨ γ)
    # ------------------------------------------------------------------
    def _distribute_or_over_and(self, expr: Expr) -> Expr:
        if not isinstance(expr, tuple):
            return expr
        op = expr[0]
        if op == "atom":
            return expr
        elif op == "and":
            a = self._distribute_or_over_and(expr[1])
            b = self._distribute_or_over_and(expr[2])
            return conj(a, b)
        elif op == "or":
            a = self._distribute_or_over_and(expr[1])
            b = self._distribute_or_over_and(expr[2])
            # If either side is a conjunction, distribute
            if isinstance(a, tuple) and a[0] == "and":
                return self._distribute_or_over_and(
                    conj(disj(a[1], b), disj(a[2], b))
                )
            elif isinstance(b, tuple) and b[0] == "and":
                return self._distribute_or_over_and(
                    conj(disj(a, b[1]), disj(a, b[2]))
                )
            return disj(a, b)
        elif op == "not":
            return expr  # Should be fully pushed in at this point
        return expr

    # ------------------------------------------------------------------
    # Step 5: Collect clauses from an AND-tree of OR-clauses
    # ------------------------------------------------------------------
    def _collect_clauses(self, expr: Expr) -> List[Clause]:
        if not isinstance(expr, tuple):
            return []
        op = expr[0]
        if op == "atom":
            return [Clause({Literal(expr[1], True)})]
        elif op == "not":
            inner = expr[1]
            if isinstance(inner, tuple) and inner[0] == "atom":
                return [Clause({Literal(inner[1], False)})]
            return []
        elif op == "and":
            return self._collect_clauses(expr[1]) + self._collect_clauses(expr[2])
        elif op == "or":
            lits = self._collect_literals_from_or(expr)
            if lits is not None:
                c = Clause(lits)
                if c.is_tautology():
                    return []  # Tautologies can be dropped
                return [c]
        return []

    def _collect_literals_from_or(self, expr: Expr):
        """Flatten an OR-tree into a set of literals."""
        if not isinstance(expr, tuple):
            return None
        op = expr[0]
        if op == "atom":
            return {Literal(expr[1], True)}
        elif op == "not":
            inner = expr[1]
            if isinstance(inner, tuple) and inner[0] == "atom":
                return {Literal(inner[1], False)}
            return None
        elif op == "or":
            left = self._collect_literals_from_or(expr[1])
            right = self._collect_literals_from_or(expr[2])
            if left is not None and right is not None:
                return left | right
        return None

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def _expr_str(self, expr: Expr) -> str:
        """Human-readable string for an expression."""
        if not isinstance(expr, tuple):
            return str(expr)
        op = expr[0]
        if op == "atom":
            return expr[1]
        elif op == "not":
            return f"¬({self._expr_str(expr[1])})"
        elif op == "and":
            return f"({self._expr_str(expr[1])} ∧ {self._expr_str(expr[2])})"
        elif op == "or":
            return f"({self._expr_str(expr[1])} ∨ {self._expr_str(expr[2])})"
        elif op == "implies":
            return f"({self._expr_str(expr[1])} → {self._expr_str(expr[2])})"
        elif op == "iff":
            return f"({self._expr_str(expr[1])} ↔ {self._expr_str(expr[2])})"
        return str(expr)


# ---------------------------------------------------------------------------
# Convenience: build a clause from propositional rule string
# ---------------------------------------------------------------------------

def make_implication_clauses(antecedent_symbol: str,
                              antecedent_positive: bool,
                              consequent_symbol: str,
                              consequent_positive: bool) -> List[Clause]:
    """
    Create CNF clauses for a simple implication:
        antecedent → consequent
    which becomes:
        ¬antecedent ∨ consequent

    Args:
        antecedent_symbol:  Name of antecedent proposition
        antecedent_positive: True if antecedent is positive (P → Q)
        consequent_symbol:  Name of consequent proposition
        consequent_positive: True if consequent is positive
    """
    ant_lit = Literal(antecedent_symbol, not antecedent_positive)  # negated
    con_lit = Literal(consequent_symbol, consequent_positive)
    return [Clause({ant_lit, con_lit})]


def make_conjunction_implication_clauses(
        antecedent_symbols: List[Tuple[str, bool]],
        consequent_symbol: str,
        consequent_positive: bool) -> List[Clause]:
    """
    Create CNF clause for:
        (A1 ∧ A2 ∧ ... ∧ An) → C
    which becomes:
        ¬A1 ∨ ¬A2 ∨ ... ∨ ¬An ∨ C
    """
    lits = set()
    for sym, pos in antecedent_symbols:
        lits.add(Literal(sym, not pos))  # negated antecedent literals
    lits.add(Literal(consequent_symbol, consequent_positive))
    return [Clause(lits)]
