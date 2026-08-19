"""
model_checker.py
================
Model Checking for Propositional Logic — the *semantic* half of the
inference engine, used as an independent cross-check on resolution.

Key definitions used here (Unit 3 terminology)
----------------------------------------------
MODEL
    A model is a possible world: a complete truth assignment to every
    proposition symbol under consideration.  With n symbols there are
    2^n possible models.

        MODEL 1: Safe_2_2 = True,  Hazard_2_2 = False, ...
        MODEL 2: Safe_2_2 = False, Hazard_2_2 = True,  ...

ENTAILMENT
    KB ⊨ α  iff  α is true in *every* model in which the KB is true.

    This module decides entailment by **enumerating models** (the truth
    table method) rather than by deriving anything.  Resolution decides
    the same question *syntactically*.  Agreement between the two is a
    practical demonstration of soundness and completeness.

SATISFIABILITY / VALIDITY
    A sentence is satisfiable if at least one model makes it true, and
    valid if every model makes it true.  :meth:`ModelChecker.check`
    reports the satisfying-model count, so both concepts are directly
    observable in the output.

Complexity
----------
O(2^n) in the number of symbols n — the reason this method is restricted
to the small *local* symbol set relevant to the current decision rather
than the rover's whole knowledge base.
"""

from __future__ import annotations

from itertools import product
from typing import Dict, List, Optional, Sequence, Set, Tuple

# A rule is (antecedents, consequent_symbol, consequent_positive) where
# antecedents is a sequence of (symbol, is_positive) pairs.  This mirrors
# the KnowledgeBase.Rule structure exactly, so the model checker and the
# resolution engine always reason about the *same* knowledge base.
RuleTuple = Tuple[Sequence[Tuple[str, bool]], str, bool]


