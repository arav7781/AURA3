import { EvaluationsList } from '@/components/EvaluationsList'

export default function EvaluationsPage() {
  return (
    <div className="max-w-5xl mx-auto px-6 py-10">
      <div className="mb-8">
        <p className="text-[11px] font-mono uppercase tracking-widest text-[#0284c7] mb-2">AI due diligence</p>
        <h1 className="text-3xl font-black text-slate-900 tracking-tight">Startup evaluations</h1>
        <p className="text-slate-600 mt-2 max-w-2xl">
          Every pitch deck submitted by a founder is researched by the AURA-3 agents, checked against the MCA
          registry and scored. Open one to read the 11-section report, download the PDF or question the analyst.
        </p>
      </div>
      <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
        <EvaluationsList />
      </div>
    </div>
  )
}
