"""Checks every explanation before and after rendering.

Per claim (one sentence), on the placeholder text and the real fact values:
  - numbers only through placeholders: no digits, number words, % or £; no unit typed after one
  - every key exists; an unavailable value only in a missing-data or caveat sentence
  - direction: each signed change must sit next to wording that matches its sign
    ("falls" for a saving, "rises" for an increase, no rise/fall for zero)
  - comparatives/superlatives only when citing a code-ranked derived.* fact
  - infeasible measures never recommended or credited; recommendations only from the plan;
    needs-verification measures described as needing a check; no "not suitable" about feasible ones
  - banned phrases (guarantees, financial advice, brands, causal claims) and "measured/actual
    usage" when the baseline was not measured
Coverage (whole explanation) returns structured gaps, so a missing piece can be filled from the
template instead of discarding everything. Post-render: scenario ID is current, nothing unfilled.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .claims import Claim, ExplanationDraft
from .facts_view import SAVING_KINDS, UP_KINDS, FactSheet
from .measures import MEASURE_ORDER, display_name, mentioned_measures
from .render import DIRECTION_FILTERS, PLACEHOLDER_RE, RenderedExplanation, placeholders, strip_placeholders

Mode = Literal["report", "whatif"]

GAS_KEY = "energy_results.change.gas_saving_kwh"
ELEC_KEY = "energy_results.change.grid_elec_saving_kwh"
CARBON_KEY = "carbon_results.saving_kg"
SCORE_KEY = "green_home_score.before.total"
CLASS_KEY = "green_home_score.before.class"
VALUE_KEYS = ("valuation.uplift_low_pct", "valuation.uplift_high_pct")
DIFF_GAS_KEY = "diff.gas_saving_kwh"
DIFF_ELEC_KEY = "diff.grid_elec_saving_kwh"
MEASURED_PROVENANCE = {"observed", "user-provided", "user_provided"}

_ALLOWED_DIGIT_TOKENS = re.compile(r"\bCO2e?\b|\bCO₂e?\b", re.IGNORECASE)
_NUMBER_WORDS = re.compile(
    r"\b(two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|"
    r"seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|hundreds|"
    r"thousand|thousands|million|millions|dozen|half|quarter|twice|percent|per cent|tonne|tonnes)\b",
    re.IGNORECASE,
)
_UNIT_AFTER = re.compile(r"\}\s*(kwh|kw|kg|tonnes?|%|per ?cent|pounds|gbp|m²|m2|points|/100|years?\b)", re.IGNORECASE)
_NEGATION = re.compile(r"\b(not|no|never|cannot|can't|isn't|aren't|won't|doesn't|without|nor|neither|rather than|"
                       r"instead of)\b[^.;]*$", re.IGNORECASE)
_BANNED = [
    (r"\bguarantee[sd]?\b", "guarantee"),
    (r"\bdefinitely\b", "definitely"),
    (r"\bcertainly\b", "certainly"),
    (r"\bprove[sn]?\b|\bproved\b", "proven"),
    (r"\bcaus(al|ed by the retrofit)\b", "causal claim"),
    (r"\bwill (increase|raise|boost|add to) (your|the) (home's |property's |house's )?(value|price)", "value promise"),
    (r"\bbest overall\b", "best overall"),
    (r"\binvest(ment|ing|or)?\b", "investment advice"),
    (r"\b(re)?mortgage\b|\bloan\b|\bborrow(ing)?\b|\bfinanc(e|ing|ial advice)\b", "financial advice"),
    (r"\bdigital twin\b", "digital twin"),
    (r"\b(daikin|mitsubishi|vaillant|worcester|bosch|viessmann|samsung|tesla|nest|hive|tado|octopus|"
     r"british gas|edf|e\.on|ovo)\b", "brand or supplier name"),
]
_BANNED_RES = [(re.compile(p, re.IGNORECASE), name) for p, name in _BANNED]
_MEASURED_RE = re.compile(
    r"\b(your )?(actual|real|measured|metered)\b[^.]{0,30}\b(use|usage|consumption|readings?|bills?)\b|"
    r"\bmeter readings?\b",
    re.IGNORECASE,
)
_COMPARATIVE_RE = re.compile(
    r"\b(more|less|fewer|greater|bigger|larger|smaller|higher|lower)\s+than\b|"
    r"\b(most|least|biggest|largest|smallest|highest|lowest|best|worst|greatest|weakest|strongest)\b",
    re.IGNORECASE,
)
_COMPARATIVE_OK = re.compile(
    r"\blowest cost\b|\blargest carbon saving\b|\bbest carbon (saving )?per pound\b|\bat (least|most)\b|"
    r"\b(the )?most of\b",
    re.IGNORECASE,
)
INCREASE_WORDS = re.compile(r"\b(ris(e|es|ing|en)|rose|raise[sd]?|raising|increas(e|es|ed|ing)|go(es)? up|going up|"
                            r"went up|higher|grow(s|ing|n)?|more|climb(s|ing|ed)?|extra|additional|add(s|ed|ing)?|"
                            r"up)\b", re.IGNORECASE)
REDUCTION_WORDS = re.compile(r"\b(fall(s|ing|en)?|fell|drop(s|ped|ping)?|reduc(e|es|ed|ing|tion|tions)|cut(s|ting)?|"
                             r"sav(e|es|ed|ing|ings)|lower(s|ed|ing)?|less|decreas(e|es|ed|ing)|down|shrink(s|ing)?|"
                             r"declin(e|es|ed|ing)|avoid(s|ed|ing)?|fewer)\b", re.IGNORECASE)
RECOMMEND_WORDS = re.compile(r"\b(install|installing|add|adding|fit|fitting|upgrade|upgrading|consider|should|"
                             r"recommend|recommended|get|choose)\b", re.IGNORECASE)
VERIFY_WORDS = re.compile(r"\b(verif\w*|check\w*|confirm\w*|survey\w*|assess\w*)\b", re.IGNORECASE)
UNSUITABLE_WORDS = re.compile(
    r"\b(not suitable|unsuitable|isn't suitable|not possible|not applicable|doesn't apply|does not apply|"
    r"cannot|can't|ruled out|not an option|not added|wasn't added|was not added|not be added|isn't possible|"
    r"needs? (checking|to be checked|verification|a survey)|must be checked|check(ed)? first|"
    r"requires? (checking|a check|verification|a survey))\b", re.IGNORECASE)
HARD_UNSUITABLE_WORDS = re.compile(
    r"\b(not suitable|unsuitable|isn't suitable|is not suitable|not possible|isn't possible|ruled out|not an option|"
    r"cannot be (installed|fitted|added)|can't be (installed|fitted|added)|does not apply|doesn't apply|not applicable)\b",
    re.IGNORECASE)
MISSING_WORDS = re.compile(
    r"\b(not (estimated|available|known|recorded|calculated)|unavailable|unknown|missing|no data|"
    r"isn't (available|known|recorded)|cannot be (estimated|calculated)|can't be (estimated|calculated)|"
    r"insufficient|not been (estimated|calculated|recorded))\b", re.IGNORECASE)
NOT_ADDITIVE_RE = re.compile(r"\bnot (simply|just|directly) (added|summed)|\bnot (additive|cumulative)\b|"
                             r"\b(don't|do not|won't|will not|cannot|can't) (simply |just )?(add|sum) up\b|"
                             r"\bnot (simply |just )?the sum of\b", re.IGNORECASE)
INTERACT_RE = re.compile(r"\binteract(s|ing|ion|ions)?\b|\bcombined effect\b", re.IGNORECASE)
# --- Decision-context rules (product concept: permissions, not-assessed topics, budget, privacy) ---------------
PERMISSION_CLAIM_RE = re.compile(
    r"\b(permitted|allowed|approved)\b|\bno (permission|consent|approval) (is )?(needed|required)\b|"
    r"\b(don't|do not|doesn't|does not) need (any )?(permission|consent|approval)\b|"
    r"\bcan (just |simply )?(go ahead|install|fit|start)\b", re.IGNORECASE)
CONSENT_WORDS = re.compile(r"\b(landlord|consent|permission|approval|agree\w*|ask\w*|check\w*|managing agent|"
                           r"building owner|freeholder|planning|surveyor)\b", re.IGNORECASE)
# Bills, payback and an illustrative loan are engine outputs (D26, D27) and may be cited by placeholder; "pays for
# itself", break-even promises and climate fit are still not assessed.
NOT_ASSESSED_RE = re.compile(
    r"\bpay(s|ing)? (for )?itself\b|\bbreak[- ]even\b|\bsave(s)? you money\b|"
    r"\b(suits|suited to|right for) (the|your) (local )?climate\b",
    re.IGNORECASE)
LOAN_KEYS = ("cost_results.loan_monthly_repayment_gbp", "cost_results.loan_apr_pct", "cost_results.loan_term_years")
_ILLUSTRATIVE_RE = re.compile(r"\billustrat", re.IGNORECASE)
BILL_KEY = "cost_results.bill_saving_gbp"
EPC_KEY = "epc_change.sap_change"
BUDGET_RE = re.compile(r"\b(within|fits|inside) (your |the )?budget\b|\baffordable\b", re.IGNORECASE)
PRIVACY_RE = re.compile(
    r"\byou (can't|cannot|can not|couldn't|could not) afford\b|"
    r"\byour (income|salary|job|employment|wages|savings|finances|credit)\b|\b(low|limited)[- ]income\b|"
    r"\bfinancially (vulnerable|struggling|stretched)\b", re.IGNORECASE)
_ESTIMATE_RE = re.compile(r"\bestimat", re.IGNORECASE)
_INDICATIVE_RE = re.compile(r"\bindicative\b", re.IGNORECASE)
_RANKING_KEYS = ("derived.score_drags", "derived.issues", "derived.largest_gas_saving_measure", "derived.priority_order")
_CLAUSE_BOUNDARY = re.compile(r"[,;:()]|\s[-–—]\s|\b(?:while|whereas|but|although|though|however)\b", re.IGNORECASE)


@dataclass(frozen=True)
class CheckError:
    code: str
    message: str
    claim: int | None = None  # index into draft.claims, None for whole-explanation errors

    def __str__(self) -> str:
        where = f"claim {self.claim}: " if self.claim is not None else ""
        return f"[{self.code}] {where}{self.message}"


@dataclass(frozen=True)
class Gap:
    """A required piece of content that is missing; `section` says where a fill belongs."""

    id: str
    section: str
    message: str
    code: str = "COVERAGE"


def _not_negated(text: str, start: int) -> bool:
    return not _NEGATION.search(text[max(0, start - 40):start])


def claim_keys(c: Claim) -> set[str]:
    return set(c.keys) | {k for k, _ in placeholders(c.text)}


def claim_measures(c: Claim, sheet: FactSheet) -> set[str]:
    """Measures a claim refers to: declared, named in the text, or reached through a placeholder."""
    out = set(c.measures) | mentioned_measures(strip_placeholders(c.text))
    names = {display_name(m): m for m in MEASURE_ORDER}
    for k in claim_keys(c):
        parts = k.split(".")
        if parts[0] == "feasibility" and len(parts) == 3:
            out.add(parts[1])
        elif k == "derived.plan_order":
            out |= set(sheet.selected_measures)
        elif k in ("diff.added", "diff.removed", "diff.blocked", "diff.conditional"):
            out |= {names[v] for v in (sheet.value(k) or []) if v in names}
        elif parts[:2] == ["energy_results", "per_measure"] and len(parts) == 4:
            name = sheet.value(f"energy_results.per_measure.{parts[2]}.measure")
            if name in names:
                out.add(names[name])
        elif parts[0] in ("standalone", "ranking") and len(parts) == 3:
            name = sheet.value(f"{parts[0]}.{parts[1]}.measure")
            if name in names:
                out.add(names[name])
        elif k == "derived.priority_order":
            out |= {names[n] for n in names if n in str(sheet.value(k) or "")}
    return out & set(MEASURE_ORDER)


def _direction_words(text: str) -> list[tuple[int, int, str]]:
    """(start, end, 'up'|'down') for every non-negated direction word."""
    out = []
    for rx, d in ((INCREASE_WORDS, "up"), (REDUCTION_WORDS, "down")):
        out += [(m.start(), m.end(), d) for m in rx.finditer(text) if _not_negated(text, m.start())]
    return out


def _direction_errors(c: Claim, sheet: FactSheet) -> list[str]:
    """Each direction word belongs to the nearest signed placeholder in its clause; that word must match
    the value's sign. A zero value must have no direction word of its own."""
    text = c.text
    plain = PLACEHOLDER_RE.sub(lambda m: "§" * len(m.group(0)), text)  # keep offsets, hide words inside keys
    signed = []
    for m in PLACEHOLDER_RE.finditer(text):
        f = sheet.get(m.group(1))
        if f is not None and f.available and (f.kind in SAVING_KINDS or f.kind in UP_KINDS):
            signed.append((m.start(), m.end(), f, m.group(2) in DIRECTION_FILTERS))
    if not signed:
        return []
    cuts = [0] + [m.end() for m in _CLAUSE_BOUNDARY.finditer(plain)] + [len(plain) + 1]

    def clause_id(pos: int) -> int:
        return max(i for i, cut in enumerate(cuts) if cut <= pos)

    owned: dict[int, list[tuple[int, str]]] = {i: [] for i in range(len(signed))}
    for ws, we, d in _direction_words(plain):
        cands = [(min(abs(ws - pe), abs(we - ps)), i) for i, (ps, pe, _, _) in enumerate(signed)
                 if clause_id(ps) == clause_id(ws)]
        if cands:
            dist, i = min(cands)
            owned[i].append((dist, d))
    errs = []
    for i, (ps, pe, f, carries_direction) in enumerate(signed):
        v = float(f.value)
        words = sorted(owned[i])
        if carries_direction:  # {key|change} renders the direction itself; only contradicting wording is an error
            want = ("down" if v > 0 else "up") if f.kind in SAVING_KINDS else ("up" if v > 0 else "down")
            if words and v != 0 and words[0][1] != want:
                errs.append(f"{f.key} goes {want}, but the wording next to it says it goes {words[0][1]}")
            continue
        if not words and len(signed) == 1 and v != 0:  # one change in the sentence: look across clauses
            words = sorted((min(abs(ws - pe), abs(we - ps)), d) for ws, we, d in _direction_words(plain))
        found = words[0][1] if words else None
        if v == 0:
            if found is not None:
                errs.append(f"{f.key} is zero (no change) but the wording says it goes {found}")
            continue
        want = ("down" if v > 0 else "up") if f.kind in SAVING_KINDS else ("up" if v > 0 else "down")
        if found is None:
            errs.append(f"{f.key} needs wording that says which way it changes ({'falls' if want == 'down' else 'rises'})")
        elif found != want:
            errs.append(f"{f.key} goes {want}, but the wording next to it says it goes {found}")
    return errs


