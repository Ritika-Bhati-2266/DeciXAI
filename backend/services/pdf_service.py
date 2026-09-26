import io

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER


def generate_decision_report(domain: str, decision_data: dict) -> io.BytesIO:
    """
    Generates a PDF report from the decision JSON data.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=letter, 
        rightMargin=72, 
        leftMargin=72, 
        topMargin=72, 
        bottomMargin=72
    )
    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'TitleStyle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor("#0f172a"),
        alignment=TA_CENTER,
        spaceAfter=30
    )
    heading_style = ParagraphStyle(
        'HeadingStyle',
        parent=styles['Heading2'],
        fontSize=16,
        textColor=colors.HexColor("#0284c7"),
        spaceBefore=20,
        spaceAfter=10
    )
    normal_style = styles['Normal']
    normal_style.fontSize = 11
    normal_style.leading = 16
    
    elements = []
    
    # Title
    domain_title = domain.capitalize()
    elements.append(Paragraph(f"DeciXAI {domain_title} Report", title_style))
    
    # Executive Summary Section
    elements.append(Paragraph("Executive Summary", heading_style))
    
    score = decision_data.get('score', 'N/A')
    if isinstance(score, float):
        score = round(score, 1)
        
    decision = decision_data.get('decision', 'N/A')
    summary = decision_data.get('summary', 'No summary available.')
    
    summary_data = [
        ["Decision / Band", str(decision)],
        ["Score", f"{score} / 100"],
    ]
    
    t = Table(summary_data, colWidths=[120, 340])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#f8fafc")),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor("#334155")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 1, colors.HexColor("#e2e8f0")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 15))
    elements.append(Paragraph(summary, normal_style))
    
    # Recommended Action Plan
    actions = decision_data.get('action_plan', [])
    if actions:
        elements.append(Paragraph("Recommended Action Plan", heading_style))
        for i, action in enumerate(actions, 1):
            elements.append(Paragraph(f"<b>{i}.</b> {action}", normal_style))
            elements.append(Spacer(1, 6))
            
    # Key Factors / Drivers
    factors = decision_data.get('key_factors', [])
    if factors:
        elements.append(Paragraph("Key Driving Factors", heading_style))
        for factor in factors:
            if isinstance(factor, dict) and 'factor' in factor:
                # Handle structured factor impacts
                text = f"• <b>{factor['factor']}:</b> {factor.get('impact', '')}"
            else:
                text = f"• {factor}"
            elements.append(Paragraph(text, normal_style))
            elements.append(Spacer(1, 6))
            
    # Risks / Watchouts
    risks = decision_data.get('risks', [])
    blocking = decision_data.get('blocking_factors', [])
    all_risks = risks + blocking
    if all_risks:
        # Deduplicate
        unique_risks = list(dict.fromkeys(all_risks))
        elements.append(Paragraph("Risks & Watchouts", heading_style))
        for risk in unique_risks:
            elements.append(Paragraph(f"• {risk}", normal_style))
            elements.append(Spacer(1, 6))

    # Details/Explanation
    explanation = decision_data.get('explanation')
    if explanation:
        elements.append(Paragraph("Detailed Context", heading_style))
        elements.append(Paragraph(explanation, normal_style))

    # Startup phased roadmap (deterministic, mirrors career roadmap in UI)
    details = decision_data.get('details') or {}
    startup_roadmap = details.get('startup_roadmap') or decision_data.get('startup_roadmap')
    if isinstance(startup_roadmap, dict):
        phases = startup_roadmap.get('phases') or []
        if phases:
            stage = startup_roadmap.get('stage', '')
            vertical = startup_roadmap.get('vertical') or {}
            vertical_label = vertical.get('label', '') if isinstance(vertical, dict) else ''
            heading = f"Startup Roadmap{f' — {stage}' if stage else ''}{f' ({vertical_label})' if vertical_label else ''}"
            elements.append(Paragraph(heading, heading_style))
            funding_plan = startup_roadmap.get('funding_plan') or {}
            if isinstance(funding_plan, dict) and funding_plan:
                burn = funding_plan.get('monthly_burn', '')
                runway = funding_plan.get('runway_months', '')
                try:
                    burn_txt = f"${int(burn):,}/mo" if burn != '' else 'N/A'
                except Exception:
                    burn_txt = str(burn)
                elements.append(Paragraph(
                    f"<b>Funding plan:</b> burn {burn_txt} | runway ~{runway} mo | "
                    f"target ${int(startup_roadmap.get('capital_target') or funding_plan.get('capital_target') or 0):,}",
                    normal_style))
                elements.append(Spacer(1, 4))
                for use in (funding_plan.get('use_of_funds') or [])[:3]:
                    elements.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;• {use}", normal_style))
                    elements.append(Spacer(1, 4))
            hiring_plan = startup_roadmap.get('hiring_plan') or []
            if hiring_plan:
                elements.append(Paragraph("<b>Hiring plan:</b>", normal_style))
                elements.append(Spacer(1, 4))
                for hire in hiring_plan[:5]:
                    if isinstance(hire, dict):
                        elements.append(Paragraph(
                            f"&nbsp;&nbsp;&nbsp;&nbsp;• {hire.get('role', '')} [{hire.get('when', '')}] — {hire.get('why', '')}",
                            normal_style))
                    else:
                        elements.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;• {hire}", normal_style))
                    elements.append(Spacer(1, 4))
            risk_flags = startup_roadmap.get('risk_flags') or []
            if risk_flags:
                risk_style = ParagraphStyle(
                    'RiskFlagStyle',
                    parent=normal_style,
                    textColor=colors.HexColor("#b91c1c"),
                    fontName='Helvetica-Bold',
                    backColor=colors.HexColor("#fef2f2"),
                    borderPadding=(6, 6, 6),
                )
                elements.append(Paragraph("CRITICAL BLOCKERS — fix before scaling:", heading_style))
                for flag in risk_flags[:5]:
                    elements.append(Paragraph(f"⛔ {flag}", risk_style))
                    elements.append(Spacer(1, 6))
            gaps = startup_roadmap.get('gaps') or []
            for gap in gaps[:4]:
                elements.append(Paragraph(f"• Gap: {gap}", normal_style))
                elements.append(Spacer(1, 6))
            for phase in phases:
                name = phase.get('phase', 'Phase')
                timeline = phase.get('timeline', '')
                focus = phase.get('focus', '')
                elements.append(Paragraph(f"<b>{name} ({timeline})</b> — {focus}", normal_style))
                elements.append(Spacer(1, 4))
                for task in (phase.get('tasks') or [])[:5]:
                    elements.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;• {task}", normal_style))
                    elements.append(Spacer(1, 4))
                exit_gate = phase.get('exit_criteria', '')
                if exit_gate:
                    elements.append(Paragraph(f"<i>Exit gate: {exit_gate}</i>", normal_style))
                    elements.append(Spacer(1, 4))
                for kpi in (phase.get('kpis') or [])[:4]:
                    elements.append(Paragraph(f"&nbsp;&nbsp;&nbsp;&nbsp;▸ KPI: {kpi}", normal_style))
                    elements.append(Spacer(1, 4))
                elements.append(Spacer(1, 2))

    doc.build(elements)
    buffer.seek(0)
    return buffer
