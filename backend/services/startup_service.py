from __future__ import annotations

import math
import re

import pandas as pd

from services.model_service import build_runtime_frame, predict_with_model
from services.llm_action_plan_service import generate_action_plan


DEFAULT_STARTUP_INPUT = {
    'funding': float('nan'),
    'team_size': float('nan'),
    'market': '',
    'experience': float('nan'),
}


def _json_safe_number(value: float):
    try:
        numeric = float(value)
    except Exception:
        return value
    if math.isnan(numeric) or math.isinf(numeric):
        return None
    return numeric


def _sanitize_startup_payload(payload: dict | None) -> dict:
    data = dict(payload or {})
    for key in ('funding', 'team_size', 'experience'):
        data[key] = _json_safe_number(data.get(key))
    return data


def _clamp(value: float, minimum: float, maximum: float) -> float:
    if value != value:
        return value
    return max(minimum, min(value, maximum))


def _round_currency(value: float, step: int = 10000) -> int:
    return int(round(value / step) * step)


def _safe_divisor(value: float) -> float:
    try:
        numeric = float(value)
    except Exception:
        return 1.0
    if numeric != numeric or numeric <= 0:
        return 1.0
    return numeric


def _startup_decision_label(score: float, experience: float) -> str:
    if score > 65 and experience < 2:
        return 'Promising but high execution risk'
    if score >= 85:
        return 'Investor-ready startup potential'
    if score > 65:
        return 'Promising'
    if score >= 50:
        return 'Average potential'
    return 'Needs stronger execution fundamentals'


def _calculate_startup_confidence(score: float, experience: float, funding: float, team_size: int, market_segment: str) -> int:
    base_confidence = 50.0 + (score - 50.0) * 0.3
    if experience == 0:
        base_confidence -= 15.0
    if funding != funding or team_size <= 0 or experience != experience:
        base_confidence -= 10.0
    if market_segment not in {'enterprise', 'consumer'}:
        base_confidence -= 5.0
    return int(round(_clamp(base_confidence, 5.0, 95.0)))


def _clean_sentence(text: str) -> str:
    cleaned = re.sub(r'\s+', ' ', str(text or '')).strip()
    cleaned = re.sub(r'([.?!]){2,}', r'\1', cleaned)
    cleaned = re.sub(r'\s+([.?!,])', r'\1', cleaned)
    return cleaned.strip()


def _dedupe_texts(items: list[str], limit: int | None = None) -> list[str]:
    unique = []
    seen = set()
    for item in items:
        cleaned = _clean_sentence(item)
        normalized = cleaned.rstrip('.').lower()
        if cleaned and normalized not in seen:
            seen.add(normalized)
            unique.append(cleaned)
    return unique if limit is None else unique[:limit]


def _normalize_market(text: str) -> dict[str, str]:
    lowered = str(text or '').strip().lower()

    market_segment = ''
    if any(re.search(rf'\b{re.escape(token)}\b', lowered) for token in ['enterprise', 'b2b']):
        market_segment = 'enterprise'
    elif any(re.search(rf'\b{re.escape(token)}\b', lowered) for token in ['consumer', 'b2c', 'd2c']):
        market_segment = 'consumer'

    market_type = ''
    for token in ['fintech', 'edtech', 'health', 'climate', 'ecommerce', 'crypto', 'saas', 'education', 'food', 'logistics', 'energy']:
        if re.search(rf'\b{re.escape(token)}\b', lowered):
            market_type = token
            break

    cleaned = re.sub(r'[^a-z\s-]', ' ', lowered)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    if not market_type and cleaned and cleaned not in {'enterprise', 'b2b', 'consumer', 'b2c', 'd2c'}:
        market_type = cleaned

    market_value = market_segment or market_type or ''
    return {
        'market': market_value,
        'market_type': market_type or 'general',
        'market_segment': market_segment or 'general',
    }


def _parse_number_with_suffix(number_text: str, suffix_text: str = '') -> float:
    cleaned_number = str(number_text or '').replace(',', '').strip()
    value = float(cleaned_number)
    suffix = str(suffix_text or '').strip().lower()

    if suffix == 'k':
        value *= 1_000
    elif suffix in {'m', 'mn'}:
        value *= 1_000_000
    elif suffix == 'b':
        value *= 1_000_000_000
    elif suffix in {'million', 'millions'}:
        value *= 1_000_000
    elif suffix in {'l', 'lac', 'lacs', 'lakh', 'lakhs'}:
        value *= 100_000
    elif suffix in {'cr', 'crore', 'crores'}:
        value *= 10_000_000

    return value


def _closest_contextual_match(text: str, patterns: list[str]) -> re.Match | None:
    closest_match = None
    closest_span = None

    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            span = match.end() - match.start()
            if closest_match is None or span < closest_span:
                closest_match = match
                closest_span = span

    return closest_match


