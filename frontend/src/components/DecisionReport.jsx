import StartupRoadmapCard from './StartupRoadmapCard'

const clampPercent = (value) => Math.max(0, Math.min(100, Math.round((value || 0) * 100)))

const normalizeOptions = (payload) => {
  const details = payload.details || {}
  if (Array.isArray(details.option_scores)) {
    return details.option_scores.map((item) => ({
      name: item.mapped_label || item.name,
      percent: typeof item.score === 'number' ? Math.round(item.score) : (typeof item.probability === 'number' ? clampPercent(item.probability) : 0),
      reason: item.reason || '',
    }))
  }
  if (Array.isArray(details.probabilities)) {
    return details.probabilities.map((item) => ({
      name: item.label,
      percent: clampPercent(item.probability),
      reason: '',
    }))
  }
  if (Array.isArray(payload.options)) {
    return payload.options.map((item) => ({
      name: item.mapped_label || item.name,
      percent: typeof item.score === 'number' ? Math.round(item.score) : (typeof item.probability === 'number' ? clampPercent(item.probability) : 0),
      reason: item.reason || '',
    }))
  }
  return []
}

const normalizeInsights = (payload) => {
  const details = payload.details || {}
  if (Array.isArray(details.explanations) && details.explanations.length) return details.explanations
  if (Array.isArray(payload.insights) && payload.insights.length) return payload.insights
  if (Array.isArray(payload.explanations) && payload.explanations.length) return payload.explanations
  return []
}

const normalizeRisks = (payload) => {
  const details = payload.details || {}
  if (Array.isArray(details.risks) && details.risks.length) {
    return details.risks.map((item) => typeof item === 'string' ? { title: 'Risk', text: item } : { title: item.path || 'Risk', text: item.risk })
  }
  if (Array.isArray(payload.risks) && payload.risks.length) {
    return payload.risks.map((item, index) => typeof item === 'string'
      ? { title: `Risk ${index + 1}`, text: item }
      : { title: item.path || `Risk ${index + 1}`, text: item.risk })
  }
  return []
}

const normalizeActions = (payload) => {
  const details = payload.details || {}
  const raw =
    (Array.isArray(details.action_plan) && details.action_plan.length ? details.action_plan : null) ||
    (Array.isArray(payload.action_plan) && payload.action_plan.length ? payload.action_plan : null) ||
    []

  // Normalize + dedupe: backend may already dedupe, but we treat UI input as untrusted.
  // This prevents "Do this first" being repeated as "Step 2" when strings are identical.
  const normalized = raw
    .map((item) => String(item || '').trim())
    .filter(Boolean)

  const unique = []
  for (const step of normalized) {
    const key = step.toLowerCase().replace(/\s+/g, ' ')
    if (!unique.some((existing) => existing.toLowerCase().replace(/\s+/g, ' ') === key)) {
      unique.push(step)
    }
  }

  return unique
}

const normalizeImpacts = (payload) => {
  const details = payload.details || {}
  if (Array.isArray(details.factor_impacts) && details.factor_impacts.length) return details.factor_impacts
  if (Array.isArray(payload.factor_impacts) && payload.factor_impacts.length) return payload.factor_impacts
  return []
}

const normalizeCareerIntel = (payload) => payload?.details?.career_intelligence || null

function RadarGlyph({ positive }) {
  return (
    <div className={`relative flex h-8 w-8 items-center justify-center rounded-xl border ${positive ? 'border-emerald-300/60 bg-emerald-400/10' : 'border-rose-300/60 bg-rose-400/10'}`}>
      <div className={`absolute h-4 w-4 rounded-full border ${positive ? 'border-emerald-300/70' : 'border-rose-300/70'}`} />
      <div className={`absolute h-2 w-2 rounded-full ${positive ? 'bg-emerald-400' : 'bg-rose-400'}`} />
    </div>
  )
}