_SECTION_FACTS = {
    "value": ("valuation.uplift_",),
    "carbon": ("carbon_results.saving_kg",),
    "energy": ("energy_results.change.", "energy_results.per_measure."),
    "cost": ("cost_results.",),
}


def _false_missing(c: Claim, sheet: FactSheet) -> bool:
    """A 'not estimated / not available' sentence in a section whose figures all exist is false."""
    prefixes = _SECTION_FACTS.get(c.section)
    if c.type != "missing_data" or not prefixes:
        return False
    keys = claim_keys(c)
    if any((f := sheet.get(k)) is not None and (not f.available or k.endswith(".reason")) for k in keys):
        return False
    section_facts = [f for k, f in sheet.facts.items() if k.startswith(prefixes) and f.numeric]
    return bool(section_facts) and all(f.available for f in section_facts)


def check_claim(i: int, c: Claim, sheet: FactSheet) -> list[CheckError]:
    errs: list[CheckError] = []

    def err(code: str, msg: str) -> None:
        errs.append(CheckError(code, msg, i))

    text = c.text
    if not text.strip():
        err("EMPTY", "claim text is empty")
        return errs

    # --- Numbers only through placeholders --------------------------------
    bare = _ALLOWED_DIGIT_TOKENS.sub(" ", strip_placeholders(text))
    if re.search(r"\d", bare):
        err("DIGIT", f"digit outside a placeholder in: {text!r}")
    if m := _NUMBER_WORDS.search(bare):
        err("NUMBER_WORD", f"number word {m.group(0)!r}; use a placeholder instead")
    if re.search(r"[%£$€]", bare):
        err("SYMBOL", "%, £ or other currency symbol outside a placeholder; the renderer adds units")
    if "{" in bare or "}" in bare:
        err("BRACES", "malformed placeholder; use {dotted.key}")
    if m := _UNIT_AFTER.search(text):
        err("UNIT", f"unit {m.group(1)!r} typed after a placeholder; the renderer adds units")

    # --- Keys exist; unavailable values are not presented as numbers --------
    keys = claim_keys(c)
    for k in sorted(keys):
        if sheet.get(k) is None:
            err("UNKNOWN_KEY", f"fact key {k!r} does not exist")
    for k, _ in placeholders(text):
        f = sheet.get(k)
        if f and not f.available and c.type not in ("missing_data", "caveat"):
            err("UNAVAILABLE", f"{k} is {f.status}; say it is not available or not estimated, and why")

    # --- Direction of every signed change ------------------------------------
    for msg in _direction_errors(c, sheet):
        err("DIRECTION", msg)
    # Per-measure savings come from a sequential simulation, so they DO add up to the package total.
    if NOT_ADDITIVE_RE.search(text):
        err("INTERACTION", "the per-measure savings add up to the total (each is worked out on the energy left by "
                           "the previous measures); do not say they are not simply added")
    if INTERACT_RE.search(text) and len(sheet.selected_measures) < 2 and c.section != "whatif":
        err("INTERACTION", "there is only one selected measure, so there is no interaction to describe")
    if _false_missing(c, sheet):
        err("CONTRADICTION", f"says something is not estimated, but every {c.section} figure is available")

    # --- Comparisons only through code-ranked facts --------------------------
    plain = _COMPARATIVE_OK.sub(" ", strip_placeholders(text))
    if _COMPARATIVE_RE.search(plain) and not any(k in keys for k in _RANKING_KEYS):
        err("COMPARATIVE", "comparative or superlative wording is only allowed when citing a code-ranked "
                           "derived.* fact (derived.score_drags, derived.largest_gas_saving_measure)")

    # --- Measures and feasibility ------------------------------------------
    measures = claim_measures(c, sheet)
    infeasible = {m for m, f in sheet.feasibility.items() if f.state == "infeasible"}
    needs_check = {m for m, f in sheet.feasibility.items() if f.state == "needs_verification"}
    recommending = bool(RECOMMEND_WORDS.search(text))
    bad = measures & infeasible
    if bad and c.type in ("recommendation", "saving", "increase"):
        err("INFEASIBLE", f"recommends or credits savings to infeasible measure(s): {sorted(bad)}")
    elif bad and c.type != "feasibility" and recommending:
        err("INFEASIBLE", f"suggests infeasible measure(s) {sorted(bad)}; only explain why they are not suitable")
    if c.section != "whatif" and c.type != "feasibility" and (c.type == "recommendation" or recommending):
        not_selected = measures - set(sheet.selected_measures) - infeasible
        if not_selected:
            err("NOT_IN_PLAN", f"recommends measure(s) not in the selected plan: {sorted(not_selected)}")
    for m_ in re.finditer(r"\b(by|of|is|are|was|were)\s+\{[a-z0-9_.]+\|changes?\}", text, re.IGNORECASE):
        err("FILTER", f"{{key|change}} already says 'fall by X' / 'rise by X'; do not put '{m_.group(1)}' before it")
    for k, _ in placeholders(text):  # a direction filter only makes sense on a change
        f = sheet.get(k)
        if f is not None and f.available and not f.signed and re.search(r"\{" + re.escape(k) + r"\|changes?\}", text):
            err("FILTER", f"{{{k}|change}} is only for changes; {k} is not a change")
    # Text facts a sentence cites count as its wording (derived.plan_order carries "needs checking" itself).
    cited_text = " ".join(str(f.value) for k in keys if (f := sheet.get(k)) is not None and f.kind in ("text", "text_list")
                          and f.available)
    if (c.type == "recommendation" or recommending) and measures & needs_check and c.type != "feasibility" \
            and not VERIFY_WORDS.search(text + " " + cited_text):
        err("VERIFY", "a measure that needs verification must be described as needing a check first")
    hard_no = HARD_UNSUITABLE_WORDS.search(text)
    if measures & needs_check and hard_no and _not_negated(text, hard_no.start()) \
            and not VERIFY_WORDS.search(text + " " + cited_text):
        err("NEEDS_CHECK", f"{sorted(measures & needs_check)} need checking first; they are not unsuitable: say they "
                           "need a check, and why")
    if c.type == "feasibility":
        # Only when the sentence is about feasible measures alone: "solid wall insulation is not suitable because
        # the walls are cavity walls" names cavity walls as the reason, not as an unsuitable measure.
        feasible_named = {m for m in measures if sheet.feasibility.get(m) and sheet.feasibility[m].state == "feasible"}
        if feasible_named and not (measures & (infeasible | needs_check)) and UNSUITABLE_WORDS.search(text):
            err("FEASIBILITY", f"says feasible measure(s) are unsuitable: {sorted(feasible_named)}")

    # --- Decision context: permissions, not-assessed topics, budget, privacy ----------------------------
    gated = {m for m in measures if sheet.permissions.get(m) in ("conditional", "unverified")}
    claim_m = PERMISSION_CLAIM_RE.search(text)
    if claim_m and _not_negated(text, claim_m.start()) and (gated or sheet.role == "tenant"):
        err("PERMISSION", f"{claim_m.group(0)!r}: permission is not verified here; say who must agree first")
    if sheet.role == "tenant" and c.type != "feasibility" and (c.type == "recommendation" or recommending) \
            and (measures & {m for m, s in sheet.permissions.items() if s == "conditional"}) \
            and not CONSENT_WORDS.search(text + " " + cited_text):
        err("PERMISSION", "a tenant needs the landlord's consent for this; say so")
    for rx, code, msg in ((NOT_ASSESSED_RE, "NOT_ASSESSED", "do not promise that measures pay for themselves; climate "
                                                            "fit is not assessed here"),
                          (PRIVACY_RE, "PRIVACY", "do not describe the user's finances, job or ability to afford")):
        m_ = rx.search(text)
        if m_ and _not_negated(text, m_.start()):
            err(code, f"{m_.group(0)!r}: {msg}")
    b_ = BUDGET_RE.search(text)
    if b_ and _not_negated(text, b_.start()) and sheet.value("decision.budget_fit_status") != "within":
        err("BUDGET", f"{b_.group(0)!r}: only say this when the plan's cost is within the stated budget")

    # --- Banned phrases and provenance wording -----------------------------
    # The engine's illustrative loan (D27) may be described, by placeholder and labelled illustrative; any other
    # lending, mortgage or investment wording is still banned.
    loan_ok = bool(keys & set(LOAN_KEYS)) and bool(_ILLUSTRATIVE_RE.search(text))
    for rx, name in _BANNED_RES:
        for m in rx.finditer(text):
            if name == "financial advice" and loan_ok and m.group(0).lower() == "loan":
                continue
            if _not_negated(text, m.start()):
                err("BANNED", f"banned phrase ({name}): {m.group(0)!r}")
                break
    if not (sheet.baseline_provenance & MEASURED_PROVENANCE):
        for m in _MEASURED_RE.finditer(text):
            if _not_negated(text, m.start()):
                err("PROVENANCE", f"says {m.group(0)!r} but the baseline is not a measured reading")
                break
    return errs