def parse_startup_input(text: str) -> dict:
    message = str(text or '')
    lowered = message.lower()

    funding_match = _closest_contextual_match(
        message,
        [
            r'\b(?:funding|raised|capital|investment)\b[^\d]{0,20}([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|m|mn|b|l|lac|lacs|lakh|lakhs|cr|crore|crores|million|millions)?\b',
            r'([0-9][0-9,]*(?:\.[0-9]+)?)\s*(k|m|mn|b|l|lac|lacs|lakh|lakhs|cr|crore|crores|million|millions)?\b[^\w]{0,10}\b(?:in funding|raised|capital|investment)\b',
        ],
    )
    team_match = _closest_contextual_match(
        message,
        [
            r'\bteam\b[^\d]{0,12}(?:of\s+)?([0-9]{1,3})\b',
            r'\b([0-9]{1,3})\b[^\w]{0,6}\b(?:team members|members|people)\b',
            r'\b(?:members|people)\b[^\d]{0,12}(?:of\s+)?([0-9]{1,3})\b',
        ],
    )
    experience_match = _closest_contextual_match(
        message,
        [
            r'\b([0-9]+(?:\.[0-9]+)?)\b[^\w]{0,6}\b(?:years|yrs)\b(?:[^\w]{0,10}\bexperience\b)?',
            r'\bexperience\b[^\d]{0,12}([0-9]+(?:\.[0-9]+)?)\b[^\w]{0,6}\b(?:years|yrs)?',
        ],
    )

    market_type = ''
    market_segment = ''

    if any(re.search(rf'\b{re.escape(token)}\b', lowered) for token in ['enterprise', 'b2b']):
        market_segment = 'enterprise'
    elif any(re.search(rf'\b{re.escape(token)}\b', lowered) for token in ['consumer', 'b2c', 'd2c']):
        market_segment = 'consumer'

    for token in ['fintech', 'edtech', 'health', 'climate', 'ecommerce', 'crypto', 'saas', 'education', 'food', 'logistics', 'energy']:
        if re.search(rf'\b{re.escape(token)}\b', lowered):
            market_type = token
            break

    market = market_segment or market_type or ''

    funding = float('nan')
    if funding_match:
        funding = _parse_number_with_suffix(funding_match.group(1), funding_match.group(2) if funding_match.lastindex and funding_match.lastindex >= 2 else '')

    team_size = float('nan')
    if team_match:
        team_size = max(1, int(team_match.group(1)))

    experience = float('nan')
    if experience_match:
        experience = float(experience_match.group(1))

    normalized_market = _normalize_market(market)
    return {
        'funding': float(funding),
        'team_size': team_size,
        'market': normalized_market['market'],
        'market_type': normalized_market['market_type'],
        'market_segment': normalized_market['market_segment'],
        'experience': float(experience),
    }


def _coerce_startup_input(data: dict | None) -> dict:
    payload = data or {}

    def _numeric_or_nan(value):
        try:
            return float(value)
        except Exception:
            return float('nan')

    normalized_market = _normalize_market(payload.get('market', DEFAULT_STARTUP_INPUT['market']))
    return {
        'funding': _numeric_or_nan(payload.get('funding', DEFAULT_STARTUP_INPUT['funding'])),
        'team_size': _numeric_or_nan(payload.get('team_size', DEFAULT_STARTUP_INPUT['team_size'])),
        'market': normalized_market['market'],
        'market_type': normalized_market['market_type'],
        'market_segment': normalized_market['market_segment'],
        'experience': _numeric_or_nan(payload.get('experience', DEFAULT_STARTUP_INPUT['experience'])),
    }


def _score_band(score: float) -> tuple[str, str]:
    if score >= 85:
        return 'Investor-ready startup potential', 'Investor Ready'
    if score >= 70:
        return 'Strong startup potential', 'Strong'
    if score >= 50:
        return 'Promising startup potential', 'Promising'
    return 'Needs stronger execution fundamentals', 'Early Stage'



def _fallback_probability(funding: float, team_size: int, market: str, experience: float) -> float:
    # Simple fallback: average of normalized factors
    funding_norm = min(funding / 100000, 1.0)  # Normalize to 0-1
    team_norm = min(team_size / 10, 1.0)      # Normalize to 0-1
    exp_norm = min(experience / 5, 1.0)       # Normalize to 0-1
    market_bonus = 1.1 if market == 'enterprise' else 1.0
    return (funding_norm * 0.4 + team_norm * 0.3 + exp_norm * 0.3) * market_bonus


def _build_key_factors(funding: float, team_size: int, market: str, experience: float) -> list[str]:
    factors = []
    if experience > 5:
        factors.append(f'Founder experience is strong at {experience:.1f} years.')
    elif experience >= 3:
        factors.append(f'Founder experience is moderate at {experience:.1f} years.')
    else:
        factors.append(f'Founder experience is early at {experience:.1f} years.')

    if funding > 100000:
        factors.append(f'Funding of ${funding:,.0f} gives the company healthier operating runway.')
    elif funding >= 50000:
        factors.append(f'Funding of ${funding:,.0f} supports basic early execution but remains tight.')
    else:
        factors.append(f'Funding of ${funding:,.0f} is lean for product, hiring, and distribution needs.')

    if 4 <= team_size <= 10:
        factors.append(f'Team size of {team_size} is in the practical early-stage operating range.')
    elif team_size < 4:
        factors.append(f'Team size of {team_size} may limit shipping speed and go-to-market capacity.')
    else:
        factors.append(f'Team size of {team_size} may introduce coordination overhead for the current stage.')

    if market == 'enterprise':
        factors.append('Enterprise positioning can support larger contract value with strong sales execution.')
    else:
        factors.append(f'{market.title()} positioning will require clear evidence of repeatable demand.')

    return _dedupe_texts(factors, limit=4)