const getSentimentVisuals = (text) => {
  const lower = String(text || '').toLowerCase();
  let val = 0; // -100 to +100
  let label = "Neutral";
  let color = "bg-slate-400";
  let textClass = "text-slate-650";
  let gradient = "from-slate-400 to-slate-500";

  if (lower.includes("strongly boosts")) {
    val = 90;
    label = "Strong Boost";
    color = "bg-emerald-500";
    textClass = "text-emerald-700";
    gradient = "from-emerald-400 to-teal-500";
  } else if (lower.includes("slightly boosts")) {
    val = 45;
    label = "Slight Boost";
    color = "bg-emerald-400";
    textClass = "text-emerald-600";
    gradient = "from-teal-300 to-emerald-400";
  } else if (lower.includes("boosts")) {
    val = 65;
    label = "Boosts";
    color = "bg-emerald-400";
    textClass = "text-emerald-600";
    gradient = "from-emerald-400 to-teal-400";
  } else if (lower.includes("strongly holds back")) {
    val = -90;
    label = "Strong Holdback";
    color = "bg-rose-500";
    textClass = "text-rose-750 font-bold";
    gradient = "from-rose-500 to-red-650";
  } else if (lower.includes("slightly holds back")) {
    val = -45;
    label = "Slight Holdback";
    color = "bg-amber-500";
    textClass = "text-amber-600";
    gradient = "from-amber-400 to-orange-505";
  } else if (lower.includes("holds back")) {
    val = -65;
    label = "Holds Back";
    color = "bg-rose-450";
    textClass = "text-rose-600";
    gradient = "from-orange-450 to-rose-500";
  }

  return { val, label, color, textClass, gradient };
}

function SentimentMeter({ text }) {
  const { val } = getSentimentVisuals(text)
  if (val === 0) return null

  const isPositive = val > 0
  const absVal = Math.abs(val)
  const pillBg = isPositive ? 'bg-emerald-100 text-emerald-700' : 'bg-rose-100 text-rose-700'

  return (
    <span className={`inline-flex items-center gap-1 mt-1.5 px-2 py-0.5 rounded-full text-[12px] font-extrabold ${pillBg}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${isPositive ? 'bg-emerald-500' : 'bg-rose-500'}`} />
      {isPositive ? `+${absVal}%` : `−${absVal}%`}
    </span>
  )
}

function VisualAlignmentBar({ label, value }) {
  const normalized = String(value || '').toLowerCase()
  let percent = 10
  let color = 'from-amber-400 to-orange-500'
  let labelText = 'Missing'
  let textColor = 'text-amber-600'
  let iconClass = 'text-amber-500'
  let icon = '⚠'
  
  if (normalized === 'match') {
    percent = 100
    color = 'from-emerald-400 to-teal-500 shadow-[0_0_8px_rgba(16,185,129,0.15)]'
    labelText = 'Match'
    textColor = 'text-emerald-700'
    iconClass = 'text-emerald-500 font-bold'
    icon = '✓'
  } else if (normalized === 'mismatch') {
    percent = 40
    color = 'from-orange-400 to-rose-500'
    labelText = 'Mismatch'
    textColor = 'text-rose-700'
    iconClass = 'text-rose-500 font-bold'
    icon = '×'
  }

  return (
    <div className="flex flex-col p-2.5 rounded-xl border border-slate-100 bg-slate-50/30">
      <div className="flex items-center justify-between text-[12px] font-bold text-slate-500 mb-1">
        <span>{label}</span>
        <span className={`font-black uppercase tracking-wider text-[14px] ${textColor} flex items-center gap-0.5`}>
          <span className={iconClass}>{icon}</span>
          <span>{labelText}</span>
        </span>
      </div>
      <div className="h-1 w-full bg-slate-200/60 rounded-full overflow-hidden">
        <div className={`h-full rounded-full bg-gradient-to-r ${color} transition-all duration-500`} style={{ width: `${percent}%` }} />
      </div>
    </div>
  )
}