def _section_text(draft: ExplanationDraft, section: str) -> str:
    return " ".join(c.text for c in draft.claims if c.section == section)


def _keys_in(draft: ExplanationDraft, section: str | None = None) -> set[str]:
    out: set[str] = set()
    for c in draft.claims:
        if section is None or c.section == section:
            out |= claim_keys(c)
    return out


def coverage_gaps(draft: ExplanationDraft, sheet: FactSheet, mode: Mode = "report",
                  must_explain: set[str] | None = None) -> list[Gap]:
    gaps: list[Gap] = []
    sections = {c.section for c in draft.claims}
    all_keys = _keys_in(draft)
    explain_section = "whatif" if mode == "whatif" else "not_suitable"

    def need(cond: bool, gid: str, section: str, msg: str, code: str = "COVERAGE") -> None:
        if not cond:
            gaps.append(Gap(gid, section, msg, code))

    # Report: every infeasible / needs-verification measure. What-if: the ones the user asked for.
    if must_explain is None:
        must_explain = {m for m, f in sheet.feasibility.items() if f.state in ("infeasible", "needs_verification")}
    for m in sorted(must_explain):
        covered = any(c.type == "feasibility" and m in claim_measures(c, sheet) for c in draft.claims)
        need(covered, f"feasibility:{m}", explain_section, f"say why {display_name(m)} is not suitable or needs checking")

    if mode == "whatif":
        need("whatif" in sections, "whatif", "whatif", "a what-if answer needs a 'whatif' section")
        for key, fuel in ((DIFF_GAS_KEY, "gas"), (DIFF_ELEC_KEY, "grid electricity")):
            f = sheet.get(key)
            if f is not None and (sheet.value("diff.added") or sheet.value("diff.removed")):
                need(key in all_keys, f"diff:{key}", "whatif", f"report the {fuel} change versus the previous plan")
        return gaps

    for k in sheet.warning_keys:
        need(k in all_keys, f"warning:{k}", "caveats", f"pass on warning {{{k}}}")

    # Decision context: every code-written context fact reaches the reader in its section.
    for key, section in (("decision.situation", "fit"), ("decision.plan_choice", "fit"),
                         ("decision.who_benefits", "fit"), ("decision.budget_fit", "fit"),
                         ("decision.excluded", "fit"), ("decision.changes_summary", "fit"),
                         ("decision.next_steps", "next_steps"),
                         ("decision.completed_note", "caveats"), ("decision.not_assessed", "caveats")):
        if sheet.get(key) is not None and sheet.get(key).available:
            need(key in _keys_in(draft, section), f"context:{key}", section, f"{section} section must cite {{{key}}}")

    score_keys = _keys_in(draft, "score")
    need(SCORE_KEY in score_keys, "score_total", "score", f"score section must use {{{SCORE_KEY}}}")
    need(CLASS_KEY in score_keys, "score_class", "score", f"score section must use {{{CLASS_KEY}}}")
    if sheet.missing_inputs and sheet.get("derived.missing_inputs") is not None:
        need("derived.missing_inputs" in all_keys, "missing_inputs", "caveats",
             "say which details about the home are missing ({derived.missing_inputs})")

    if sheet.selected_measures:
        plan_measures: set[str] = set()
        for c in draft.claims:
            if c.section == "plan":
                plan_measures |= claim_measures(c, sheet)
        missing = [m for m in sheet.selected_measures if m not in plan_measures]
        need(not missing, "plan", "plan", f"plan section must name every selected measure, missing: {missing}")

        energy_keys = _keys_in(draft, "energy")
        for key, fuel in ((GAS_KEY, "gas"), (ELEC_KEY, "electricity")):
            if sheet.get(key) is not None:
                need(key in energy_keys, f"fuel:{key}", "energy", f"energy section must report the {fuel} change "
                                                                  f"({{{key}}})")
        need(bool(_ESTIMATE_RE.search(_section_text(draft, "energy"))), "energy_estimate", "energy",
             "energy section must call the savings estimates", "WORDING")
        if sheet.get(CARBON_KEY) is not None:
            need(CARBON_KEY in _keys_in(draft, "carbon"), "carbon", "carbon", f"carbon section must use {{{CARBON_KEY}}}")
            need(bool(_ESTIMATE_RE.search(_section_text(draft, "carbon"))), "carbon_estimate", "carbon",
                 "carbon section must call the figure an estimate", "WORDING")

    if sheet.selected_measures:
        bill = sheet.get(BILL_KEY)
        if bill is not None and bill.available:
            need(BILL_KEY in _keys_in(draft, "cost"), "bills", "cost", f"cost section must give the bill change "
                                                                     f"({{{BILL_KEY}}})")
        epc = sheet.get(EPC_KEY)
        if epc is not None:
            need(EPC_KEY in _keys_in(draft, "score"), "epc_change", "score",
                 "score section must give the modelled EPC change (or say why it is not estimated)")
        if "heat_pump" in sheet.estimated_measures:
            need(bool(re.search(r"\b(EPC|SAP)\b", _section_text(draft, "caveats"))), "hp_epc", "caveats",
                 "say that a heat pump can lower the EPC (SAP) rating while cutting carbon", "WORDING")
    need(bool(_ESTIMATE_RE.search(_section_text(draft, "caveats"))) or not draft.claims, "estimates_caveat",
         "caveats", "say that the figures are estimates, not guarantees", "WORDING")
    if sheet.baseline_provenance and not (sheet.baseline_provenance & MEASURED_PROVENANCE):
        need(bool(re.search(r"\b(benchmark|typical|not a meter|meter reading)", _section_text(draft, "caveats"),
                            re.IGNORECASE)), "benchmark_caveat", "caveats",
             "say that the starting energy use is a benchmark, not this home's meter", "WORDING")

    value_available = all(sheet.get(k) is not None and sheet.get(k).available for k in VALUE_KEYS)
    if value_available:
        need(bool(re.search(r"\bassociat", _section_text(draft, "value"), re.IGNORECASE)), "value_association",
             "value", "say the value change is an association, not a causal effect", "WORDING")
        need(all(k in _keys_in(draft, "value") for k in VALUE_KEYS), "value", "value",
             "value section must give the indicative range")
        need(bool(_INDICATIVE_RE.search(_section_text(draft, "value"))), "value_indicative", "value",
             "value must be described as indicative", "WORDING")
    else:
        need(any(c.section == "value" and c.type == "missing_data" for c in draft.claims), "value_missing", "value",
             "value is not estimated: say so and why")
    return gaps