def _build_blocking_factors(funding: float, team_size: int, experience: float) -> list[str]:
    blocking_factors = []
    if funding < 50000:
        blocking_factors.append('Low funding limits execution speed')
    if team_size < 4:
        blocking_factors.append('Small team limits product and growth execution')
    if experience < 3:
        blocking_factors.append('Low founder experience increases execution risk')
    return _dedupe_texts(blocking_factors, limit=3)


def _build_risks(funding: float, team_size: int, market: str, experience: float) -> list[str]:
    risks = []
    if funding < 100000:
        risks.append('Limited runway can slow hiring, experimentation, and customer acquisition.')
    if team_size < 4:
        risks.append('A very small team may struggle to cover product, sales, and operations at once.')
    if team_size > 10:
        risks.append('A larger early-stage team can create coordination drag before strong traction is established.')
    if experience < 3:
        risks.append('Execution quality may depend on learning speed, advisors, and process discipline.')
    if market != 'enterprise':
        risks.append('Consumer-oriented growth usually needs stronger proof of retention and efficient acquisition.')
    return _dedupe_texts(risks, limit=3)


def _build_action_plan(funding: float, team_size: int, market: str, experience: float) -> list[str]:
    suggestions = []
    max_team_target = min(12, max(team_size, math.ceil(team_size * 1.5)))

    if team_size < 4:
        suggested_team = min(4, max_team_target)
        if suggested_team > team_size:
            suggestions.append(
                f'Expand the core team from {team_size} to about {suggested_team} people, focused on product and go-to-market execution.'
            )
    elif team_size > 10:
        suggestions.append('Stabilize ownership and productivity before adding more headcount.')

    if funding < 100000:
        funding_target = _round_currency(max(funding, min(funding * 1.8, 200000.0)))
        if funding_target > funding:
            suggestions.append(
                f'Plan the next raise around ${funding_target:,.0f} to improve runway without overshooting realistic early-stage needs.'
            )

    if experience <= 5:
        suggestions.append('Add experienced operators or advisors to reduce execution risk and sharpen decision quality.')

    if market == 'enterprise':
        suggestions.append('Focus on pilots, conversion milestones, and a repeatable enterprise sales motion.')
    else:
        suggestions.append('Strengthen proof of demand with repeat usage, customer feedback, and a narrower market wedge.')

    if 4 <= team_size <= 10 and funding >= 100000 and experience > 5:
        suggestions.insert(0, 'Prioritize traction milestones and capital efficiency rather than major structural changes.')

    return _dedupe_texts(suggestions, limit=3)


def _bounded_team_target(current: float, target: float) -> float:
    """
    The startup training data can produce very large 'ideal' team sizes (e.g. 79).
    That may reflect later-stage companies, but it is not practical early-stage guidance.
    """
    if target != target:
        return target
    bounded = min(float(target), 12.0)
    if current == current:
        bounded = max(bounded, min(max(float(current), 4.0), 12.0))
    return bounded


def _startup_stage(score: float) -> str:
    if score >= 85:
        return 'Investor-ready'
    if score >= 70:
        return 'Seed-ready'
    if score >= 50:
        return 'Pre-seed'
    return 'Idea-validation'