function RoadmapCard({ eyebrow, title, alignment, roadmap, tone = 'slate' }) {
  const tones = {
    slate: 'border-slate-200 bg-slate-50/20',
    cyan: 'border-cyan-200/80 bg-cyan-50/20',
    rose: 'border-rose-200/80 bg-rose-50/20',
  }

  return (
    <div className={`rounded-xl border p-4 shadow-sm bg-white ${tones[tone] || tones.slate}`}>
      <div className="text-[12px] uppercase tracking-[0.22em] text-slate-400 font-bold">{eyebrow}</div>
      <div className="mt-0.5 text-base font-bold text-slate-950">{title}</div>

      {/* Visual Alignment matching bars */}
      <div className="mt-3.5 grid grid-cols-2 sm:grid-cols-4 gap-2">
        <VisualAlignmentBar label="Skills" value={alignment?.skills} />
        <VisualAlignmentBar label="Projects" value={alignment?.projects} />
        <VisualAlignmentBar label="Certs" value={alignment?.certifications} />
        <VisualAlignmentBar label="Interest" value={alignment?.interest} />
      </div>

      <div className="mt-3 grid gap-3">
        <div className="grid grid-cols-2 gap-2.5">
          {/* Skills to Add */}
          <div className="rounded-lg border border-slate-100 bg-slate-50/30 p-2">
            <span className="text-[12px] font-bold uppercase tracking-wider text-slate-400 block mb-1">Skills to add</span>
            <div className="flex flex-wrap gap-1">
              {(roadmap?.skills_to_add || []).slice(0, 4).map((item, idx) => {
                const text = typeof item === 'object' && item !== null ? item.name || item.title || JSON.stringify(item) : String(item)
                return (
                  <span key={idx} className="rounded bg-white border border-slate-100 px-1 py-0.5 text-[12px] font-bold text-slate-600">
                    {text}
                  </span>
                )
              })}
              {!(roadmap?.skills_to_add || []).length && <span className="text-[12px] text-slate-400">None</span>}
            </div>
          </div>

          {/* Certifications */}
          <div className="rounded-lg border border-slate-100 bg-slate-50/30 p-2">
            <span className="text-[12px] font-bold uppercase tracking-wider text-slate-400 block mb-1">Certifications</span>
            <div className="space-y-1">
              {(roadmap?.certifications || []).slice(0, 2).map((item, index) => {
                const text = typeof item === 'object' && item !== null ? item.name || item.title || JSON.stringify(item) : String(item)
                return (
                  <div key={index} className="text-[12px] font-bold text-slate-700" title={text}>
                    &bull; {text}
                  </div>
                )
              })}
              {!(roadmap?.certifications || []).length && <span className="text-[12px] text-slate-400">None</span>}
            </div>
          </div>
        </div>

        {/* Project Ideas */}
        <div className="rounded-lg border border-slate-100 bg-slate-50/30 p-2.5">
          <span className="text-[12px] font-bold uppercase tracking-wider text-slate-400 block mb-2">Project Ideas</span>
          <div className="grid gap-2 sm:grid-cols-2">
            {(roadmap?.project_ideas || []).slice(0, 2).map((item, index) => {
              const isObj = typeof item === 'object' && item !== null;
              return (
                <div key={index} className="rounded-lg border border-slate-100 bg-white p-2 shadow-sm">
                  <div className="text-[13px] font-bold text-slate-800">{isObj ? item.title : item}</div>
                  {isObj && (
                    <div className="mt-1 text-[12px] text-slate-500 leading-normal">
                      <span className="font-bold text-slate-600">Problem:</span> {item.problem}
                      <div className="mt-1 flex flex-wrap gap-1">
                        <span className="bg-cyan-50 text-cyan-700 px-1 rounded text-[14px] font-mono font-bold">{item.stack}</span>
                        <span className="bg-emerald-50 text-emerald-700 px-1 rounded text-[14px] font-bold">{item.impact}</span>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

function ScoreDial({ percent }) {
  const radius = 23
  const circumference = 2 * Math.PI * radius
  const val = Number(percent) || 0
  const dashOffset = circumference - (val / 100) * circumference

  return (
    <div className="relative flex h-20 w-20 shrink-0 items-center justify-center rounded-full border border-white/15 bg-white/10 shadow-[0_8px_32px_rgba(0,0,0,0.2)] backdrop-blur-md">
      <svg className="absolute inset-0 -rotate-90" viewBox="0 0 60 60" width="80" height="80">
        <circle cx="30" cy="30" r={radius} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4.5" />
        <circle
          cx="30"
          cy="30"
          r={radius}
          fill="none"
          stroke="url(#comparison-score-gradient)"
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
          strokeWidth="4.5"
          filter="url(#score-dial-glow)"
        />
        <defs>
          <filter id="score-dial-glow" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
          <linearGradient id="comparison-score-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="50%" stopColor="#34d399" />
            <stop offset="100%" stopColor="#facc15" />
          </linearGradient>
        </defs>
      </svg>
      <div className="relative z-10 text-center text-white">
        <div className="text-base font-black leading-none tracking-tight">{percent}</div>
        <div className="text-[13px] uppercase tracking-wider text-cyan-200 mt-1 font-bold">Score</div>
      </div>
    </div>
  )
}

function PanelTitle({ eyebrow, title, count, tone = 'slate' }) {
  const tones = {
    slate: 'bg-slate-100 text-slate-600',
    cyan: 'bg-cyan-50 text-cyan-700',
    rose: 'bg-rose-50 text-rose-700',
    emerald: 'bg-emerald-50 text-emerald-700',
  }

  return (
    <div className="flex items-center justify-between gap-4 border-b border-slate-100 pb-2 mb-3">
      <div>
        <div className="text-[12px] uppercase tracking-[0.15em] text-slate-400 font-extrabold">{eyebrow}</div>
        <h3 className="text-base font-extrabold text-slate-900 mt-0.5 tracking-tight">{title}</h3>
      </div>
      {count !== undefined && (
        <div className={`rounded-full px-2 py-0.5 text-[13px] font-bold ${tones[tone] || tones.slate}`}>
          {count}
        </div>
      )}
    </div>
  )
}

function ComparisonBars({ options }) {
  return (
    <div className="space-y-3">
      {options.map((option, index) => {
        const rank = index + 1
        const accent = index === 0
          ? 'from-sky-500 to-indigo-500 shadow-[0_0_12px_rgba(56,189,248,0.25)]'
          : index === 1
            ? 'from-teal-400 to-emerald-500 shadow-[0_0_12px_rgba(45,212,191,0.2)]'
            : 'from-slate-400 to-slate-600 shadow-sm'

        return (
          <div key={`${option.name}-${index}`} className="glass-panel p-3.5 rounded-2xl transition-all duration-300 hover:shadow-md hover:bg-white/90 hover:scale-[1.01] border-slate-200/60">
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-base font-extrabold ${index === 0 ? 'bg-sky-50 text-sky-700 border border-sky-100/60' : 'bg-slate-100 text-slate-600 border border-slate-200'}`}>
                    {rank}
                  </div>
                  <div>
                    <div className="text-base font-bold text-slate-900 leading-tight tracking-tight">{option.name}</div>
                    <div className="text-[12px] uppercase tracking-wider text-slate-400 font-bold mt-0.5">Path fit signal</div>
                  </div>
                </div>
                {option.reason && <div className="mt-2.5 text-[14px] leading-relaxed text-slate-600 font-bold">{option.reason}</div>}
              </div>
              <div className="shrink-0 text-right">
                <div className="text-base font-black text-slate-950">{option.percent}%</div>
                <div className="text-[12px] uppercase tracking-wider text-slate-400 font-bold">Match</div>
              </div>
            </div>
            <div className="mt-2.5">
              <div className="h-2 overflow-hidden rounded-full bg-slate-200/60">
                <div className={`report-rise h-full rounded-full bg-gradient-to-r ${accent}`} style={{ width: `${option.percent}%` }} />
              </div>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function StoryCard({ title, items, emptyText, tone }) {
  const styles = {
    insight: {
      dot: 'bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.6)]',
      numBg: 'bg-cyan-500',
      tag: 'Momentum',
      border: 'border-l-cyan-400',
    },
    risk: {
      dot: 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.6)]',
      numBg: 'bg-rose-500',
      tag: 'Watch-out',
      border: 'border-l-rose-400',
    },
    action: {
      dot: 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]',
      numBg: 'bg-emerald-500',
      tag: 'Execution',
      border: 'border-l-emerald-400',
    },
  }

  const current = styles[tone] || styles.insight

  return (
    <div className="glass-panel p-5 rounded-2xl transition-all duration-300 hover:shadow-md border border-slate-200/60 lg:col-span-3 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-4">
        <h3 className="text-base font-extrabold text-slate-900 flex items-center gap-2 tracking-tight">
          <span className={`h-3 w-3 rounded-full ${current.dot}`}></span>
          {title}
        </h3>
        <span className="text-[12px] text-slate-400 font-extrabold uppercase tracking-wider">{current.tag}</span>
      </div>
      {items.length ? (
        <div className="divide-y divide-slate-100">
          {items.map((item, index) => {
            const text = item.text || item
            return (
              <div key={index} className="flex items-start gap-2.5 py-2.5">
                <span className="shrink-0 text-[14px] font-extrabold text-slate-400 mt-px w-5 text-right">{index + 1}.</span>
                <p className="flex-1 text-slate-700 leading-relaxed text-[14px] font-bold">
                  {text} <SentimentMeter text={text} />
                </p>
              </div>
            )
          })}
        </div>
      ) : (
        <p className="text-[14px] text-slate-400 italic py-4 text-center">{emptyText}</p>
      )}
    </div>
  )
}

function ActionJourney({ actions }) {
  if (!actions.length) {
    return (
      <div className="glass-panel p-5 rounded-2xl border border-slate-200/60 bg-white lg:col-span-3 text-center py-6">
        <p className="text-[14px] text-slate-400 italic font-bold">No action plan available.</p>
      </div>
    )
  }

  return (
    <div className="glass-panel p-5 rounded-2xl border border-slate-200/60 bg-white lg:col-span-3">
      <div className="flex items-center justify-between border-b border-slate-100 pb-3 mb-5">
        <h3 className="text-base font-bold text-slate-900 flex items-center gap-2 tracking-tight">
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]"></span>
          Execution Pipeline
        </h3>
        <span className="text-[12px] text-slate-400 font-extrabold uppercase tracking-wider">Milestones</span>
      </div>
      
      <div className="relative flex flex-col md:flex-row items-stretch justify-between gap-6 md:gap-4">
        {/* Connecting line for desktop */}
        <div className="absolute top-8 left-8 right-8 h-[2px] bg-slate-100/90 hidden md:block z-0 animate-pulse" />
        
        {actions.map((action, index) => {
          const isFirst = index === 0
          const stepNum = index + 1
          
          return (
            <div key={index} className="relative z-10 flex-1 flex flex-col md:items-center text-left md:text-center p-4 rounded-xl border border-slate-150 bg-slate-50/20 shadow-sm hover:shadow-md hover:bg-white hover:border-slate-250 transition-all duration-300">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-r from-emerald-400 to-teal-500 text-white text-[14px] font-black shadow-md md:mb-3 border border-white/20">
                {stepNum}
              </div>
              <div className="mt-2 md:mt-0">
                <span className="text-[12px] font-black uppercase tracking-widest text-slate-400 block mb-1">
                  {isFirst ? 'Priority Action' : `Step ${stepNum}`}
                </span>
                <p className="text-slate-700 leading-relaxed text-[14px] font-bold mx-auto">
                  {typeof action === 'object' && action !== null ? action.text || action.action || action.title || JSON.stringify(action) : String(action)}
                </p>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function DecisionReport({ payload, interactiveFields, onInteractiveChange, isLiveUpdating, onRefresh, onDownload }) {
  const options = normalizeOptions(payload)
  const insights = normalizeInsights(payload)
  const risks = normalizeRisks(payload)
  const actions = normalizeActions(payload)
  const impacts = normalizeImpacts(payload)
  const realityCheck = payload.reality_check || ''
  const projectIdeas = payload.project_ideas || []
  const careerIntel = normalizeCareerIntel(payload)
  const startupRoadmap = payload?.details?.startup_roadmap || null
  const bestPercent = typeof payload.score === 'number'
    ? Math.round(payload.score)
    : (options[0]?.percent || 0)
  const confidence = typeof payload.confidence === 'number'
    ? Math.round(payload.confidence)
    : clampPercent(payload.probability)
  const whatIf = payload.what_if || payload.details?.what_if || ''
  const sliders = Array.isArray(interactiveFields) ? interactiveFields : []
  const showSliders = Boolean(sliders.length && typeof onInteractiveChange === 'function')

  return (
    <div className="space-y-4">
      {/* Sleek, Compact Decision Signal Board Header */}
      <div className="relative overflow-hidden rounded-2xl bg-[radial-gradient(ellipse_at_top_left,_var(--tw-gradient-stops))] from-slate-900 via-slate-950 to-indigo-950 p-5 text-white shadow-xl border border-slate-800">
        {/* Visual mesh glow helpers */}
        <div className="absolute top-0 right-0 -mt-8 -mr-8 h-40 w-40 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none"></div>
        <div className="absolute bottom-0 left-1/3 -mb-10 h-32 w-32 rounded-full bg-indigo-500/10 blur-2xl pointer-events-none"></div>

        <div className="relative z-10 flex items-center justify-between gap-4 border-b border-white/10 pb-4">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex rounded-full border border-white/15 bg-white/10 px-2.5 py-0.5 text-[12px] uppercase tracking-[0.15em] text-cyan-300 font-extrabold shadow-sm">
                Decision Signal Board
              </span>
              {typeof onDownload === 'function' && (
                <button
                  onClick={onDownload}
                  className="inline-flex items-center gap-1 rounded-full border border-white/20 bg-white/10 px-2.5 py-0.5 text-[12px] font-bold uppercase tracking-wider text-white transition hover:bg-white/20 hover:scale-[1.02] shadow-sm"
                >
                  <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  PDF
                </button>
              )}
            </div>
            <h2 className="mt-2 text-xl font-extrabold tracking-tight leading-snug">{payload.decision}</h2>
            <p className="mt-1 text-base text-slate-300 font-bold">{payload.summary}</p>
          </div>
          <ScoreDial percent={bestPercent} />
        </div>

        {/* Secondary Metrics Horizontal Grid Row */}
        <div className="relative z-10 grid grid-cols-3 gap-4 pt-4 text-white/90">
          <div className="flex flex-col">
            <span className="text-[12px] font-extrabold uppercase tracking-[0.15em] text-cyan-300">Confidence</span>
            <span className="text-base font-extrabold mt-1 tracking-tight text-white">{confidence}%</span>
          </div>
          <div className="flex flex-col border-l border-white/10 pl-4">
            <span className="text-[12px] font-extrabold uppercase tracking-[0.15em] text-emerald-300">Top Path</span>
            <span className="text-base font-extrabold mt-1 tracking-tight text-white">{options[0]?.name || payload.decision}</span>
          </div>
          <div className="flex flex-col border-l border-white/10 pl-4">
            <span className="text-[12px] font-extrabold uppercase tracking-[0.15em] text-amber-300">Next Move</span>
            <span className="text-base font-extrabold mt-1 tracking-tight text-white">
              {(() => {
                const next = String(payload.next_step || '').trim()
                const first = String(actions[0] || '').trim()
                if (next && first && next.toLowerCase() === first.toLowerCase()) return first
                return first || next || 'Review factors'
              })()}
            </span>
          </div>
        </div>
      </div>

      {/* Bento Grid layout */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 items-start">
        {/* Option Comparison Card */}
        <div className="glass-panel p-5 rounded-2xl md:col-span-2 shadow-md">
          <PanelTitle eyebrow="Path ranking" title="Option comparison" count={`${options.length} options`} tone="cyan" />
          <ComparisonBars options={options} />
        </div>

        {/* Live Slider controls */}
        {showSliders && (
          <div className="glass-panel p-5 rounded-2xl shadow-md">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3.5">
              <div>
                <span className="text-[12px] uppercase tracking-[0.15em] text-slate-400 font-extrabold">What-if</span>
                <h3 className="text-base font-extrabold text-slate-900 mt-0.5 tracking-tight">Live Sliders</h3>
              </div>
              {typeof onRefresh === 'function' && (
                <button
                  type="button"
                  onClick={onRefresh}
                  className="text-[13px] font-bold text-sky-600 hover:text-sky-850 transition duration-200"
                >
                  {isLiveUpdating ? 'Updating...' : 'Refresh'}
                </button>
              )}
            </div>
            <div className="space-y-3 pr-1">
              {sliders.map((field) => (
                <div key={field.name} className="rounded-xl border border-slate-100 bg-white/50 p-3 shadow-sm hover:shadow-md transition-all duration-300">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-[14px] font-bold text-slate-700">{field.label}</span>
                    <span className="text-[14px] font-extrabold text-sky-600 bg-sky-50 px-1.5 py-0.5 rounded">{field.value ?? field.range?.min ?? 0}</span>
                  </div>
                  <input
                    type="range"
                    min={field.range?.min}
                    max={field.range?.max}
                    step={field.range?.step || 1}
                    value={field.value ?? field.range?.min ?? 0}
                    onChange={(event) => onInteractiveChange(field.name, Number(event.target.value))}
                    className="mt-2 w-full h-1 bg-slate-200/80 rounded-lg appearance-none cursor-pointer accent-sky-500 hover:accent-sky-600 transition-all"
                  />
                  <div className="mt-1 flex justify-between text-[12px] text-slate-400 font-bold">
                    <span>{field.range?.min}</span>
                    <span>{field.range?.max}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Insights drivers */}
        <StoryCard
          title="Insights"
          items={insights.map((item) => ({ text: item }))}
          emptyText="No model insights available."
          tone="insight"
        />

        {/* Risks list */}
        <StoryCard
          title="Risks"
          items={risks}
          emptyText="No major risks surfaced."
          tone="risk"
        />

        {/* Action checklist */}
        <ActionJourney actions={actions} />

        {/* Factor Impact Signals map */}
        <div className="rounded-xl border border-slate-200/60 bg-white p-4 shadow-sm lg:col-span-3">
          <PanelTitle eyebrow="Model trace" title="Factor impact" count="Signal map" tone="slate" />
          <div className="grid gap-3 grid-cols-1 sm:grid-cols-2 lg:grid-cols-4">
            {impacts.length ? impacts.slice(0, 4).map((item, index) => {
              const rawValue = Number(item.value)
              const strength = Number.isFinite(rawValue) ? Math.max(Math.min(Math.abs(rawValue) * 100, 100), 8) : 20
              const positive = Number.isFinite(rawValue) ? rawValue >= 0 : !String(item.impact || '').toLowerCase().includes('holds back')

              return (
                <div key={index} className="rounded-lg border border-slate-100 bg-slate-50/30 p-2.5 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[14px] font-bold text-slate-800" title={item.factor}>{item.factor}</span>
                      <span className={`text-[12px] font-bold px-1.5 py-0.5 rounded ${positive ? 'bg-emerald-50 text-emerald-700' : 'bg-rose-50 text-rose-700'}`}>
                        {positive ? 'Positive' : 'Negative'}
                      </span>
                    </div>
                    <p className="text-[13px] text-slate-500 mt-1 leading-normal" title={item.impact}>{item.impact}</p>
                  </div>
                  <div className="mt-3">
                    <div className="h-1.5 w-full bg-slate-200 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${positive ? 'bg-gradient-to-r from-emerald-400 to-teal-500' : 'bg-gradient-to-r from-orange-400 to-rose-500'}`}
                        style={{ width: `${strength}%` }}
                      />
                    </div>
                  </div>
                </div>
              )
            }) : (
              <div className="rounded-lg bg-slate-50 p-3 text-base text-slate-400 italic text-center sm:col-span-2 lg:col-span-4">No factor impact data available.</div>
            )}
          </div>
        </div>

        {/* Reality check perspective */}
        {realityCheck && (
          <div className="rounded-xl border border-rose-100 bg-rose-50/50 p-3.5 shadow-sm lg:col-span-3">
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-rose-100 text-rose-600">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
              </div>
              <div>
                <span className="text-[12px] font-bold uppercase tracking-wider text-rose-500">Auditor Perspective / Reality Check</span>
                <p className="text-base italic leading-relaxed text-slate-700 mt-0.5">"{realityCheck}"</p>
              </div>
            </div>
          </div>
        )}

        {/* Scenario lab scenario details */}
        {whatIf && (
          <div className="rounded-xl border border-amber-100 bg-amber-50/50 p-3.5 shadow-sm lg:col-span-3">
            <div className="flex items-start gap-3">
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-amber-100 text-amber-700 font-extrabold text-base">
                W
              </div>
              <div>
                <span className="text-[12px] font-bold uppercase tracking-wider text-amber-600">Scenario Lab / What-if Scenario</span>
                <p className="text-base text-amber-950/90 mt-0.5 leading-relaxed">{whatIf}</p>
              </div>
            </div>
          </div>
        )}

        {/* Project Ideas for mentorship */}
        {projectIdeas.length > 0 && (
          <div className="rounded-xl border border-slate-200/60 bg-white p-4 shadow-sm lg:col-span-3">
            <PanelTitle eyebrow="Mentorship" title="High-Quality Project Ideas" count={projectIdeas.length} tone="cyan" />
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {projectIdeas.slice(0, 3).map((idea, idx) => (
                <div key={idx} className="flex flex-col justify-between rounded-lg border border-slate-100 bg-slate-50/40 p-3 shadow-sm">
                  <div>
                    <h4 className="text-base font-bold text-slate-900">{idea.title}</h4>
                    <div className="mt-2 space-y-1">
                      <span className="text-[14px] font-bold uppercase text-slate-400">Problem</span>
                      <p className="text-[13px] text-slate-500 leading-normal">{idea.problem}</p>
                    </div>
                  </div>
                  <div className="mt-3 pt-2 border-t border-slate-100">
                    <span className="text-[14px] font-mono text-cyan-600 bg-cyan-50/50 px-1 py-0.5 rounded font-bold block mb-1">{idea.stack}</span>
                    <span className="inline-flex rounded bg-emerald-50 text-emerald-700 px-1 py-0.5 text-[12px] font-bold">
                      Impact: {idea.impact}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Career roadmap track details */}
        {careerIntel?.best_fit && careerIntel?.interest && (
          <div className="rounded-xl border border-slate-200/60 bg-white p-4 shadow-sm lg:col-span-3">
            <PanelTitle
              eyebrow="Decision clarity"
              title="Roadmap (Best Fit vs Interest)"
              count={careerIntel.recommended_view === 'dual_track' ? 'Dual track' : 'Single track'}
              tone="slate"
            />
            {Array.isArray(careerIntel.difference) && careerIntel.difference.length > 0 && (
              <div className="mt-2 rounded-lg border border-slate-100 bg-slate-50/50 p-2.5 text-base text-slate-600 leading-normal">
                {careerIntel.difference.slice(0, 2).map((line, index) => (
                  <div key={index}>{line}</div>
                ))}
              </div>
            )}
            {careerIntel.recommended_view === 'dual_track' ? (
              <div className="mt-4 grid gap-4 sm:grid-cols-2">
                <RoadmapCard
                  eyebrow="Best fit (current)"
                  title={careerIntel.best_fit.path_label || 'Best fit'}
                  alignment={careerIntel.best_fit.alignment}
                  roadmap={careerIntel.best_fit.roadmap}
                  tone="cyan"
                />
                <RoadmapCard
                  eyebrow="Interest track (target)"
                  title={careerIntel.interest.path_label || 'Interest track'}
                  alignment={careerIntel.interest.alignment}
                  roadmap={careerIntel.interest.roadmap}
                  tone="rose"
                />
              </div>
            ) : (
              <div className="mt-4">
                <RoadmapCard
                  eyebrow="Single track"
                  title={careerIntel.best_fit.path_label || payload.decision || 'Roadmap'}
                  alignment={careerIntel.best_fit.alignment}
                  roadmap={careerIntel.best_fit.roadmap}
                  tone="cyan"
                />
              </div>
            )}
          </div>
        )}

        {/* Startup phased execution roadmap */}
        {startupRoadmap?.phases && (
          <StartupRoadmapCard roadmap={startupRoadmap} />
        )}
      </div>
    </div>
  )
}
