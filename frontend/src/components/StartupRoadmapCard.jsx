import { useEffect, useMemo, useState } from 'react'

const STATUS_STYLE = {
  match: { bar: 'from-emerald-400 to-teal-500', text: 'text-emerald-700', label: 'Ready', icon: '✓', width: '100%' },
  partial: { bar: 'from-amber-400 to-orange-500', text: 'text-amber-700', label: 'Partial', icon: '◐', width: '55%' },
  mismatch: { bar: 'from-rose-400 to-rose-600', text: 'text-rose-700', label: 'Gap', icon: '×', width: '30%' },
  missing: { bar: 'from-slate-300 to-slate-400', text: 'text-slate-500', label: 'Missing', icon: '⚠', width: '12%' },
}

function currencySymbol(currency) {
  return String(currency || 'USD').toUpperCase() === 'INR' ? '₹' : '$'
}

function formatMoney(amount, currency) {
  const symbol = currencySymbol(currency)
  return `${symbol}${Number(amount || 0).toLocaleString()}`
}

// Stable signature of the plan content — progress resets when the plan changes.
function planSignature(roadmap) {
  const payload = JSON.stringify({
    p: (roadmap.phases || []).map((ph) => [ph.phase, ph.timeline, ph.tasks]),
    w: roadmap.next_7_days || [],
  })
  let hash = 5381
  for (let i = 0; i < payload.length; i += 1) {
    hash = ((hash << 5) + hash + payload.charCodeAt(i)) >>> 0
  }
  return hash.toString(36)
}

function ReadinessBar({ label, info }) {
  const status = STATUS_STYLE[info?.status] || STATUS_STYLE.missing
  return (
    <div className="flex flex-col p-2.5 rounded-xl border border-slate-100 bg-white">
      <div className="flex items-center justify-between text-[12px] font-bold text-slate-500 mb-1">
        <span className="capitalize">{label}</span>
        <span className={`font-black uppercase tracking-wider text-[13px] ${status.text} flex items-center gap-1`}>
          <span>{status.icon}</span>
          <span>{status.label}</span>
        </span>
      </div>
      <div className="text-[12px] font-bold text-slate-700 leading-snug mb-1.5">{info?.label || '—'}</div>
      <div className="h-1 w-full bg-slate-200/60 rounded-full overflow-hidden">
        <div className={`h-full rounded-full bg-gradient-to-r ${status.bar} transition-all duration-500`} style={{ width: status.width }} />
      </div>
    </div>
  )
}