def _vertical_playbook(market_type: str) -> dict:
    """Vertical-specific compliance / GTM nuances.

    Additive only — callers merge these into phase tasks so the base
    Validate -> Build -> Traction -> Raise skeleton never changes.
    """
    playbooks = {
        'fintech': {
            'label': 'Fintech (regulated)',
            'validate_add': 'Map RBI/compliance perimeter early — decide regulated vs partner-led (NBFC/Bank-as-a-service) path.',
            'build_add': 'Ship KYC/KYB, audit logs, and reconciliation from day one; sandbox with 1 compliance reviewer.',
            'traction_kpi': 'Approval rate ≥95% + reconciliation breaks <0.5% + 2 live partners.',
            'hire': 'Compliance/finance-ops hire by Day 60 (fractional ok).',
        },
        'health': {
            'label': 'HealthTech (trust-critical)',
            'validate_add': 'Validate clinical workflow with 3 practitioners; list data-privacy (DPDP/HIPAA-aware) requirements.',
            'build_add': 'Add consent management, data retention policy, and clinician review loop before launch.',
            'traction_kpi': 'Pilot retention ≥60% at 4 weeks + clinician NPS ≥40.',
            'hire': 'Clinical/domain advisor + QA-focused engineer by Day 60.',
        },
        'edtech': {
            'label': 'EdTech (outcomes-driven)',
            'validate_add': 'Define one measurable learning outcome; pre-sell to 2 institutions/cohorts.',
            'build_add': 'Instrument learning analytics (completion, assessment lift) from first release.',
            'traction_kpi': 'Completion ≥40% + NPS ≥35 on core cohort.',
            'hire': 'Content/curriculum + community lead by Day 60.',
        },
        'saas': {
            'label': 'B2B SaaS (sales-led)',
            'validate_add': 'Nail one repeatable job-to-be-done; get 2 paid LOIs before building admin extras.',
            'build_add': 'Ship SSO-ready auth, roles, usage metering, and admin audit trail.',
            'traction_kpi': '3 paid pilots + ≥1 expansion + NDR signal.',
            'hire': 'Founding AE / founder-led sales with SDR support by Day 90.',
        },
        'ecommerce': {
            'label': 'Commerce (retention-led)',
            'validate_add': 'Prove repeat purchase on one hero SKU/category before expanding catalog.',
            'build_add': 'Instrument returns, CAC payback, and repeat-rate dashboards.',
            'traction_kpi': 'Repeat rate ≥25% + CAC payback <90 days.',
            'hire': 'Growth/performance marketer (part-time ok) by Day 60.',
        },
        'climate': {
            'label': 'Climate (capex-aware)',
            'validate_add': 'Validate unit economics + policy/tender dependency with 2 buyers.',
            'build_add': 'Meter impact metrics (CO2/kWh/cost saved) alongside product analytics.',
            'traction_kpi': '2 paid deployments + measured impact report.',
            'hire': 'Field ops / partnerships lead by Day 90.',
        },
        'crypto': {
            'label': 'Crypto (security-first)',
            'validate_add': 'Define custody/key-management and regulatory stance in writing before launch.',
            'build_add': 'External audit for contracts + bug-bounty before mainnet funds.',
            'traction_kpi': 'Audited release + TVL/usage with 0 criticals.',
            'hire': 'Security auditor (external) + protocol engineer.',
        },
    }
    return playbooks.get((market_type or '').lower(), {
        'label': f"{(market_type or 'General').title()} vertical",
        'validate_add': '',
        'build_add': '',
        'traction_kpi': '',
        'hire': '',
    })


def _readiness_status(value: bool, partial: bool = False) -> str:
    if value:
        return 'match'
    if partial:
        return 'partial'
    return 'mismatch'


