import React from 'react'
import { STARTUP_PRESETS } from './startupConfig'

export default function StartupForm({
  input,
  setInput,
  fieldErrors = {},
  onSubmit,
  loading,
  onApplyPreset,
}) {
  const handleChange = (field, value) => {
    setInput((prev) => ({ ...prev, [field]: value }))
  }

  const handleNumericChange = (field, value) => {
    setInput((prev) => ({ ...prev, [field]: value === '' ? '' : Number(value) }))
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      {/* Quick Presets */}
      <div className="space-y-1.5">
        <span className="text-[10px] font-black uppercase tracking-wider text-slate-400 block">
          Venture Profiles
        </span>
        <div className="flex flex-wrap gap-1.5">
          {STARTUP_PRESETS.map((preset, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => onApplyPreset(preset)}
              className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-2.5 py-1 text-[11px] font-bold text-slate-700 hover:border-sky-400 hover:bg-sky-50 hover:text-sky-700 transition shadow-2xs cursor-pointer active:scale-95"
            >
              <span className="text-[9px] uppercase px-1 py-0.5 rounded bg-slate-100 text-slate-500 font-extrabold">
                {preset.badge}
              </span>
              <span>{preset.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Inputs */}
      <div className="space-y-3.5 max-h-[55vh] overflow-y-auto pr-1">
        {/* Funding */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-3.5 shadow-2xs">
          <label className="text-[11px] font-black uppercase tracking-wider text-slate-700 block mb-1">
            Capital Raised / Funding (full amount in ₹/$) <span className="text-rose-500">*</span>
          </label>
          <input
            type="number"
            min="0"
            step="10000"
            value={input.funding ?? ''}
            onChange={(e) => handleNumericChange('funding', e.target.value)}
            placeholder="e.g. 2000000 (20 lakh)"
            className="w-full rounded-xl border border-slate-200 bg-slate-50/60 p-2.5 text-xs text-slate-800 outline-none transition focus:border-sky-500 focus:bg-white focus:ring-2 focus:ring-sky-100"
          />
          {fieldErrors.funding && (
            <p className="mt-1 text-[11px] text-rose-500 font-semibold">{fieldErrors.funding}</p>
          )}
        </div>

        {/* Team Size */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-3.5 shadow-2xs">
          <label className="text-[11px] font-black uppercase tracking-wider text-slate-700 block mb-1">
            Team Size (Headcount) <span className="text-rose-500">*</span>
          </label>
          <input
            type="number"
            min="1"
            max="100"
            value={input.team_size ?? ''}
            onChange={(e) => handleNumericChange('team_size', e.target.value)}
            placeholder="e.g. 5"
            className="w-full rounded-xl border border-slate-200 bg-slate-50/60 p-2.5 text-xs text-slate-800 outline-none transition focus:border-sky-500 focus:bg-white focus:ring-2 focus:ring-sky-100"
          />
          {fieldErrors.team_size && (
            <p className="mt-1 text-[11px] text-rose-500 font-semibold">{fieldErrors.team_size}</p>
          )}
        </div>

        {/* Target Market */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-3.5 shadow-2xs">
          <label className="text-[11px] font-black uppercase tracking-wider text-slate-700 block mb-1">
            Target Market / Vertical <span className="text-rose-500">*</span>
          </label>
          <input
            type="text"
            value={input.market || ''}
            onChange={(e) => handleChange('market', e.target.value)}
            placeholder="e.g. Developer Tools, B2B SaaS, HealthTech"
            className="w-full rounded-xl border border-slate-200 bg-slate-50/60 p-2.5 text-xs text-slate-800 outline-none transition focus:border-sky-500 focus:bg-white focus:ring-2 focus:ring-sky-100"
          />
          {fieldErrors.market && (
            <p className="mt-1 text-[11px] text-rose-500 font-semibold">{fieldErrors.market}</p>
          )}
        </div>

        {/* Experience */}
        <div className="rounded-2xl border border-slate-200/90 bg-white p-3.5 shadow-2xs">
          <label className="text-[11px] font-black uppercase tracking-wider text-slate-700 block mb-1">
            Founder Relevant Experience (Years) <span className="text-rose-500">*</span>
          </label>
          <input
            type="number"
            min="0"
            max="40"
            value={input.experience ?? ''}
            onChange={(e) => handleNumericChange('experience', e.target.value)}
            placeholder="e.g. 5"
            className="w-full rounded-xl border border-slate-200 bg-slate-50/60 p-2.5 text-xs text-slate-800 outline-none transition focus:border-sky-500 focus:bg-white focus:ring-2 focus:ring-sky-100"
          />
          {fieldErrors.experience && (
            <p className="mt-1 text-[11px] text-rose-500 font-semibold">{fieldErrors.experience}</p>
          )}
        </div>
      </div>

      {/* Submit Button */}
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-2xl bg-gradient-to-r from-blue-600 via-indigo-600 to-sky-600 hover:from-blue-700 hover:to-indigo-700 py-3 text-xs font-bold uppercase tracking-wider text-white shadow-lg shadow-blue-500/20 transition-all hover:scale-[1.01] active:scale-[0.98] disabled:opacity-50 flex items-center justify-center gap-2 cursor-pointer"
      >
        {loading ? (
          <>
            <div className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" />
            <span>Evaluating Venture Viability...</span>
          </>
        ) : (
          <span>Run Startup Decision Engine</span>
        )}
      </button>
    </form>
  )
}