export default function StartupRoadmapCard({ roadmap }) {
  const [copied, setCopied] = useState(false)
  const [resetFlash, setResetFlash] = useState(false)

  // Hooks must run unconditionally — derive a safe roadmap before any early return.
  const safeRoadmap = roadmap && typeof roadmap === 'object' ? roadmap : {}
  const storageKey = `decixai_startup_roadmap_progress_${planSignature(safeRoadmap)}`
  const [completed, setCompleted] = useState(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      return saved ? JSON.parse(saved) : {}
    } catch {
      return {}
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(completed))
    } catch {}
  }, [completed, storageKey])

  // Live what-if sliders regenerate the plan → new signature → reload that
  // plan's saved progress instead of carrying the old plan's checks over.
  useEffect(() => {
    try {
      const saved = localStorage.getItem(storageKey)
      const parsed = saved ? JSON.parse(saved) : {}
      setCompleted(parsed && typeof parsed === 'object' ? parsed : {})
    } catch {
      setCompleted({})
    }
  }, [storageKey])

  const phases = Array.isArray(safeRoadmap.phases) ? safeRoadmap.phases : []
  const gaps = Array.isArray(safeRoadmap.gaps) ? safeRoadmap.gaps : []
  const riskFlags = Array.isArray(safeRoadmap.risk_flags) ? safeRoadmap.risk_flags : []
  const milestones = Array.isArray(safeRoadmap.milestones_30_60_90) ? safeRoadmap.milestones_30_60_90 : []
  const readiness = safeRoadmap.readiness || {}
  const hiringPlan = Array.isArray(safeRoadmap.hiring_plan) ? safeRoadmap.hiring_plan : []
  const fundingPlan = safeRoadmap.funding_plan || null
  const vertical = safeRoadmap.vertical || null
  const next7Days = Array.isArray(safeRoadmap.next_7_days) ? safeRoadmap.next_7_days : []
  const weeklyCadence = Array.isArray(safeRoadmap.weekly_cadence) ? safeRoadmap.weekly_cadence : []
  const burnCheckpoints = Array.isArray(safeRoadmap.burn_checkpoints) ? safeRoadmap.burn_checkpoints : []
  const currency = fundingPlan?.burn_currency || safeRoadmap.currency || 'USD'
  if (!phases.length) return null

  const taskId = (prefix, i) => `${prefix}${i}`
  const toggleTask = (id) =>
    setCompleted((prev) => {
      const next = { ...prev }
      if (next[id]) delete next[id]
      else next[id] = true
      return next
    })

  const phaseProgress = useMemo(
    () =>
      phases.map((phase, pIdx) => {
        const tasks = Array.isArray(phase.tasks) ? phase.tasks : []
        const done = tasks.filter((_, tIdx) => completed[taskId(`p${pIdx}-`, tIdx)]).length
        return { done, total: tasks.length, pct: tasks.length ? Math.round((done / tasks.length) * 100) : 0 }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [phases, completed]
  )

  const weekDone = next7Days.filter((_, i) => completed[taskId('w', i)]).length
  const totalTasks = phaseProgress.reduce((acc, p) => acc + p.total, 0)
  const doneTasks = phaseProgress.reduce((acc, p) => acc + p.done, 0)
  const overallPct = totalTasks ? Math.round((doneTasks / totalTasks) * 100) : 0

  const handleResetProgress = () => {
    setCompleted({})
    setResetFlash(true)
    setTimeout(() => setResetFlash(false), 1400)
  }

  const handleCopy = async () => {
    const lines = [
      `Startup Roadmap — ${roadmap.stage || 'Execution plan'}${vertical?.label ? ` (${vertical.label})` : ''}`,
      fundingPlan ? `Runway ~${fundingPlan.runway_months} mo | Burn ${formatMoney(fundingPlan.monthly_burn, currency)}/mo | Target ${formatMoney(roadmap.capital_target || fundingPlan.capital_target, currency)}` : '',
      '',
      ...next7Days.map((t) => `• This week: ${t}`),
      '',
      ...phases.flatMap((p, i) => [
        `${i + 1}. ${p.phase} (${p.timeline}) — ${p.focus}${p.owner ? ` [${p.owner}]` : ''}`,
        ...(Array.isArray(p.tasks) ? p.tasks.map((t) => `   • ${t}`) : []),
        ...(Array.isArray(p.kpis) && p.kpis.length ? [`   KPIs: ${p.kpis.join(' | ')}`] : []),
        `   Exit: ${p.exit_criteria || ''}`,
        '',
      ]),
      hiringPlan.length ? `Hiring: ${hiringPlan.map((h) => `${h.role} [${h.when}]`).join('; ')}` : '',
    ].filter(Boolean).join('\n')
    try {
      await navigator.clipboard.writeText(lines)
      setCopied(true)
      setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  return (
    <div className="rounded-xl border border-fuchsia-200/60 bg-white p-4 shadow-sm col-span-1 lg:col-span-3">
      {/* Header + overall progress */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-100 pb-3 mb-3">
        <h3 className="text-base font-bold text-slate-900 flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-fuchsia-500" />
          Startup Roadmap — {roadmap.stage || 'Execution plan'}
          {vertical?.label && (
            <span className="ml-1 rounded-full bg-fuchsia-50 border border-fuchsia-200 px-2 py-0.5 text-[11px] font-bold text-fuchsia-700">
              {vertical.label}
            </span>
          )}
        </h3>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 min-w-[180px]">
            <div className="h-2 flex-1 bg-slate-200/70 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full bg-gradient-to-r from-fuchsia-500 to-indigo-500 transition-all duration-500"
                style={{ width: `${overallPct}%` }}
              />
            </div>
            <span className="text-[12px] font-black text-slate-700 tabular-nums whitespace-nowrap">
              {doneTasks}/{totalTasks} · {overallPct}%
            </span>
          </div>
          <span className="text-[12px] text-slate-400 font-bold uppercase tracking-wider hidden sm:inline">
            {roadmap.runway_months != null ? `~${roadmap.runway_months} mo runway` : 'Phased plan'}
          </span>
          <button
            type="button"
            onClick={handleCopy}
            className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-bold text-slate-600 hover:border-fuchsia-300 hover:text-fuchsia-700 transition cursor-pointer"
          >
            {copied ? 'Copied ✓' : 'Copy plan'}
          </button>
          <button
            type="button"
            onClick={handleResetProgress}
            title="Clear checked tasks for this plan"
            className="rounded-lg border border-slate-200 bg-white px-2 py-1 text-[11px] font-bold text-slate-600 hover:border-rose-300 hover:text-rose-700 transition cursor-pointer"
          >
            {resetFlash ? 'Reset ✓' : 'Reset'}
          </button>
        </div>
      </div>

      {fundingPlan && (
        <div className="mb-3 grid gap-2 sm:grid-cols-3">
          <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-2 text-[12px]">
            <span className="block text-[10px] font-black uppercase tracking-widest text-slate-400">Monthly burn</span>
            <span className="text-[14px] font-black text-slate-800">{formatMoney(fundingPlan.monthly_burn, currency)}/mo</span>
          </div>
          <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-2 text-[12px]">
            <span className="block text-[10px] font-black uppercase tracking-widest text-slate-400">Capital target</span>
            <span className="text-[14px] font-black text-slate-800">{formatMoney(roadmap.capital_target || fundingPlan.capital_target, currency)}</span>
          </div>
          <div className="rounded-lg border border-slate-100 bg-slate-50/50 p-2 text-[12px]">
            <span className="block text-[10px] font-black uppercase tracking-widest text-slate-400">Use of funds</span>
            <span className="text-[12px] font-bold text-slate-600">60% hires / 25% traction / 15% buffer</span>
          </div>
        </div>
      )}

      {burnCheckpoints.length > 0 && (
        <div className="mb-3 grid gap-2 sm:grid-cols-3">
          {burnCheckpoints.map((c, i) => (
            <div key={i} className="rounded-lg border border-orange-100 bg-orange-50/40 p-2 text-[12px]">
              <span className="block text-[10px] font-black uppercase tracking-widest text-orange-500">{c.checkpoint} spend ceiling</span>
              <span className="text-[14px] font-black text-slate-800">{formatMoney(c.expected_spend, currency)}</span>
              <span className="block text-[11px] font-bold text-slate-500 leading-snug mt-0.5">Gate: {c.gate}</span>
            </div>
          ))}
        </div>
      )}

      {hiringPlan.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1.5">
          {hiringPlan.map((h, i) => (
            <span key={i} title={h.why || ''} className="rounded-full bg-indigo-50 border border-indigo-100 px-2.5 py-1 text-[12px] font-bold text-indigo-800">
              👥 {typeof h === 'string' ? h : `${h.role} · ${h.when || ''}`}
            </span>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 mb-3">
        <ReadinessBar label="Capital" info={readiness.capital} />
        <ReadinessBar label="Team" info={readiness.team} />
        <ReadinessBar label="Experience" info={readiness.experience} />
        <ReadinessBar label="Market" info={readiness.market} />
      </div>

      {riskFlags.length > 0 && (
        <div className="mb-3 rounded-lg border border-rose-200 bg-rose-50/60 p-2.5 text-[13px] text-rose-900 leading-relaxed">
          <span className="font-black uppercase tracking-wider text-[11px] text-rose-600 block mb-1">⛔ Critical blockers</span>
          {riskFlags.map((flag, i) => (
            <div key={i} className="font-bold">• {flag}</div>
          ))}
        </div>
      )}

      {gaps.length > 0 && (
        <div className="mb-3 rounded-lg border border-amber-100 bg-amber-50/50 p-2.5 text-[13px] text-amber-900 leading-relaxed">
          <span className="font-black uppercase tracking-wider text-[11px] text-amber-600 block mb-1">Key gaps</span>
          {gaps.slice(0, 3).map((gap, i) => (
            <div key={i}>• {gap}</div>
          ))}
        </div>
      )}

      {/* This week — immediate actions */}
      {next7Days.length > 0 && (
        <div className="mb-3 rounded-xl border border-emerald-100 bg-emerald-50/40 p-3">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] font-black uppercase tracking-widest text-emerald-600">🗓 Start this week</span>
            <span className="text-[11px] font-black text-emerald-700 tabular-nums">
              {weekDone}/{next7Days.length} done
            </span>
          </div>
          <ul className="space-y-1">
            {next7Days.map((task, i) => {
              const id = taskId('w', i)
              const checked = Boolean(completed[id])
              return (
                <li key={id}>
                  <label className="flex items-start gap-2 text-[13px] text-slate-700 leading-snug cursor-pointer group">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleTask(id)}
                      className="mt-0.5 h-4 w-4 shrink-0 cursor-pointer accent-emerald-600"
                    />
                    <span className={checked ? 'line-through text-slate-400' : 'group-hover:text-slate-900 transition'}>{task}</span>
                  </label>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      {/* Phases with checkable tasks */}
      <div className="relative grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="absolute top-8 left-8 right-8 h-[2px] bg-fuchsia-100/80 hidden xl:block" />
        {phases.map((phase, index) => {
          const tasks = Array.isArray(phase.tasks) ? phase.tasks : []
          const progress = phaseProgress[index]
          const phaseDone = progress.total > 0 && progress.done === progress.total
          const deliverables = Array.isArray(phase.deliverables) ? phase.deliverables : []
          return (
          <div
            key={index}
            className={`relative rounded-xl border p-3.5 shadow-sm hover:shadow-md transition-all ${
              phaseDone ? 'border-emerald-200 bg-emerald-50/30' : 'border-slate-150 bg-slate-50/30 hover:bg-white'
            }`}
          >
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-full text-white text-[13px] font-black shadow ${
                  phaseDone ? 'bg-gradient-to-r from-emerald-500 to-teal-500' : 'bg-gradient-to-r from-fuchsia-500 to-indigo-500'
                }`}
              >
                {phaseDone ? '✓' : index + 1}
              </span>
              <span className="text-[11px] font-black uppercase tracking-widest text-fuchsia-600 bg-fuchsia-50 border border-fuchsia-100 rounded-full px-2 py-0.5">
                {phase.timeline}
              </span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] font-black uppercase tracking-widest text-slate-400">{phase.phase}</div>
              {phase.owner && (
                <div className="text-[10px] font-black uppercase tracking-wider text-indigo-600 bg-indigo-50 border border-indigo-100 rounded-full px-1.5 py-0.5">
                  {phase.owner}
                </div>
              )}
            </div>
            <div className="text-[14px] font-bold text-slate-900 leading-snug mt-0.5">{phase.focus}</div>

            {/* Per-phase progress */}
            <div className="mt-2 flex items-center gap-2">
              <div className="h-1.5 flex-1 bg-slate-200/70 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    phaseDone ? 'bg-gradient-to-r from-emerald-400 to-teal-500' : 'bg-gradient-to-r from-fuchsia-400 to-indigo-400'
                  }`}
                  style={{ width: `${progress.pct}%` }}
                />
              </div>
              <span className="text-[11px] font-black text-slate-500 tabular-nums">
                {progress.done}/{progress.total}
              </span>
            </div>

            <ul className="mt-2 space-y-1.5">
              {tasks.map((task, tIdx) => {
                const id = taskId(`p${index}-`, tIdx)
                const checked = Boolean(completed[id])
                return (
                  <li key={id}>
                    <label className="flex items-start gap-1.5 text-[13px] text-slate-600 leading-snug cursor-pointer group">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleTask(id)}
                        className="mt-0.5 h-3.5 w-3.5 shrink-0 cursor-pointer accent-fuchsia-600"
                      />
                      <span className={checked ? 'line-through text-slate-400' : 'group-hover:text-slate-900 transition'}>{task}</span>
                    </label>
                  </li>
                )
              })}
            </ul>

            {deliverables.length > 0 && (
              <div className="mt-2.5 rounded-lg bg-violet-50/70 border border-violet-100 p-2 text-[12px] text-violet-900 leading-snug">
                <span className="font-black uppercase tracking-wider text-[10px] text-violet-600 block">Deliverables</span>
                {deliverables.map((d, dIdx) => (
                  <div key={dIdx}>📦 {d}</div>
                ))}
              </div>
            )}

            {phase.exit_criteria && (
              <div className="mt-2 rounded-lg bg-emerald-50/70 border border-emerald-100 p-2 text-[12px] text-emerald-900 leading-snug">
                <span className="font-black uppercase tracking-wider text-[10px] text-emerald-600 block">Exit gate</span>
                {phase.exit_criteria}
              </div>
            )}
            {Array.isArray(phase.kpis) && phase.kpis.length > 0 && (
              <div className="mt-2 rounded-lg bg-sky-50/70 border border-sky-100 p-2 text-[12px] text-sky-900 leading-snug">
                <span className="font-black uppercase tracking-wider text-[10px] text-sky-600 block">KPIs to hit</span>
                {phase.kpis.map((kpi, kIdx) => (
                  <div key={kIdx}>▸ {kpi}</div>
                ))}
              </div>
            )}
          </div>
          )
        })}
      </div>

      {/* Weekly operating cadence */}
      {weeklyCadence.length > 0 && (
        <div className="mt-3 rounded-xl border border-sky-100 bg-sky-50/40 p-3">
          <span className="text-[11px] font-black uppercase tracking-widest text-sky-600">🔁 Weekly cadence</span>
          <div className="mt-1.5 grid gap-1 sm:grid-cols-2">
            {weeklyCadence.map((item, i) => (
              <div key={i} className="text-[12px] font-bold text-slate-600 leading-snug">• {item}</div>
            ))}
          </div>
        </div>
      )}

      {milestones.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {milestones.map((milestone, i) => (
            <span key={i} className="rounded-full bg-slate-900 text-white px-2.5 py-1 text-[12px] font-bold">
              {milestone}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