def _build_startup_roadmap(
    funding: float,
    team_size: int,
    market: str,
    experience: float,
    score: float,
    market_type: str = '',
    market_segment: str = '',
) -> dict:
    """Deterministic phased execution roadmap for the startup domain.

    Mirrors the career domain's `career_intelligence` payload so the
    frontend can render a rich roadmap without depending on the LLM.
    Phases are always Validate -> Build -> Traction -> Raise/Scale,
    with tasks tailored to capital / team / experience gaps.
    """
    stage = _startup_stage(score)
    monthly_burn = max(float(team_size) * 6000.0, 15000.0) if team_size > 0 else 15000.0
    runway_months = round(float(funding) / monthly_burn, 1) if funding > 0 else 0.0
    capital_target = _round_currency(max(float(funding) * 1.8, 200000.0))
    team_target = int(min(12, max(4, team_size + 1 if team_size < 4 else team_size)))

    market_label = (market or market_type or market_segment or 'your market').strip() or 'your market'
    enterprise_motion = (market_segment or market or '').lower() in {'enterprise'} or 'b2b' in str(market).lower()

    readiness = {
        'capital': {
            'status': _readiness_status(funding >= 200000, partial=funding >= 100000),
            'label': f"${funding:,.0f} capital / ~{runway_months} mo runway",
        },
        'team': {
            'status': _readiness_status(4 <= team_size <= 10, partial=(team_size == 3 or 11 <= team_size <= 12)),
            'label': f"Team of {team_size} ({'healthy' if 4 <= team_size <= 10 else 'needs shaping'})",
        },
        'experience': {
            'status': _readiness_status(experience >= 5, partial=experience >= 3),
            'label': f"{experience:.1f} yrs founder experience",
        },
        'market': {
            'status': _readiness_status(bool((market_segment or '') in {'enterprise', 'consumer'}),
                                        partial=bool(market_type and market_type != 'general')),
            'label': f"{market_label.title()} positioning",
        },
    }

    gaps: list[str] = []
    if funding < 100000:
        gaps.append(f"Runway is thin (~{runway_months} mo) — target ~${capital_target:,.0f} for 12-18 months of execution.")
    if team_size < 4:
        gaps.append(f"Team of {team_size} is below the 4-person execution minimum — hire toward ~{team_target} (product + GTM).")
    elif team_size > 10:
        gaps.append("Team is large for this stage — freeze hiring until ownership and traction milestones are clear.")
    if experience < 3:
        gaps.append("Founder experience < 3 yrs — add an operator/advisor and a weekly decision cadence.")
    if not (market_segment or '') in {'enterprise', 'consumer'} and (not market_type or market_type == 'general'):
        gaps.append("Market wedge is vague — narrow to one ICP and one repeatable use case.")
    if not gaps:
        gaps.append("Foundations are solid — the unlock is traction proof (pilots, retention, revenue).")

    # Critical blockers, kept separate from advisory `gaps` so the UI/PDF
    # can surface them prominently (red/bold).
    risk_flags: list[str] = []
    if funding <= 0:
        risk_flags.append("CRITICAL: No capital recorded — execution cannot start without bridge funding or revenue.")
    elif runway_months < 2:
        risk_flags.append(f"CRITICAL: Runway under 2 months (~{runway_months} mo) — cut burn or bridge immediately.")
    if team_size <= 2:
        risk_flags.append("CRITICAL: Founding team of 2 or fewer — no redundancy; add a technical co-founder or core builder.")
    if experience < 2:
        risk_flags.append("CRITICAL: Founder experience under 2 yrs — execution risk is high without an operator/advisor.")
    if not (market_segment or '') in {'enterprise', 'consumer'} and (not market_type or market_type == 'general'):
        risk_flags.append("CRITICAL: No clear market wedge — validation will stall without one ICP and use case.")

    thin_runway = funding < 100000
    small_team = team_size < 4
    junior_founder = experience < 3

    validate_tasks = [
        f"Interview 20 {market_label} buyers/users; score pain, budget, and urgency (close 5 design partners).",
        "Prototype the core workflow (concierge or clickable demo) and get 5 recorded feedback sessions.",
        "Write a one-page thesis: ICP, problem, willingness-to-pay, and why now.",
    ]
    if thin_runway:
        validate_tasks.append("Cap validation spend: time-box discovery to 2 weeks and use no-code/concierge tests only.")
    else:
        validate_tasks.append("Pre-sell 2 LOIs or paid pilots during discovery to de-risk the build phase.")
    if junior_founder:
        validate_tasks.append("Recruit 1 domain advisor this month; review every major decision with them weekly.")
    else:
        validate_tasks.append("Document your unfair advantage (distribution, domain, prior wins) into the pitch narrative.")

    build_tasks = [
        (
            "Freeze scope to 3 core jobs-to-be-done; ship behind feature flags with weekly demos."
            if team_size >= 4 else
            f"Expand to ~{team_target} (product + GTM) before committing to a 30-day build sprint."
        ),
        "Add auth, billing rails, event tracking, and a feedback widget before launch.",
        "Dogfood with design partners; fix onboarding drop-off above 40%.",
    ]
    if small_team:
        build_tasks.append("Keep the stack boring (proven tools) — no microservices or infra rewrites at this stage.")
    else:
        build_tasks.append("Assign clear DRI per workstream (product, GTM, ops) to avoid coordination drag.")
    build_tasks.append("Run a weekly demo day with design partners; ship fixes within 48 hours of feedback.")

    if enterprise_motion:
        traction_tasks = [
            f"Close 3-5 paid pilots in {market_label} with written success criteria and conversion dates.",
            "Ship a security/compliance one-pager (data handling, access control) to unblock procurement.",
            "Instrument activation → pilot → paid conversion funnel and review it weekly.",
            "Turn the first win into a case study + reference call within 14 days of go-live.",
            "Map the buying committee (champion, economic buyer, security) for every open pilot.",
        ]
        traction_exit = "3+ pilots with ≥1 conversion to paid + repeatable sales script."
    else:
        traction_tasks = [
            f"Drive 4 weeks of repeat usage in {market_label} — cohort retention is the gate, not signups.",
            "Run 15 customer interviews; ship the top 3 friction fixes within the sprint.",
            "Stand up a referral loop (share/invite) and measure K-factor weekly.",
            "Publish 2 build-in-public / teardown posts per week in the community where your ICP lives.",
            "A/B test onboarding (1 variable at a time) until activation crosses 40%.",
        ]
        traction_exit = "W4 retention ≥25% + NPS ≥30 on the core wedge."

    if score >= 70:
        raise_tasks = [
            "Build a data room: metrics, cohort charts, pipeline, burn multiple, and 18-month plan.",
            "Open 30 investor/advisor conversations with a tight 10-slide narrative.",
            "Set a weekly operating cadence: metrics review, top 3 bets, and kill list."
            + (" Add an experienced operator/advisor to de-risk execution." if experience < 5 else ""),
            "Secure 2 warm intros per week via design partners and advisors — no cold spray.",
            "Define the round terms (target, minimum, use of funds) before the first partner meeting.",
        ]
    else:
        raise_tasks = [
            "Cut burn to extend runway 3+ months; tie every hire to a traction metric.",
            "Line up bridge options (revenue, angels, grants) tied to hitting the Traction exit criteria.",
            "Set a weekly operating cadence: metrics review, top 3 bets, and kill list."
            + (" Add an experienced operator/advisor to de-risk execution." if experience < 5 else ""),
            "Sell services / annual prepay to 2 design partners to fund the next build cycle.",
            "Pause fundraising outreach until the Traction exit gate is hit — raise on proof, not slides.",
        ]

    vertical = _vertical_playbook(market_type)
    if vertical.get('validate_add'):
        validate_tasks.append(vertical['validate_add'])
    if vertical.get('build_add'):
        build_tasks.append(vertical['build_add'])

    validate_kpis = [
        '5 design partners signed + willingness-to-pay in writing.',
        'Top 3 pains ranked by budget + urgency (scorecard).',
    ]
    build_kpis = [
        'Live MVP with ≥3 weekly-active design partners.',
        'Onboarding drop-off <40% + event tracking live.',
    ]
    if enterprise_motion:
        traction_kpis = [
            '3-5 paid pilots with success criteria + conversion dates.',
            'Pilot → paid conversion ≥20% + 1 case study.',
        ]
    else:
        traction_kpis = [
            'W4 retention ≥25% + activation ≥40%.',
            'NPS ≥30 on core wedge + referral loop live.',
        ]
    if vertical.get('traction_kpi'):
        traction_kpis.append(vertical['traction_kpi'])
    raise_kpis = [
        'Data room live: cohorts, pipeline, burn multiple, 18-mo plan.',
        '2+ partners in diligence + 6-month pipeline.',
    ] if score >= 70 else [
        f"Runway extended to ≥6 mo (now ~{runway_months} mo).",
        'Traction gate hit before priced raise.',
    ]

    # Hiring plan — role-level, stage-gated (additive, UI-optional).
    hiring_plan: list[dict] = []
    if team_size < 4:
        hiring_plan.append({
            'role': 'Product + GTM builder',
            'when': 'Days 0-30',
            'why': f"Team of {team_size} below 4-person minimum — target ~{team_target}.",
        })
    if junior_founder:
        hiring_plan.append({
            'role': 'Domain advisor / fractional operator',
            'when': 'Days 0-30',
            'why': 'Founder experience <3 yrs — weekly decision review.',
        })
    if vertical.get('hire'):
        hiring_plan.append({'role': vertical['hire'].split(' by ')[0], 'when': 'Days 31-90', 'why': vertical['hire']})
    if enterprise_motion:
        hiring_plan.append({
            'role': 'Founding sales / solutions (founder-led + 1 support)',
            'when': 'Days 61-90',
            'why': 'Enterprise pilots need buying-committee coverage.',
        })
    else:
        hiring_plan.append({
            'role': 'Growth + community loop owner',
            'when': 'Days 61-90',
            'why': 'Consumer traction needs retention + referral ownership.',
        })
    if score >= 70:
        hiring_plan.append({
            'role': 'Ops / finance discipline (part-time ok)',
            'when': 'Days 91-180',
            'why': 'Raise readiness needs burn-multiple + reporting rigor.',
        })

    monthly_burn = max(float(team_size) * 6000.0, 15000.0) if team_size > 0 else 15000.0
    funding_plan = {
        'monthly_burn': int(round(monthly_burn)),
        'runway_months': runway_months,
        'capital_target': capital_target,
        'use_of_funds': [
            f"Product + GTM hires (~60% of ${capital_target:,.0f}).",
            'Traction experiments + pilots (~25%).',
            'Ops buffer + compliance (~15%).',
        ],
    }

    phases = [
        {
            'phase': 'Validate',
            'timeline': 'Days 0-30',
            'focus': f"Nail one ICP and one painful problem in {market_label}.",
            'tasks': validate_tasks,
            'exit_criteria': "5 design partners + willingness-to-pay evidence in writing.",
            'kpis': validate_kpis,
        },
        {
            'phase': 'Build MVP',
            'timeline': 'Days 31-60',
            'focus': "Ship the smallest lovable product with analytics from day one.",
            'tasks': build_tasks,
            'exit_criteria': "Live MVP with ≥3 active design partners using it weekly.",
            'kpis': build_kpis,
        },
        {
            'phase': 'Traction',
            'timeline': 'Days 61-90',
            'focus': "Prove repeatable demand, not vanity growth.",
            'tasks': traction_tasks,
            'exit_criteria': traction_exit,
            'kpis': traction_kpis,
        },
        {
            'phase': 'Raise / Scale' if score >= 70 else 'Extend runway',
            'timeline': 'Days 91-180',
            'focus': (
                f"Raise ~${capital_target:,.0f} on traction proof; scale what repeats."
                if score >= 70 else
                f"Extend runway (~{runway_months} mo left) while hitting traction gates before raising."
            ),
            'tasks': raise_tasks,
            'exit_criteria': (
                "Term sheet path: 2+ partners in diligence + 6-month pipeline."
                if score >= 70 else
                "Traction gate hit + 12-month runway plan before a priced raise."
            ),
        },
    ]

    return {
        'stage': stage,
        'readiness': readiness,
        'gaps': _dedupe_texts(gaps, limit=4),
        'risk_flags': _dedupe_texts(risk_flags, limit=5),
        'phases': phases,
        'runway_months': runway_months,
        'capital_target': capital_target,
        'team_target': team_target,
        'vertical': {'type': (market_type or 'general'), 'label': vertical.get('label', 'General')},
        'hiring_plan': hiring_plan[:5],
        'funding_plan': funding_plan,
        'milestones_30_60_90': [
            'Day 30: 5 design partners + written willingness-to-pay.',
            'Day 60: live MVP with weekly active usage.',
            f"Day 90: {traction_exit}",
        ],
    }


