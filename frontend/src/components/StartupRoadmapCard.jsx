import { useState } from 'react'

const STATUS_STYLE = {
  match: { bar: 'from-emerald-400 to-teal-500', text: 'text-emerald-700', label: 'Ready', icon: '✓', width: '100%' },
  partial: { bar: 'from-amber-400 to-orange-500', text: 'text-amber-700', label: 'Partial', icon: '◐', width: '55%' },
  mismatch: { bar: 'from-rose-400 to-rose-600', text: 'text-rose-700', label: 'Gap', icon: '×', width: '30%' },
  missing: { bar: 'from-slate-300 to-slate-400', text: 'text-slate-500', label: 'Missing', icon: '⚠', width: '12%' },
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
  const [expandedPhases, setExpandedPhases] = useState({})
  if (!roadmap || typeof roadmap !== 'object') return null
  const phases = Array.isArray(roadmap.phases) ? roadmap.phases : []
  const gaps = Array.isArray(roadmap.gaps) ? roadmap.gaps : []
  const riskFlags = Array.isArray(roadmap.risk_flags) ? roadmap.risk_flags : []
  const milestones = Array.isArray(roadmap.milestones_30_60_90) ? roadmap.milestones_30_60_90 : []
  const readiness = roadmap.readiness || {}
  if (!phases.length) return null

  const togglePhase = (index) =>
    setExpandedPhases((prev) => ({ ...prev, [index]: !prev[index] }))

  return (
    <div className="rounded-xl border border-fuchsia-200/60 bg-white p-4 shadow-sm col-span-1 lg:col-span-3">
      <div className="flex items-center justify-between border-b border-slate-100 pb-2 mb-3">
        <h3 className="text-base font-bold text-slate-900 flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-fuchsia-500" />
          Startup Roadmap — {roadmap.stage || 'Execution plan'}
        </h3>
        <span className="text-[12px] text-slate-400 font-bold uppercase tracking-wider">
          {roadmap.runway_months != null ? `~${roadmap.runway_months} mo runway` : 'Phased plan'}
        </span>
      </div>

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

      <div className="relative grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div className="absolute top-8 left-8 right-8 h-[2px] bg-fuchsia-100/80 hidden xl:block" />
        {phases.map((phase, index) => {
          const tasks = Array.isArray(phase.tasks) ? phase.tasks : []
          const expanded = Boolean(expandedPhases[index])
          const visibleTasks = expanded ? tasks : tasks.slice(0, 3)
          return (
          <div key={index} className="relative rounded-xl border border-slate-150 bg-slate-50/30 p-3.5 shadow-sm hover:shadow-md hover:bg-white transition-all">
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <span className="flex h-7 w-7 items-center justify-center rounded-full bg-gradient-to-r from-fuchsia-500 to-indigo-500 text-white text-[13px] font-black shadow">
                {index + 1}
              </span>
              <span className="text-[11px] font-black uppercase tracking-widest text-fuchsia-600 bg-fuchsia-50 border border-fuchsia-100 rounded-full px-2 py-0.5">
                {phase.timeline}
              </span>
            </div>
            <div className="text-[11px] font-black uppercase tracking-widest text-slate-400">{phase.phase}</div>
            <div className="text-[14px] font-bold text-slate-900 leading-snug mt-0.5">{phase.focus}</div>
            <ul className="mt-2 space-y-1.5">
              {visibleTasks.map((task, tIdx) => (
                <li key={tIdx} className="flex items-start gap-1.5 text-[13px] text-slate-600 leading-snug">
                  <span className="mt-1 h-1.5 w-1.5 rounded-full bg-fuchsia-400 shrink-0" />
                  <span>{task}</span>
                </li>
              ))}
            </ul>
            {tasks.length > 3 && (
              <button
                type="button"
                onClick={() => togglePhase(index)}
                className="mt-2 text-[12px] font-black uppercase tracking-wider text-fuchsia-600 hover:text-fuchsia-800 transition cursor-pointer"
              >
                {expanded ? 'Show less ↑' : `Show all tasks (${tasks.length}) ↓`}
              </button>
            )}
            {phase.exit_criteria && (
              <div className="mt-2.5 rounded-lg bg-emerald-50/70 border border-emerald-100 p-2 text-[12px] text-emerald-900 leading-snug">
                <span className="font-black uppercase tracking-wider text-[10px] text-emerald-600 block">Exit gate</span>
                {phase.exit_criteria}
              </div>
            )}
          </div>
          )
        })}
      </div>

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