class ModelChecker:
    """
    Truth-table model checker for propositional logic.

    Usage::

        checker = ModelChecker()
        result = checker.check(
            facts={"Safe_2_3"},
            negated_facts={"Hazard_2_3", "Radiation_2_3"},
            rules=[((("Safe_2_3", True), ("Hazard_2_3", False),
                     ("Radiation_2_3", False)), "CanMove_2_3", True)],
            query_symbol="CanMove_2_3",
            query_positive=True,
        )
        result["entailed"]  # True
    """

    def __init__(self, max_symbols: int = 12):
        """
        Args:
            max_symbols: Hard limit on symbols to enumerate.
                         2^12 = 4096 models — fast enough to run on every
                         decision without slowing the simulation down.
        """
        self.max_symbols = max_symbols
        self.models_enumerated = 0   # cumulative, for the metrics panel
        self.checks_performed = 0

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def check(self,
              facts: Set[str],
              negated_facts: Set[str],
              rules: List[RuleTuple],
              query_symbol: str,
              query_positive: bool,
              symbols: Optional[Set[str]] = None) -> dict:
        """
        Decide whether KB ⊨ (query_symbol = query_positive) by enumerating
        every model over ``symbols``.

        Args:
            facts:          Symbols asserted TRUE in the KB.
            negated_facts:  Symbols asserted FALSE in the KB.
            rules:          KB rules as :data:`RuleTuple` values.
            query_symbol:   Proposition being queried.
            query_positive: False queries the negative literal ¬symbol.
            symbols:        Symbols to enumerate.  If omitted, collected
                            from the KB and the query.

        Returns:
            A dict with ``entailed``, the model counts, whether the symbol
            set had to be truncated, whether the KB is consistent, and a
            formatted ``explanation`` string.
        """
        self.checks_performed += 1

        if symbols is None:
            symbols = self._collect_symbols(facts, negated_facts, rules,
                                            query_symbol)

        # Restrict enumeration to a tractable set.  The query symbol is
        # always retained; truncation is reported, never silent.
        sym_list, truncated = self._limit_symbols(symbols, query_symbol)

        # Only the parts of the KB that live inside the enumerated symbol
        # set can be checked.  Restricting the KB the same way keeps the
        # result meaningful instead of accidentally vacuous.
        sym_set = set(sym_list)
        local_facts = {s for s in facts if s in sym_set}
        local_negated = {s for s in negated_facts if s in sym_set}
        local_rules = [
            r for r in rules
            if r[1] in sym_set and all(s in sym_set for s, _ in r[0])
        ]

        models_checked = 0
        models_satisfying_kb = 0
        models_entailing_query = 0
        example_satisfying: Optional[Dict[str, bool]] = None
        counterexample: Optional[Dict[str, bool]] = None

        for bits in product([True, False], repeat=len(sym_list)):
            model: Dict[str, bool] = dict(zip(sym_list, bits))
            models_checked += 1

            if not self._model_satisfies_kb(model, local_facts,
                                            local_negated, local_rules):
                continue

            models_satisfying_kb += 1
            if example_satisfying is None:
                example_satisfying = dict(model)

            query_true = model.get(query_symbol, False)
            if not query_positive:
                query_true = not query_true

            if query_true:
                models_entailing_query += 1
            elif counterexample is None:
                # A model satisfying the KB but falsifying the query is a
                # direct witness that the KB does NOT entail the query.
                counterexample = dict(model)

        self.models_enumerated += models_checked

        kb_consistent = models_satisfying_kb > 0

        # Classical semantics: an inconsistent KB entails everything
        # (vacuous truth).  We report that explicitly rather than
        # silently returning False, so it can never be mistaken for a
        # genuine "not entailed" answer.
        if not kb_consistent:
            entailed = True
        else:
            entailed = models_entailing_query == models_satisfying_kb

        query_str = query_symbol if query_positive else f"¬{query_symbol}"

        return {
            "entailed": entailed,
            "models_checked": models_checked,
            "models_satisfying_kb": models_satisfying_kb,
            "models_entailing_query": models_entailing_query,
            "kb_consistent": kb_consistent,
            "truncated": truncated,
            "symbols_used": sym_list,
            "example_model": example_satisfying,
            "counterexample": counterexample,
            "explanation": self._build_explanation(
                query_str, entailed, models_checked, models_satisfying_kb,
                models_entailing_query, kb_consistent, truncated,
                example_satisfying, counterexample),
        }

    # ------------------------------------------------------------------
    # Satisfiability
    # ------------------------------------------------------------------

    def check_consistency(self,
                          facts: Set[str],
                          negated_facts: Set[str],
                          rules: List[RuleTuple],
                          symbols: Optional[Set[str]] = None) -> bool:
        """
        SATISFIABILITY test: is there at least one model satisfying the KB?

        Returns True if the KB is consistent (satisfiable).
        """
        if symbols is None:
            symbols = self._collect_symbols(facts, negated_facts, rules, None)
        sym_list, _ = self._limit_symbols(symbols, None)
        sym_set = set(sym_list)

        local_facts = {s for s in facts if s in sym_set}
        local_negated = {s for s in negated_facts if s in sym_set}
        local_rules = [
            r for r in rules
            if r[1] in sym_set and all(s in sym_set for s, _ in r[0])
        ]

        for bits in product([True, False], repeat=len(sym_list)):
            model = dict(zip(sym_list, bits))
            self.models_enumerated += 1
            if self._model_satisfies_kb(model, local_facts, local_negated,
                                        local_rules):
                return True
        return False

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _model_satisfies_kb(self,
                            model: Dict[str, bool],
                            facts: Set[str],
                            negated_facts: Set[str],
                            rules: List[RuleTuple]) -> bool:
        """
        Is this model a model *of the KB*?

        The KB is the conjunction of:
          * every positive fact       (symbol must be True)
          * every negative fact       (symbol must be False)
          * every rule  A1 ∧ … ∧ An → C
        """
        for sym in facts:
            if not model.get(sym, False):
                return False

        for sym in negated_facts:
            if model.get(sym, False):
                return False

        for antecedents, con_sym, con_pos in rules:
            # An implication is false only when the antecedent is true and
            # the consequent is false; otherwise it is satisfied.
            antecedent_true = True
            for sym, pos in antecedents:
                value = model.get(sym, False)
                if (value if pos else not value) is False:
                    antecedent_true = False
                    break
            if not antecedent_true:
                continue

            con_value = model.get(con_sym, False)
            if (con_value if con_pos else not con_value) is False:
                return False

        return True

    def _collect_symbols(self,
                         facts: Set[str],
                         negated_facts: Set[str],
                         rules: List[RuleTuple],
                         query_symbol: Optional[str]) -> Set[str]:
        """Gather every symbol mentioned by the KB and the query."""
        symbols: Set[str] = set(facts) | set(negated_facts)
        if query_symbol:
            symbols.add(query_symbol)
        for antecedents, con_sym, _ in rules:
            symbols.add(con_sym)
            for sym, _pos in antecedents:
                symbols.add(sym)
        return symbols

    def _limit_symbols(self,
                       symbols: Set[str],
                       query_symbol: Optional[str]) -> Tuple[List[str], bool]:
        """
        Cap the symbol set at ``max_symbols``, always keeping the query
        symbol.  Returns (symbol_list, was_truncated).
        """
        ordered = sorted(symbols)
        if len(ordered) <= self.max_symbols:
            return ordered, False

        kept: List[str] = []
        if query_symbol and query_symbol in symbols:
            kept.append(query_symbol)
        for sym in ordered:
            if len(kept) >= self.max_symbols:
                break
            if sym not in kept:
                kept.append(sym)
        return sorted(kept), True

    def _build_explanation(self,
                           query_str: str,
                           entailed: bool,
                           models_checked: int,
                           models_kb: int,
                           models_entailing: int,
                           kb_consistent: bool,
                           truncated: bool,
                           example: Optional[dict],
                           counterexample: Optional[dict]) -> str:
        """Format the model-checking result for the console and the UI."""
        lines = [
            f"MODEL CHECKING: KB ⊨ {query_str} ?",
            f"  Possible Models Checked:  {models_checked}",
            f"  Models Satisfying KB:     {models_kb}",
            f"  Models Entailing Query:   {models_entailing}",
            f"  Entailment:               {'YES' if entailed else 'NO'}",
        ]

        if not kb_consistent:
            lines.append("  WARNING: no model satisfies the KB — the KB is "
                         "INCONSISTENT, so it vacuously entails everything.")
        elif entailed:
            lines.append(f"  CONCLUSION: all {models_kb} KB-satisfying models "
                         f"make {query_str} true, therefore KB ⊨ {query_str}.")
        else:
            lines.append(f"  CONCLUSION: {models_kb - models_entailing} of "
                         f"{models_kb} KB-satisfying models make {query_str} "
                         f"false, therefore KB ⊭ {query_str}.")
            if counterexample:
                sample = self._format_model(counterexample, limit=4)
                lines.append(f"  Counter-example model: {sample}")

        if example and entailed and kb_consistent:
            lines.append(f"  Example satisfying model: "
                         f"{self._format_model(example, limit=4)}")

        if truncated:
            lines.append(f"  NOTE: symbol set truncated to "
                         f"{self.max_symbols} symbols to keep 2^n tractable.")

        return "\n".join(lines)

    @staticmethod
    def _format_model(model: Dict[str, bool], limit: int = 4) -> str:
        """Render a model as ``Sym=True, Sym2=False, …``."""
        items = list(model.items())[:limit]
        rendered = ", ".join(f"{k}={v}" for k, v in items)
        if len(model) > limit:
            rendered += ", …"
        return "{" + rendered + "}"

    def reset_counters(self) -> None:
        """Zero the cumulative operation counters (used on simulation reset)."""
        self.models_enumerated = 0
        self.checks_performed = 0