def _build_startup_response(score: float, funding: float, team_size: int, market: str, experience: float, market_segment: str | None = None) -> dict:
    label = _startup_decision_label(score, experience)
    confidence = _calculate_startup_confidence(score, experience, funding, team_size, market_segment or market)
    score_label = 'Fallback Estimate' if confidence < 40 else label
    key_factors = _build_key_factors(funding, team_size, market, experience)
    blocking_factors = _build_blocking_factors(funding, team_size, experience)
    risks = _build_risks(funding, team_size, market, experience)
    action_plan = _build_action_plan(funding, team_size, market, experience)

    summary_parts = [
        f'The startup scores {score:.1f}/100 based on capital, team shape, founder experience, and market context.'
    ]
    if key_factors:
        summary_parts.append(key_factors[0])
    if blocking_factors:
        summary_parts.append(blocking_factors[0] + '.')

    summary = _clean_sentence(' '.join(summary_parts))
    what_if_score = min(100, int(round(score + 10)))
    insights = [
        f'Funding ({"+8%" if funding >= 100000 else "-8%"}) {"improves" if funding >= 100000 else "reduces"} operating runway.',
        f'Team size ({"+6%" if 4 <= team_size <= 10 else "-6%"}) {"supports" if 4 <= team_size <= 10 else "limits"} execution capacity.',
        f'Founder experience ({"+7%" if experience >= 3 else "-7%"}) {"reduces" if experience >= 3 else "increases"} execution risk.',
    ]

    return {
        'score': round(score, 1),
        'decision': label,
        'decision_band': score_label,
        'band': score_label,
        'confidence': confidence,
        'confidence_ratio': round(confidence / 100.0, 4),
        'summary': summary,
        'insights': insights,
        'key_factors': key_factors,
        'risks': risks,
        'options': [{'name': market.title() if market else 'Startup', 'score': round(score, 1), 'reason': summary}],
        'action_plan': action_plan,
        'what_if': f'Adding stronger traction evidence or extending runway can improve the score from {int(round(score))} to {what_if_score}.',
        'blocking_factors': blocking_factors,
        'probability': round(score / 100.0, 4),


        'score_label': score_label,
        'score_band': score_label,
        'next_step': action_plan[0] if action_plan else '',
        'explanation': ' '.join(insights),
        'suggestions': action_plan[:3],
    }


