"""Pydantic data contracts (brief section 7).

``ExceptionRecord`` and ``Rules`` follow the brief field for field. Additive fields are marked
``# ADDITION`` and listed in docs/ASSUMPTIONS.md; nothing from the brief is renamed or removed.
These models are the source of truth for the generated TypeScript types (``make types``).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

ExceptionType = Literal[
    "pulse_gap",
    "pulse_missing_payment",
    "pulse_spike",
    "pulse_missing_batch",
    "label_mismatch",
    "sentinel_outlier",
    "sentinel_two_currencies",
    "sentinel_currency_code",
    "sentinel_reversal",
    "typo",
    "miner_cluster",
    # ADDITION (review of 22 Nov 2026, fix 4, docs/ASSUMPTIONS.md A46): a netting group at or
    # above materiality with no Pulse finding, and a full balance on the wrong side.
    "open_balance",
    "wrong_side_balance",
]
Workgroup = Literal["Payroll", "Fixed assets"]
Erp = Literal["P20", "BPP"]
ExceptionClass = Literal["List component", "Timing item", "Required Adjustment Item"]
Status = Literal["new", "explained", "dismissed", "escalated"]
VerifierResult = Literal["passed", "failed", "not_run"]
# ADDITION (#21, docs/ASSUMPTIONS.md A25): the inbox tab a finding sits on. "attention" is the
# default view (at or above materiality, or a type in Rules.inbox_always_types).
InboxView = Literal["attention", "prompts", "repeats", "other"]


class TypoCheck(BaseModel):
    """ADDITION (#30, A6): the assistant's reading of a spelling prompt.

    Advisory only: it never changes the record's id, score, status, class or exposure, and a
    "not_a_typo" verdict never hides the prompt. The controller can allow-list the word.
    """

    verdict: Literal["typo", "not_a_typo"]
    suggestion: str | None = None  # a word from the run's own dictionary, or None


class ExceptionRecord(BaseModel):
    """One finding. Every engine emits this shape (brief section 7)."""

    id: str
    run_id: str
    type: ExceptionType
    workgroup: Workgroup
    erp: Erp
    entity: str
    account: str
    account_name: str
    title: str
    exposure_eur: float
    facts: dict[str, float | str]
    evidence: list[str]
    first_signal: date
    today_detection: date | None
    lead_days: int | None
    expected_by: date | None
    suggested_class: ExceptionClass | None
    score: float
    score_breakdown: dict[str, float]
    ai_comment: str | None
    verifier: VerifierResult
    status: Status
    decision_reason: str | None
    # ADDITION: the class the person chose (the brief says the person decides the class).
    decided_class: ExceptionClass | None = None
    # ADDITION: the preparer's edited comment, kept separate from the AI draft for audit.
    edited_comment: str | None = None
    # ADDITION (#21, A25): the inbox tab, set by the pipeline from the run's Rules.
    inbox_view: InboxView | None = None
    # ADDITION (#30, A6): the assistant's check of a spelling prompt; None when no model ran.
    ai_check: TypoCheck | None = None


class PaymentProfile(BaseModel):
    """How one account accrues and pays (brief section 8, Pulse table)."""

    erp: Erp
    entity: str
    account: str
    label: str
    batch_text_pattern: str = Field(
        description="Regex on the line Text; group 'period' holds the period label"
    )
    batch_users: list[str] = Field(default_factory=list, description="User Name filter, if any")
    batch_doc_types: list[str] = Field(default_factory=list)
    batch_group: Literal["period", "document"] = "period"
    min_batch_eur: float = 0.0
    payment_unit: Literal["document", "line"] = "document"
    payment_doc_types: list[str] = Field(default_factory=list)
    min_payment_eur: float = 0.0
    max_units: int = 2
    window_anchor: Literal["period_end", "accrual_date"] = "period_end"
    window_start_days: int = -5
    window_end_days: int = 70
    tolerance_pct: float = 0.02
    # ASSUMPTION: match preference. True = fewest payment units, then smallest difference,
    # then shortest lag (reproduces the C192 Expected values); False = the brief's literal
    # "smallest difference, then shortest lag" (reproduces the C242 Expected values).
    # Confirmed in #4 (docs/ASSUMPTIONS.md A12).
    prefer_fewest_units: bool = False

    @property
    def key(self) -> str:
        """Stable account key, e.g. ``P20/C192/279006``."""
        return f"{self.erp}/{self.entity}/{self.account}"


def default_payment_profiles() -> list[PaymentProfile]:
    """The two profiles the brief specifies (C192 social security, C242 accrued payroll)."""
    return [
        PaymentProfile(
            erp="P20",
            entity="C192",
            account="279006",
            label="C192 social security",
            batch_text_pattern=r"^Payroll(?P<period>\d{6})$",
            batch_group="period",
            min_batch_eur=50_000,
            payment_unit="document",
            min_payment_eur=1_000,
            max_units=2,
            window_anchor="period_end",
            window_start_days=-5,
            window_end_days=70,
            tolerance_pct=0.02,
            prefer_fewest_units=True,
        ),
        PaymentProfile(
            erp="BPP",
            entity="C242",
            account="34900015",
            label="C242 accrued payroll",
            batch_text_pattern=r"(?i)^Aus?zahl\.\s*Rente_(?P<period>\d{2}\.\d{4})",
            batch_users=["BOT_UPLOAD_002"],
            batch_doc_types=["GX"],
            batch_group="document",
            payment_unit="line",
            payment_doc_types=["TX"],
            max_units=5,
            window_anchor="accrual_date",
            window_start_days=0,
            window_end_days=14,
            tolerance_pct=0.01,
        ),
    ]


Side = Literal["debit", "credit"]


class NormalSide(BaseModel):
    """ADDITION (review of 22 Nov 2026, docs/ASSUMPTIONS.md A43): the side an account's balance
    normally sits on, for every account of one ERP whose number starts with ``account_prefix``.
    The longest matching prefix wins; an account no entry matches has an unknown side."""

    erp: Erp
    account_prefix: str = Field(min_length=1)
    side: Side


def default_normal_sides() -> list[NormalSide]:
    """ASSUMPTION (A43): the chart-of-accounts ranges, pending mentor question 10.

    P20: 1xxxxx assets (debit), 2xxxxx liabilities (credit). BPP: 1x and 2x assets (debit),
    3x and 4x liabilities (credit). Fits every payroll account and both Fixed assets accounts.
    """
    return [
        NormalSide(erp="P20", account_prefix="1", side="debit"),
        NormalSide(erp="P20", account_prefix="2", side="credit"),
        NormalSide(erp="BPP", account_prefix="1", side="debit"),
        NormalSide(erp="BPP", account_prefix="2", side="debit"),
        NormalSide(erp="BPP", account_prefix="3", side="credit"),
        NormalSide(erp="BPP", account_prefix="4", side="credit"),
    ]


class Rules(BaseModel):
    """Controller-set parameters. Brief fields first; every engine threshold lives here."""

    materiality_eur: float = 500_000
    tolerance_pct: float = 0.01  # a batch matches within max(1% of batch, tolerance_eur)
    tolerance_eur: float = 1_000
    grace_days: int = 15
    outlier_multiple: float = 1_000
    weights: dict[str, int] = {
        "exposure": 40,
        "days_past_expected": 20,
        "penalty_account": 20,
        "error_type": 10,
        "repeats": 10,
    }
    # ADDITION (brief section 8, "payment profile ... is part of the Rules").
    payment_profiles: list[PaymentProfile] = Field(default_factory=default_payment_profiles)
    # ADDITION: Pulse thresholds the brief states as numbers (3x, trailing 12 months).
    spike_multiple: float = 3.0
    spike_lookback_months: int = 12
    # ADDITION / ASSUMPTION: only months inside this look-back are checked for a missing batch.
    # Confirmed in #4 (docs/ASSUMPTIONS.md A14).
    missing_batch_lookback_months: int = 24
    # ADDITION / ASSUMPTION: a missing payment is raised only when the batch's expected-by
    # date falls within this many months before the run date; older unmatched batches stay
    # listed on the gap alert. Decided in #20 (docs/ASSUMPTIONS.md A15).
    missing_payment_lookback_months: int = Field(default=12, ge=1)
    # ADDITION (review of 22 Nov 2026, docs/ASSUMPTIONS.md A15, A44): before a missing payment
    # is raised, the account's own open credit balance must still hold the batch (less the
    # credits of later batches not yet due); a batch the balance shows as paid is not raised.
    missing_payment_balance_check: bool = True
    # ADDITION (brief open item 2): which lines Sentinel S1 may flag. Decided in #9
    # (docs/ASSUMPTIONS.md A1): person-posted lines only.
    sentinel_s1_scope: Literal["people_only", "exempt_bot_upload", "all"] = "people_only"
    # ADDITION (review of 22 Nov 2026, fix 8, docs/ASSUMPTIONS.md A1): True skips S1 on accounts
    # whose allowed age is "No Overdue" (pension-type provisions, where large one-off bookings
    # are normal). Off: the brief's open-item-1 example (A2) is on such an account.
    sentinel_s1_skip_no_overdue_accounts: bool = False
    # ADDITION (#16, docs/ASSUMPTIONS.md A8): today's close review falls on this working day
    # after month end. Working days are Monday to Friday minus close_review_holidays. (This
    # replaces close_review_days, month end + 5 calendar days; saved rules that still carry
    # that field load fine, it is ignored.)
    close_review_working_day: int = Field(default=5, ge=1)
    close_review_holidays: list[date] = Field(default_factory=list)
    # ADDITION (#16, A8): "weekly" counts lead days from the weekly run on or after the first
    # signal (Okane runs weekly); "daily" counts from the first signal itself.
    lead_time_view: Literal["weekly", "daily"] = "weekly"
    # ADDITION (#16, A8): weekday of the weekly run, 0 = Monday (the Monday 06:00 job).
    weekly_run_weekday: int = Field(default=0, ge=0, le=6)
    # ADDITION (#10, docs/ASSUMPTIONS.md A4): Sentinel S2 ignores amounts below this, in the
    # document currency (the figure as typed).
    sentinel_s2_min_amount: float = 1_000
    # ADDITION (#12, docs/ASSUMPTIONS.md A6): typo prompts. A word seen at most
    # typo_max_rare_count times, typo_max_edits letters (Levenshtein) away from a word seen at
    # least typo_common_ratio times as often, is flagged unless it is on the allow-list.
    typo_max_rare_count: int = Field(default=3, ge=1)
    typo_common_ratio: float = Field(default=20.0, gt=0)
    # ADDITION (#13): bounded so a slip on the Rules page cannot flood the Inbox.
    typo_max_edits: int = Field(default=1, ge=1, le=3)
    # known abbreviations and foreign words that are never typos (compared lower-case)
    typo_allow_list: list[str] = Field(
        default_factory=lambda: ["alloc", "avance", "recov", "reverse"]
    )
    # ADDITION (#13, A6): only words of at least this many letters are checked for typos.
    typo_min_word_length: int = Field(default=5, ge=2)
    # ADDITION (#13, A6) / ASSUMPTION: the period-label prompt looks only at documents with at
    # least this many lines that name a period, so "most lines" means something.
    period_label_min_lines: int = Field(default=3, ge=2)
    # ADDITION / ASSUMPTION: Recurring-Correction Miner.
    miner_min_repeats: int = 3
    # ADDITION (#14, docs/ASSUMPTIONS.md A7): a repeated manual posting reaches the Inbox when
    # its score (distinct entities x distinct months) is at least this.
    miner_min_score: int = 12
    # ADDITION (#14, A7): True = the person who posted is part of the fingerprint (the original
    # rule); False = the same header text by anyone on the account forms one pattern.
    miner_by_user: bool = True
    # ADDITION (review of 22 Nov 2026, fix 6, docs/ASSUMPTIONS.md A7): a pattern whose lines
    # mostly cancel in exact pairs (an accrual and its reversal) is a routine, not a repeated
    # correction; it is dropped when this share of its lines or more is paired. 1.0 = off (the
    # default, decided in the review of PR #73: on, it drops every Fixed assets card); 0.5 is
    # the proposed setting.
    miner_max_paired_share: float = Field(default=1.0, gt=0, le=1)
    # ADDITION / ASSUMPTION: risk score scaling.
    penalty_accounts: list[str] = Field(default_factory=lambda: ["P20/C192/279006"])
    exposure_cap_multiple: float = 5.0
    days_past_expected_cap: int = 90
    # ADDITION (#18, A9): the repeats component is 1 when a Miner pattern on the account spans
    # at least this many months (the original rule).
    repeats_min_months: int = Field(default=3, ge=1)
    # ADDITION (#21, A25): finding types shown in the inbox's default view whatever their amount
    # (a missing payroll batch has no amount because it was never booked).
    inbox_always_types: list[ExceptionType] = Field(default_factory=lambda: ["pulse_missing_batch"])
    # ADDITION (review of 22 Nov 2026, fix 5, docs/ASSUMPTIONS.md A47): on the Fixed assets
    # view, unpaired lines posted within this many days of the extract are this month's
    # accruals (timing); older unpaired lines never matched.
    fa_recent_days: int = Field(default=60, ge=1)
    # ADDITION (A47, A11): local currencies whose EUR rate is not yet confirmed; their EUR
    # figures are shown as "estimated rate".
    unconfirmed_rate_currencies: list[str] = Field(
        default_factory=lambda: ["JPY", "PLN", "USD", "CNY"]
    )
    # ADDITION (review of 22 Nov 2026, fix 7, docs/ASSUMPTIONS.md A8): a finding is "new this
    # week" when its first signal falls within this many days before the analysis date.
    new_since_days: int = Field(default=7, ge=1)
    # ADDITION (A43): each account's normal side, by ERP and account-number prefix. Used to
    # word a gap by direction ("more paid than accrued") and to label the Exposure page.
    account_normal_side: list[NormalSide] = Field(default_factory=default_normal_sides)
    error_type_severity: dict[str, float] = {
        "pulse_gap": 1.0,
        "pulse_missing_payment": 0.9,
        "sentinel_currency_code": 0.8,
        "sentinel_two_currencies": 0.7,
        "sentinel_outlier": 0.7,
        "sentinel_reversal": 0.7,
        "pulse_missing_batch": 0.6,
        "label_mismatch": 0.5,
        "pulse_spike": 0.5,
        "miner_cluster": 0.4,
        "typo": 0.2,
        # ADDITION (A46): a liability in debit or an asset in credit is a likely posting error;
        # an open net is real exposure the ageing report already lists line by line.
        "wrong_side_balance": 0.8,
        "open_balance": 0.6,
    }


class Line(BaseModel):
    """One open line item in the common model (brief section 6 mapping table)."""

    line_id: int
    workbook: Workgroup
    erp: Erp
    sheet: str
    source_row: int
    entity: str
    account: str
    account_name: str | None
    document_no: str
    item: int | None
    year: int | None
    period: int | None
    doc_type: str | None
    posting_date: date | None
    doc_date: date | None
    amount_dc: float
    currency_dc: str | None
    amount_lc: float
    currency_lc: str
    amount_eur: float
    eur_rate: float
    partner: str | None
    user_name: str | None
    text: str | None
    header_text: str | None
    reference: str | None
    assignment: str | None
    age_days: int | None
    allowed_age: int | None
    overdue_abs: float | None
    reversal: str | None


# ADDITION (#24): "upload" (A38).
RunTrigger = Literal["manual", "watcher", "schedule", "startup", "rules_change", "upload"]
# ADDITION (#24, A38): how an extract reached Okane's store.
ExtractRoute = Literal["upload", "watcher", "schedule", "startup", "manual"]


class ExtractSource(BaseModel):
    """ADDITION (#24, A38): one workbook a run read, with where it came from."""

    kind: Workgroup
    file_name: str
    file_hash: str
    extract_date: date | None = None
    route: ExtractRoute | None = None  # None for the synthetic sample folder
    received_by: str | None = None
    received_at: datetime | None = None
    rows: int = 0
    late: bool = False
    next_due: datetime | None = None


class Run(BaseModel):
    """One pipeline run over one snapshot."""

    run_id: str
    snapshot_id: str
    trigger: RunTrigger
    status: Literal["running", "finished", "failed"]
    source_files: list[str]
    file_hashes: list[str]
    synthetic: bool
    as_of: date
    started_at: datetime
    finished_at: datetime | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    # ADDITION (#24, A38): the workbooks this run read, their extract dates and lateness.
    sources: list[ExtractSource] = Field(default_factory=list)


class UploadResult(BaseModel):
    """ADDITION (#24, A38): answer to POST /api/uploads."""

    status: Literal["accepted"]
    kind: Workgroup
    file_name: str
    message: str
    run: Run | None = None


class RuleChange(BaseModel):
    """One entry of the append-only rules change log."""

    seq: int
    changed_at: datetime
    changed_by: str
    field: str
    old_value: str
    new_value: str
    reason: str


class RulesUpdate(BaseModel):
    """Body of PUT /api/rules: the full new rules plus who and why."""

    rules: Rules
    changed_by: str | None = None
    reason: str = Field(min_length=3)


class DecisionUpdate(BaseModel):
    """Body of PATCH /api/exceptions/{id}. A reason is required for any decided status."""

    status: Status | None = None
    decision_reason: str | None = None
    decided_class: ExceptionClass | None = None
    edited_comment: str | None = None
    decided_by: str | None = None


class DecisionEntry(BaseModel):
    """Audit trail entry for a decision on an exception."""

    exception_id: str
    status: Status
    decision_reason: str | None
    decided_class: ExceptionClass | None
    edited_comment: str | None
    decided_by: str
    decided_at: datetime


class TimelinePoint(BaseModel):
    """Gap chart point: month-end balance, expected balance and gap (brief section 8)."""

    month: str
    balance: float
    expected: float
    gap: float
    batch_eur: float | None
    batch_matched: bool | None


class BatchMatch(BaseModel):
    """One accrual batch and the payments that settled it, if any."""

    period: str | None
    accrual_date: date
    period_end: date | None
    batch_eur: float
    lines: int
    evidence: list[str]
    matched: bool
    payment_eur: float | None = None
    payment_dates: list[date] = Field(default_factory=list)
    payment_evidence: list[str] = Field(default_factory=list)
    payment_labels: list[str] = Field(default_factory=list)
    diff_pct: float | None = None
    lag_days: int | None = None


class PulseTimeline(BaseModel):
    """GET /api/pulse/{erp}/{entity}/{account}/timeline."""

    erp: Erp
    entity: str
    account: str
    label: str
    points: list[TimelinePoint]
    batches: list[BatchMatch]
    lag_median: float | None
    lag_p90: float | None


class EvidenceLine(BaseModel):
    """A source line shown in the drawer (text is shown as-is to the user, never to a model)."""

    document: str
    posting_date: date | None
    doc_type: str | None
    user_name: str | None
    text: str | None
    amount_eur: float
    currency_dc: str | None
    amount_dc: float


class Comment(BaseModel):
    """POST /api/exceptions/{id}/comment response."""

    exception_id: str
    comment: str
    source: Literal["model", "template"]
    verifier: VerifierResult
    checked_figures: list[str]
    failed_figures: list[str]
    cached: bool
    # ADDITION (#45, A10): when both model drafts were rejected, the labelled template is the
    # comment and the last rejected draft is kept here with the reasons, one click away.
    rejected_draft: str | None = None
    rejected_reasons: list[str] = Field(default_factory=list)


class ExceptionDetail(BaseModel):
    """GET /api/exceptions/{id}: the record, its evidence lines and chart series."""

    exception: ExceptionRecord
    evidence_lines: list[EvidenceLine]
    timeline: list[TimelinePoint] | None
    decisions: list[DecisionEntry]


class ExposureGroup(BaseModel):
    """Payroll netting per ERP, entity and account (brief section 8)."""

    erp: Erp
    entity: str
    account: str
    account_name: str | None
    lines: int
    overdue_abs: float
    net_eur: float
    paired_lines: int
    above_materiality: bool
    exception_id: str | None = None
    # ADDITION (A43): the account's normal side, "debit", "credit" or "unknown", so the Exposure
    # page can say whether the net is owed, an asset not yet used up, or on the wrong side.
    normal_side: str = "unknown"


class ExposureResponse(BaseModel):
    """GET /api/exposure/payroll: the old report next to the real exposure."""

    run_id: str
    materiality_eur: float
    old_rule_lines: int
    old_rule_overdue_abs: float
    net_eur: float
    groups_above: int
    groups: list[ExposureGroup]


class AssistantState(BaseModel):
    """ADDITION (review of 22 Nov 2026, fix 3, docs/ASSUMPTIONS.md A45): GET /api/assistant.

    ``assistant``: "on" when Ollama answers and the configured model is pulled; "offline" when
    it is enabled but Ollama does not answer or lacks the model; "off" when disabled in the
    settings. Without the assistant, notes use the labelled standard wording (A29). Kept apart
    from the liveness probe ``/api/health``, which is open without a password on the hosted
    demo (A41) and must not call out to the model server.
    """

    assistant: Literal["on", "offline", "off"]
    model: str
    reason: str | None = None


class FixedAssetGroup(BaseModel):
    """ADDITION (A47): one Fixed assets ERP, entity and account after exact pairing."""

    erp: Erp
    entity: str
    account: str
    account_name: str | None
    currency_lc: str
    lines: int
    zero_amount_lines: int  # amount in document currency 0: FX valuations, never paired
    paired_lines: int
    recent_lines: int  # unpaired, posted within Rules.fa_recent_days of the extract
    recent_net_lc: float
    recent_net_eur: float
    older_lines: int  # unpaired and older
    older_net_lc: float
    older_net_eur: float
    # Exchange differences: FX valuations plus what exact pairs (matched in document currency)
    # leave in local currency and EUR. net = recent + older + fx (review of PR #73).
    fx_net_lc: float = 0.0
    fx_net_eur: float = 0.0
    net_lc: float
    net_eur: float
    estimated_rate: bool  # the EUR rate of currency_lc is not yet confirmed (A11)


class FixedAssetExposure(BaseModel):
    """ADDITION (A47): GET /api/exposure/fixed-assets, what is really open in Fixed assets."""

    run_id: str
    extract_date: date | None
    recent_days: int
    lines: int
    zero_amount_lines: int
    paired_lines: int
    recent_lines: int
    older_lines: int
    net_eur: float
    groups: list[FixedAssetGroup]


class Kpis(BaseModel):
    """GET /api/kpis: header statistics."""

    run_id: str | None
    exceptions: int
    open_exceptions: int
    median_days_earlier: float | None
    blind_spots: int
    by_type: dict[str, int]
    old_rule_lines: int
    old_rule_overdue_abs: float
    exposure_groups_above: int
    # ADDITION (#21, A25): findings still to review per inbox tab, plus "all".
    inbox_views: dict[str, int] = Field(default_factory=dict)