def check(draft: ExplanationDraft, sheet: FactSheet, mode: Mode = "report",
          must_explain: set[str] | None = None) -> list[CheckError]:
    """Pre-render checks. Empty list = safe to render.

    must_explain: measures that need a feasibility sentence (default in report mode: every infeasible or
    needs-verification measure; in what-if mode pass the blocked / conditional measures the user asked for).
    """
    if not draft.claims:
        return [CheckError("EMPTY", "no claims")]
    errs: list[CheckError] = []
    for i, c in enumerate(draft.claims):
        errs.extend(check_claim(i, c, sheet))
    errs.extend(CheckError(g.code, g.message) for g in coverage_gaps(draft, sheet, mode, must_explain))
    return errs


def check_rendered(rendered: RenderedExplanation, current_scenario_id: str) -> list[CheckError]:
    """Post-render checks: right scenario, nothing left unfilled."""
    errs: list[CheckError] = []
    if rendered.scenario_id != current_scenario_id:
        errs.append(CheckError("STALE", f"explanation is for scenario {rendered.scenario_id}, "
                                        f"current is {current_scenario_id}"))
    text = rendered.all_text
    if PLACEHOLDER_RE.search(text) or "{" in text or "}" in text:
        errs.append(CheckError("UNFILLED", "placeholder left in rendered text"))
    spans = [sp for s in rendered.sections for c in s.claims for sp in c.spans]
    if any(re.search(r"\b(None|nan|NaN|null)\b", sp.display) for sp in spans):
        errs.append(CheckError("UNFILLED", "raw None/nan in a rendered value"))
    if re.search(r"(kWh/year|CO2e/year|%|m²|years)\s*(kWh|kg|tonnes|%|per cent|years?)\b", text):
        errs.append(CheckError("UNIT", "duplicated unit in rendered text"))
    return errs


def banned_phrases(text: str) -> list[str]:
    """Non-negated banned phrases in any text (used by the evaluation on rendered output)."""
    found = []
    for rx, name in _BANNED_RES:
        for m in rx.finditer(text):
            if _not_negated(text, m.start()):
                found.append(f"{name}: {m.group(0)}")
                break
    return found