def get_startup_decision(data: dict | None):
    startup = _coerce_startup_input(data)
    funding = startup['funding']
    team_size = startup['team_size']
    market = startup['market']
    experience = startup['experience']

    missing = []
    if math.isnan(funding):
        missing.append('funding')
    if math.isnan(team_size):
        missing.append('team_size')
    if math.isnan(experience):
        missing.append('experience')
    if missing:
        return {
            'decision': 'Need more details to assess startup potential',
            'probability': 0.5,
            'score_label': 'Unknown',
            'score_band': 'Unknown',
            'summary': 'The startup model needs your funding amount, team size, and founder experience to produce a reliable result.',
            'next_step': 'Share funding, team size, and founder experience.',
            'target_score': 75.0,
            'key_factors': ['missing_inputs'],
            'explanation': f'Missing required inputs: {", ".join(missing)}.',
            'suggestions': [
                'Provide: funding, team size, and founder experience.',
                'If unsure, provide approximate ranges.',
            ],
            'risks': ['Inputs were missing, so any score would be unreliable.'],
            'meta': {'missing_fields': missing},
            'intent': 'startup',
            'mode': 'single',
            'parsed_input': _sanitize_startup_payload(startup),
        }

    market_type = startup.get('market_type', '')
    market_segment = startup.get('market_segment', market)
    feature_values = {
        'funding': funding,
        'team_size': team_size,
        'market': market,
        'experience': experience,
        'funding_per_team': funding / _safe_divisor(team_size),
        'runway_score': min(funding / 300000.0, 2.5),
        'experience_per_team_member': experience / _safe_divisor(team_size),
        'capital_efficiency': (funding / _safe_divisor(team_size)) / 100000.0,
    }
    model_frame = build_runtime_frame('startup', feature_values)

    model_result = predict_with_model('startup', model_frame)
    if model_result is None:
        fallback_prob = _fallback_probability(funding, team_size, market, experience)
        response = _build_startup_response(fallback_prob * 100, funding, team_size, market, experience, market_segment)
        response['insights'] = []
        response['risks'] = []
        response['action_plan'] = []
        response['what_if'] = ''
        response['confidence'] = _calculate_startup_confidence(fallback_prob * 100, experience, funding, team_size, market_segment)
        response['probability'] = fallback_prob
        response['score'] = fallback_prob * 100
        response['score_label'] = response['score_label']
        response['score_band'] = response['score_label']
        response['decision_band'] = response['score_label']
    else:
        row = {
            'funding': funding,
            'team_size': team_size,
            'market': market,
            'experience': experience,
            'funding_per_team': funding / _safe_divisor(team_size),
        }
        positive = []
        negative = []
        factor_impacts = []
        for raw_feature, shap_value in model_result.get('raw_shap', [])[:8]:
            feature = raw_feature.replace('num__', '').replace('cat__', '')
            statement = f"{feature}: SHAP={float(shap_value):+.4f}; current={row.get(feature, feature)}"
            factor_impacts.append({'factor': feature, 'impact': statement, 'value': round(float(shap_value), 4)})
            if float(shap_value) > 0:
                positive.append(statement)
            elif float(shap_value) < 0:
                negative.append(statement)

        updated = dict(row)
        profiles = model_result.get('profiles', {}) or {}
        numeric_profiles = profiles.get('numeric', {}) or {}
        changed = []
        action_plan = []
        ranked_gaps = []
        for feature in ['funding', 'team_size', 'experience']:
            profile = numeric_profiles.get(feature, {})
            target = profile.get('positive_p25') or profile.get('positive_median')
            if target is None:
                continue
            target_value = float(target)
            if feature == 'team_size':
                target_value = _bounded_team_target(row.get('team_size', float('nan')), target_value)
            if updated[feature] != updated[feature]:
                continue
            if target_value > updated[feature]:
                updated[feature] = target_value
                changed.append(feature)
                ranked_gaps.append((target_value - row[feature], feature, row[feature], target_value))
        updated['funding_per_team'] = updated['funding'] / _safe_divisor(updated['team_size'])
        rerun = predict_with_model('startup', build_runtime_frame('startup', updated))
        what_if = ''
        if rerun is not None:
            what_if = (
                f"Re-running the startup model after improving {', '.join(changed) or 'top gap features'} "
                f"changes the score from {round(model_result['probability'] * 100, 2)} to {round(rerun['probability'] * 100, 2)}."
            )

        ranked_gaps.sort(reverse=True)
        for _, feature, current, target in ranked_gaps[:4]:
            if feature == 'team_size':
                action_plan.append(
                    f"Improve team size; current core team is {int(round(float(current)))}. Aim for about {int(round(float(target)))} people to increase execution capacity."
                )
            else:
                action_plan.append(
                    f"Improve {feature}; current value {round(float(current), 2)} is below the stronger model profile range near {round(float(target), 2)}."
                )

        score = round(model_result['probability'] * 100, 2)
        label = _startup_decision_label(score, experience)
        confidence = _calculate_startup_confidence(score, experience, funding, team_size, market_segment)
        score_label = 'Fallback Estimate' if confidence < 40 else label
        option_name = (
            market_type.title() if market_type and market_type != 'general' else
            market.title() if market else
            market_segment.title() if market_segment and market_segment != 'general' else
            'Startup'
        )
        response = {
            'score': score,
            'decision': label,
            'decision_band': score_label,
            'band': score_label,
            'confidence': confidence,
            'confidence_ratio': round(confidence / 100.0, 4),
            'summary': f"Startup score returned directly from the trained model: {score}.",
            'insights': positive[:4],
            'key_factors': [f"{item['factor']} ({item['value']:+.4f})" for item in factor_impacts],
            'risks': negative[:4],
            'options': [{'name': option_name, 'score': score}],
            'action_plan': action_plan,
            'what_if': what_if,
            'blocking_factors': negative[:3],
            'probability': model_result['probability'],
            'score_label': score_label,
            'score_band': score_label,
            'next_step': action_plan[0] if action_plan else '',
            'explanation': ' '.join(positive + negative),
            'suggestions': action_plan[:3],
        }
    merged = response | {
        'intent': 'startup',
        'mode': 'single',
        'parsed_input': _sanitize_startup_payload(startup),
    }

    try:
        roadmap = _build_startup_roadmap(
            float(funding),
            int(round(float(team_size))),
            str(market or ''),
            float(experience),
            float(merged.get('score', 0.0) or 0.0),
            market_type=str(market_type or ''),
            market_segment=str(market_segment or ''),
        )
        merged['details'] = dict((merged.get('details') or {}))
        merged['details']['startup_roadmap'] = roadmap
        merged['followup_questions'] = [
            'Who is the single ICP for the next 30 days (title + segment)?',
            'Which 3 design partners will use the MVP weekly?',
            f"What traction gate unlocks the next ${roadmap.get('capital_target', 200000):,.0f} raise?",
        ]
    except Exception:
        pass

    llm_plan = generate_action_plan(
        domain="startup",
        user_input={
            "funding": funding,
            "team_size": team_size,
            "experience": experience,
            "market": market,
            "market_segment": market_segment,
        },
        decision=str(merged.get("decision") or ""),
        score=float(merged.get("score", 0.0) or 0.0),
        risks=[str(item) for item in (merged.get("risks") or [])],
        insights=[str(item) for item in (merged.get("insights") or [])],
    )
    if llm_plan:
        action_steps = llm_plan.get("action_plan", [])
        merged["action_plan"] = action_steps
        merged["suggestions"] = action_steps[:3]
        merged["next_step"] = action_steps[0] if action_steps else ""
        merged["meta"] = dict((merged.get("meta") or {}))
        merged["meta"]["action_plan_source"] = "ollama"
        # Store additional LLM outputs in details
        merged["details"] = dict((merged.get("details") or {}))
        merged["details"]["reality_check"] = llm_plan.get("reality_check", "")
        merged["details"]["project_ideas"] = llm_plan.get("project_ideas", [])

    return merged


def get_startup_decision_from_text(text: str) -> dict:
    parsed = parse_startup_input(text)
    response = get_startup_decision(parsed)
    response['parsed_input'] = _sanitize_startup_payload(parsed)
    return response
