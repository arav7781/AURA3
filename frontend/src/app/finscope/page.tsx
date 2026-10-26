'use client'

import { useState, useRef, useEffect } from 'react'
import { motion } from 'framer-motion'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import ReactPlayer from 'react-player'
import {
  Brain, Send, Paperclip, Sparkles, X, FileText, TrendingUp, Shield, AlertTriangle, Newspaper, Users, LineChart, Network, Menu, MessageSquare
} from 'lucide-react'
import { API_BASE } from '@/lib/api'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Title,
  Tooltip,
  Legend,
  ArcElement,
} from 'chart.js'
import { Bar, Radar } from 'react-chartjs-2'

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  RadialLinearScale,
  PointElement,
  LineElement,
  Filler,
  Title,
  Tooltip,
  Legend,
  ArcElement
)

const SOCKET_BASE = API_BASE
const CHATS_KEY = 'aura3.finscope.chats'

interface StoredChat {
  id: string
  title: string
  updatedAt: string
  messages: (Omit<ChatMessage, 'timestamp'> & { timestamp: string })[]
}

function readChats(): StoredChat[] {
  try {
    return JSON.parse(window.localStorage.getItem(CHATS_KEY) || '[]')
  } catch {
    return []
  }
}

function writeChats(chats: StoredChat[]) {
  try {
    window.localStorage.setItem(CHATS_KEY, JSON.stringify(chats.slice(0, 30)))
  } catch {
    // Storage full or unavailable: history just won't persist.
  }
}

const newSessionId = () => `fs_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`

const JAILBREAK_INPUT_PATTERNS = [
  /ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)/i,
  /(system|developer)\s+prompt/i,
  /act\s+as\s+(a\s+)?(lawyer|doctor|hacker|jailbroken\s+ai)/i,
  /(bypass|override|disable)\s+(safety|guardrails|policy|policies|rules)/i,
  /jailbreak|dan\s+mode|do\s+anything\s+now/i,
  /pretend\s+to\s+be/i,
]

const INAPPROPRIATE_INPUT_PATTERNS = [
  /\b(murder|kill|bomb|weapon)\b/i,
  /\b(hate\s*speech|racist|sexist)\b/i,
  /\b(porn|sex\s*chat|explicit)\b/i,
]

function shouldBlockFinScopePrompt(prompt: string): boolean {
  const normalized = prompt.trim()
  if (!normalized) return false

  return [
    ...JAILBREAK_INPUT_PATTERNS,
    ...INAPPROPRIATE_INPUT_PATTERNS,
  ].some((pattern) => pattern.test(normalized))
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  agent?: string
  file?: string
  timestamp: Date
}

// Extract YouTube video cards from raw URLs
function extractYouTubeVideos(content: string): { cleanContent: string; videos: { title: string; url: string; thumbnail: string; videoId: string }[] } {
  const videos: { title: string; url: string; thumbnail: string; videoId: string }[] = []
  
  // Match lines containing youtube links, extracting optional leading text as title
  const lineRegex = /^(.*?)https:\/\/(?:www\.)?youtube\.com\/watch\?v=([a-zA-Z0-9_-]+)[^\s]*\s*$/gm
  
  let cleanContent = content.replace(lineRegex, (match, prefix, videoId) => {
    let title = prefix.trim().replace(/^[-*•]*\s*/, '').replace(/:\s*$/, '').replace(/\*\*/g, '').trim()
    if (!title || title.length < 2) title = 'Video Tutorial'
    videos.push({
      title,
      url: `https://www.youtube.com/watch?v=${videoId}`,
      thumbnail: `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`,
      videoId: videoId
    })
    return '' // Remove the URL line
  })
  
  // Clean up introductory fluff phrases left behind
  cleanContent = cleanContent.replace(/Here are some YouTube video resources.*:\s*/gi, '')

  return { cleanContent: cleanContent.trim(), videos }
}

// Extract document analysis flashcard
function extractFlashcard(content: string) {
  const flashcardRegex = /\[FLASHCARD\]([\s\S]*?)\[\/FLASHCARD\]/
  const match = flashcardRegex.exec(content)
  if (!match) return { cleanContent: content, flashcard: null }

  const cardText = match[1]
  const extract = (key: string, def = '') => {
    const rx = new RegExp(`${key}:\\s*(.+)`)
    const m = cardText.match(rx)
    return m ? m[1].trim().replace(/\*\*/g, '') : def
  }

  const flashcard = {
    title: extract('Title', 'Startup Analysis'),
    highlight: extract('Highlight', ''),
    verdict: extract('Verdict', 'Review'),
    team: extract('Team', ''),
    metrics: extract('KeyMetrics', ''),
    whatItDoes: extract('What It Does', '')
  }

  return {
    cleanContent: content.replace(flashcardRegex, '').trim(),
    flashcard
  }
}

// Extract competitor comparison chart data
function extractCompetitorChart(content: string) {
  const chartRegex = /\[COMPETITOR_CHART\]([\s\S]*?)\[\/COMPETITOR_CHART\]/
  const match = chartRegex.exec(content)
  if (!match) return { cleanContent: content, competitorData: null }

  let competitorData = null
  try {
    const jsonStr = match[1].trim()
    competitorData = JSON.parse(jsonStr)
  } catch (e) {
    console.warn('Failed to parse competitor chart JSON:', e)
  }

  return {
    cleanContent: content.replace(chartRegex, '').trim(),
    competitorData
  }
}

// Extract interactive UI widgets
function extractInteractiveForm(content: string) {
  const hasForm = content.includes('[PORTFOLIO_FORM]')
  return {
    cleanContent: content.replace('\[PORTFOLIO_FORM\]', '').replace('[PORTFOLIO_FORM]', '').trim(),
    hasForm
  }
}

// Extract news card data
function extractNewsCard(content: string) {
  const newsRegex = /\[NEWS_CARD\]([\s\S]*?)\[\/NEWS_CARD\]/
  const match = newsRegex.exec(content)
  if (!match) return { cleanContent: content, newsData: null }

  let newsData = null
  try {
    const jsonStr = match[1].trim()
    newsData = JSON.parse(jsonStr)
  } catch (e) {
    console.warn('Failed to parse news card JSON:', e)
  }

  return {
    cleanContent: content.replace(newsRegex, '').trim(),
    newsData
  }
}

function AgentBadge({ agent }: { agent?: string }) {
  if (!agent) return null
  const colorMap: Record<string, string> = {
    'Financial Educator': 'border-emerald-200 text-emerald-700 bg-emerald-50',
    'Document Analyzer': 'border-amber-200 text-amber-700 bg-amber-50',
    'Market Researcher': 'border-blue-200 text-blue-700 bg-blue-50',
    'Portfolio Coach': 'border-purple-200 text-purple-700 bg-purple-50',
    'News Reporter': 'border-rose-200 text-rose-700 bg-rose-50',
    'Guardrails': 'border-red-200 text-red-700 bg-red-50',
  }
  const style = colorMap[agent] || 'border-slate-200 text-slate-600 bg-slate-50'
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-[9px] font-bold font-mono uppercase tracking-wider rounded-sm border bg-white/[0.02] ${style}`}>
      <Brain className="w-2.5 h-2.5" />
      {agent}
    </span>
  )
}

function YouTubeCard({ video }: { video: any }) {
  return (
    <a 
      href={video.url} 
      target="_blank" 
      rel="noopener noreferrer"
      className="group block rounded-lg overflow-hidden border border-slate-200 bg-white shadow-xl hover:shadow-2xl transition-all duration-300 transform hover:-translate-y-1"
    >
      <div className="relative aspect-video overflow-hidden bg-slate-900 flex items-center justify-center">
        <div className="absolute inset-0 bg-gradient-to-br from-slate-800 to-slate-900" />
        <img src={video.thumbnail} alt="" referrerPolicy="no-referrer" onError={e => { e.currentTarget.style.display = 'none' }} className="absolute inset-0 w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity" />
        
        {/* Fake play button overlay */}
        <div className="relative z-10 w-12 h-12 bg-red-600 rounded-full flex items-center justify-center shadow-lg group-hover:scale-110 group-hover:bg-red-500 transition-transform duration-300">
          <div className="w-0 h-0 border-t-[8px] border-t-transparent border-l-[14px] border-l-white border-b-[8px] border-b-transparent ml-1"></div>
        </div>

        {/* Top right "YouTube" badge */}
        <div className="absolute top-2 right-2 bg-black/60 backdrop-blur-sm px-2 py-1 rounded text-[9px] font-bold text-white uppercase tracking-wider flex items-center gap-1">
           Watch on YouTube
        </div>
      </div>
      <div className="p-3 border-t border-slate-200 bg-slate-50 group-hover:bg-blue-50/50 transition-colors">
        <p className="text-[12px] font-bold text-slate-800 group-hover:text-[#0284c7] transition-colors line-clamp-2 leading-snug">
          {video.title}
        </p>
      </div>
    </a>
  )
}

function StartupFlashCard({ flashcard }: { flashcard: any }) {
  const imageUrl = "https://images.unsplash.com/photo-1553729459-efe14ef6055d?auto=format&fit=crop&w=800&q=80"
  
  // Determine verdict color
  const isPositive = flashcard.verdict.toLowerCase().includes('positive') || flashcard.verdict.toLowerCase().includes('strong') || flashcard.verdict.toLowerCase().includes('bullish')
  const isWarning = flashcard.verdict.toLowerCase().includes('warning') || flashcard.verdict.toLowerCase().includes('red flag')
  const verdictColor = isPositive ? 'text-secondary-fixed' 
                     : isWarning ? 'text-error' 
                     : 'text-amber-400'

  return (
    <div className="glass-card relative group overflow-hidden flex flex-col rounded-xl w-full h-full">
      {/* Hero Area */}
      <div className="h-44 relative overflow-hidden hero-clip bg-slate-100">
        <img src={imageUrl} alt="Startup" className="w-full h-full object-cover opacity-60 group-hover:scale-110 transition-transform duration-[2000ms]" />
        <div className="absolute inset-0 bg-gradient-to-t from-white to-transparent opacity-80" />
        <div className="absolute inset-0 bg-[#0284c7]/5 mix-blend-overlay" />
        
        {/* Holographic Overlay */}
        <div className="absolute top-4 left-4 p-2 bg-white/80 backdrop-blur-md border border-slate-200 shadow-sm">
          <span className="font-mono text-[9px] text-[#0284c7] font-bold tracking-widest uppercase">Protocol: AUR-7</span>
        </div>
        
        <div className="absolute bottom-10 left-6">
          <h3 className="font-body font-black text-3xl text-slate-900 tracking-tight">{flashcard.title || 'Startup'}</h3>
          <span className="text-[10px] font-mono text-primary-container/80 uppercase tracking-widest">
            {flashcard.whatItDoes && flashcard.whatItDoes !== 'Not specified' ? flashcard.whatItDoes.slice(0, 30) + '...' : 'Series Selection'}
          </span>
        </div>
      </div>
      
      {/* Card Content */}
      <div className="p-6 pt-0 flex flex-col flex-1">
        <p className="text-xs text-on-surface-variant leading-relaxed mb-6 border-l border-primary-container/20 pl-4 py-2 italic font-light">
          "{flashcard.highlight || 'Strategic cross-chain asset accumulation.'}"
        </p>
        
        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-1.5 text-secondary-fixed">
              <Sparkles className="w-3.5 h-3.5" />
              <span className="text-[8px] font-black uppercase">Verdict</span>
            </div>
            <span className={`text-xs font-bold uppercase ${verdictColor}`}>{flashcard.verdict || 'NEUTRAL'}</span>
          </div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-1.5 text-tertiary">
              <Users className="w-3.5 h-3.5" />
              <span className="text-[8px] font-black uppercase">Team</span>
            </div>
            <span className="text-xs font-bold text-slate-900 truncate">{flashcard.team && flashcard.team !== 'Not specified' ? flashcard.team.split(',')[0].split('(')[0].trim() : 'Not specified'}</span>
          </div>
          <div className="flex flex-col gap-1">
            <div className="flex items-center gap-1.5 text-primary-container">
              <TrendingUp className="w-3.5 h-3.5" />
              <span className="text-[8px] font-black uppercase">Metrics</span>
            </div>
            <span className="text-xs font-bold text-slate-900 truncate">{flashcard.metrics && flashcard.metrics !== 'Not specified' ? flashcard.metrics : 'N/A'}</span>
          </div>
        </div>
        
        <div className="mt-auto bg-slate-50 p-4 rounded-lg border border-slate-200">
          <span className="text-[8px] font-mono text-on-surface-variant uppercase">Key metric</span>
          <p className="text-sm font-bold text-slate-900 mt-1">{flashcard.metrics || 'Not specified'}</p>
          {flashcard.team && flashcard.team !== 'Not specified' && (
            <p className="text-xs text-slate-600 mt-2"><span className="font-semibold">Team:</span> {flashcard.team}</p>
          )}
        </div>
      </div>
    </div>
  )
}

function CompetitorChartCard({ data }: { data: any }) {
  const { company, competitors, metrics, strengths, weaknesses } = data
  const allLabels = [company, ...competitors]

  // Bar chart: Funding comparison
  const fundingData = {
    labels: allLabels,
    datasets: [{
      label: 'Total Funding ($M)',
      data: [metrics.fundingM.company, ...metrics.fundingM.competitors],
      backgroundColor: [
        'rgba(168, 85, 247, 0.8)',
        'rgba(3, 225, 255, 0.6)',
        'rgba(16, 185, 129, 0.6)',
        'rgba(251, 191, 36, 0.6)',
      ],
      borderColor: [
        'rgba(168, 85, 247, 1)',
        'rgba(3, 225, 255, 1)',
        'rgba(16, 185, 129, 1)',
        'rgba(251, 191, 36, 1)',
      ],
      borderWidth: 1,
      borderRadius: 6,
    }]
  }

  const fundingOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      title: {
        display: true,
        text: 'Funding Comparison ($M)',
        color: '#a855f7',
        font: { size: 11, weight: 'bold' as const, family: 'monospace' },
        padding: { bottom: 10 },
      },
      tooltip: {
        backgroundColor: 'rgba(0,0,0,0.9)',
        titleFont: { size: 11 },
        bodyFont: { size: 10 },
        borderColor: 'rgba(168,85,247,0.3)',
        borderWidth: 1,
      },
    },
    scales: {
      x: {
        ticks: { color: '#9ca3af', font: { size: 9, family: 'monospace' } },
        grid: { color: 'rgba(255,255,255,0.03)' },
      },
      y: {
        ticks: { color: '#9ca3af', font: { size: 9 } },
        grid: { color: 'rgba(255,255,255,0.05)' },
      },
    },
  }

  // Radar chart: Multi-metric comparison
  const radarData = {
    labels: ['Market Share', 'Accuracy', 'Growth Rate', 'Customer Base'],
    datasets: [
      {
        label: company,
        data: [
          metrics.marketShare.company,
          metrics.accuracy.company,
          metrics.growthRate.company,
          Math.min(metrics.customerBase.company / 10, 100),
        ],
        backgroundColor: 'rgba(168, 85, 247, 0.2)',
        borderColor: 'rgba(168, 85, 247, 1)',
        borderWidth: 2,
        pointBackgroundColor: 'rgba(168, 85, 247, 1)',
        pointBorderColor: '#fff',
        pointRadius: 3,
      },
      ...competitors.map((comp: string, idx: number) => {
        const colors = [
          { bg: 'rgba(3, 225, 255, 0.15)', border: 'rgba(3, 225, 255, 0.8)' },
          { bg: 'rgba(16, 185, 129, 0.15)', border: 'rgba(16, 185, 129, 0.8)' },
          { bg: 'rgba(251, 191, 36, 0.15)', border: 'rgba(251, 191, 36, 0.8)' },
        ]
        const c = colors[idx % colors.length]
        return {
          label: comp,
          data: [
            metrics.marketShare.competitors[idx],
            metrics.accuracy.competitors[idx],
            metrics.growthRate.competitors[idx],
            Math.min(metrics.customerBase.competitors[idx] / 10, 100),
          ],
          backgroundColor: c.bg,
          borderColor: c.border,
          borderWidth: 1.5,
          pointBackgroundColor: c.border,
          pointBorderColor: '#fff',
          pointRadius: 2,
        }
      }),
    ]
  }

  const radarOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'bottom' as const,
        labels: {
          color: '#9ca3af',
          font: { size: 9, family: 'monospace' },
          boxWidth: 10,
          padding: 8,
        },
      },
      title: {
        display: true,
        text: 'Competitive Positioning',
        color: '#03e1ff',
        font: { size: 11, weight: 'bold' as const, family: 'monospace' },
        padding: { bottom: 6 },
      },
    },
    scales: {
      r: {
        angleLines: { color: 'rgba(255,255,255,0.08)' },
        grid: { color: 'rgba(255,255,255,0.06)' },
        pointLabels: { color: '#9ca3af', font: { size: 9, family: 'monospace' } },
        ticks: { display: false },
        suggestedMin: 0,
        suggestedMax: 100,
      },
    },
  }

  return (
    <div className="flex flex-col gap-6 w-full h-full">
      <div className="glass-card p-6 flex-1 flex flex-col gap-6 rounded-xl">
        <div className="flex justify-between items-start">
          <div className="flex flex-col">
            <span className="font-['JetBrains_Mono'] text-[9px] text-secondary-fixed tracking-[3px] uppercase">Competitor_Landscape_v2</span>
            <h3 className="font-body font-black text-xl text-slate-900 mt-1">{company} vs Market Benchmarks</h3>
          </div>
          <div className="p-2 bg-secondary-fixed/10 border border-secondary-fixed/20 rounded-sm">
            <LineChart className="text-secondary-fixed w-4 h-4" />
          </div>
        </div>
        
        {/* Charts Grid */}
        <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-2 border-b md:border-b-0 md:border-r border-white/5 h-[220px]">
             <Radar data={radarData} options={radarOptions} />
          </div>
          <div className="p-2 h-[220px]">
             <Bar data={fundingData} options={fundingOptions} />
          </div>
        </div>
        
        {/* Strengths & Weaknesses (Adapted from original but fitting new style) */}
        {(strengths?.length > 0 || weaknesses?.length > 0) && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-4 border-t border-white/5">
             <div className="flex flex-col gap-2">
                <span className="text-[10px] font-mono text-emerald-400 uppercase tracking-widest font-bold flex items-center gap-1.5">
                  <Shield className="w-3 h-3" /> Strengths
                </span>
                <ul className="space-y-1">
                  {strengths?.slice(0, 3).map((s: string, i: number) => (
                    <li key={i} className="text-[10px] text-on-surface-variant flex items-start gap-1.5">
                      <span className="text-emerald-500 mt-0.5">✓</span>
                      {s}
                    </li>
                  ))}
                </ul>
             </div>
             <div className="flex flex-col gap-2">
                <span className="text-[10px] font-mono text-amber-400 uppercase tracking-widest font-bold flex items-center gap-1.5">
                  <AlertTriangle className="w-3 h-3" /> Weaknesses
                </span>
                <ul className="space-y-1">
                  {weaknesses?.slice(0, 3).map((w: string, i: number) => (
                    <li key={i} className="text-[10px] text-on-surface-variant flex items-start gap-1.5">
                      <span className="text-amber-500 mt-0.5">⚠</span>
                      {w}
                    </li>
                  ))}
                </ul>
             </div>
          </div>
        )}
      </div>
      
      {/* SEC Guideline Alert block from template */}
      <div className="glass-card p-4 rounded-xl flex items-center gap-4 border-l-4 border-l-secondary-fixed">
        <div className="w-12 h-12 bg-secondary-fixed/10 flex items-center justify-center rounded-sm">
          <Network className="text-secondary-fixed w-5 h-5 animate-pulse" />
        </div>
        <div className="flex-1">
          <h4 className="text-[11px] font-black uppercase tracking-wider text-slate-900">AURA-3 FORECAST</h4>
          <p className="text-[10px] text-on-surface-variant leading-tight mt-1">Institutional liquidity impact: <span className="text-secondary-fixed font-bold">Positive correlation</span> anticipated based on analysis.</p>
        </div>
        <button className="px-4 py-2 border border-secondary-fixed/30 text-[9px] font-black uppercase text-slate-900 hover:bg-secondary-fixed hover:text-on-secondary-fixed transition-all cursor-pointer">Impact Audit</button>
      </div>
    </div>
  )
}

function ChatNewsCard({ data }: { data: any }) {
  if (!data?.articles?.length) return null
  const fallbackImage = "https://images.unsplash.com/photo-1554224155-6726b3ff858f?auto=format&fit=crop&w=800&q=80"
  return (
    <div className="mb-4 mt-2">
      <div className="flex items-center gap-2 mb-3 px-1">
        <Newspaper className="w-4 h-4 text-[#0284c7]" />
        <h3 className="text-[11px] font-bold text-slate-800 uppercase tracking-widest">
          Live Market Intel: <span className="text-purple-700">${data.symbol}</span>
        </h3>
      </div>
      <div className="flex flex-col gap-2">
        {data.articles.map((item: any, i: number) => (
          <a
            key={i}
            href={item.url || '#'}
            target="_blank"
            rel="noopener noreferrer"
            className="group flex gap-3 p-3 bg-white border border-slate-200 hover:border-[#0284c7]/30 rounded-sm transition-all duration-300 shadow-sm"
          >
            {item.photo && (
              <div className="w-20 h-20 shrink-0 bg-slate-100 overflow-hidden rounded-sm hidden sm:block border border-slate-100 group-hover:border-[#0284c7]/20 transition-colors">
                <img
                  src={item.photo}
                  alt=""
                  referrerPolicy="no-referrer"
                  onError={(e) => {
                    const img = e.currentTarget

                    if (img.dataset.fallbackApplied !== 'true') {
                      img.dataset.fallbackApplied = 'true'
                      img.src = fallbackImage
                      return
                    }

                    if (img.dataset.backupApplied !== 'true') {
                      img.dataset.backupApplied = 'true'
                      img.src = `https://picsum.photos/seed/finscope-${i}/240/240`
                      return
                    }

                    img.style.display = 'none'
                  }}
                  className="w-full h-full object-cover opacity-60 group-hover:opacity-100 group-hover:scale-105 transition-all duration-500"
                />
              </div>
            )}
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1.5">
                <span className="text-[9px] font-mono text-gray-500 uppercase tracking-widest">{item.source}</span>
                <span className="text-[9px] font-mono text-gray-700">|</span>
                <span className="text-[9px] font-mono text-gray-500">{item.time ? new Date(item.time).toLocaleDateString() : 'Recent'}</span>
                {item.sentiment && (
                  <>
                    <div className="flex-1" />
                    <span className={`text-[8px] font-mono font-bold px-1.5 py-0.5 rounded-sm border ${
                      item.sentiment === 'positive' ? 'text-emerald-400 border-emerald-400/20 bg-emerald-400/10' :
                      item.sentiment === 'negative' ? 'text-rose-400 border-rose-400/20 bg-rose-400/10' :
                      'text-sky-400 border-sky-400/20 bg-sky-400/10'
                    }`}>
                      {item.sentiment.toUpperCase()}
                    </span>
                  </>
                )}
              </div>
              <h4 className="text-[12px] font-semibold text-slate-800 group-hover:text-[#0284c7] line-clamp-2 mb-1.5 leading-snug transition-colors">
                {item.title}
              </h4>
              <p className="text-[10px] text-slate-600 line-clamp-2 leading-relaxed">
                {item.snippet}
              </p>
            </div>
          </a>
        ))}
      </div>
    </div>
  )
}

function PortfolioFormCard({ onSubmit }: { onSubmit: (msg: string) => void }) {
  const [risk, setRisk] = useState('Moderate')
  const [horizon, setHorizon] = useState('3-7 yrs')
  const [goal, setGoal] = useState('')

  const submit = () => {
    onSubmit(`My Risk Tolerance is ${risk}, Time Horizon is ${horizon}, and my goal is ${goal || 'General Wealth Generation'}. Please provide my allocation.`)
  }

  return (
    <div className="mb-4 mt-3 p-5 rounded-xl border border-slate-200 bg-white shadow-md">
      <h3 className="text-[13px] font-extrabold text-slate-900 mb-4 flex items-center gap-2 uppercase tracking-wide">
        <Brain className="w-4 h-4 text-[#0284c7]" /> Build Custom Portfolio
      </h3>
      
      <div className="space-y-5">
        <div>
          <label className="text-[10px] uppercase font-mono text-[#03e1ff] mb-2.5 block tracking-widest font-bold">Risk Tolerance</label>
          <div className="flex flex-wrap gap-2">
            {['Conservative', 'Moderate', 'Aggressive'].map(r => (
              <button 
                key={r} 
                onClick={() => setRisk(r)} 
                className={`px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all border ${risk === r ? 'bg-[#0284c7] text-white border-[#0284c7] shadow-sm' : 'bg-slate-50 text-slate-600 border-slate-200 hover:border-[#0284c7]/50 hover:bg-slate-100'}`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-[10px] uppercase font-mono text-[#a855f7] mb-2.5 block tracking-widest font-bold">Time Horizon</label>
          <div className="flex flex-wrap gap-2">
            {['< 3 yrs', '3-7 yrs', '10+ yrs'].map(h => (
              <button 
                key={h} 
                onClick={() => setHorizon(h)} 
                className={`px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all border ${horizon === h ? 'bg-purple-600 text-white border-purple-600 shadow-sm' : 'bg-slate-50 text-slate-600 border-slate-200 hover:border-purple-600/50 hover:bg-slate-100'}`}
              >
                {h}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-[10px] uppercase font-mono text-emerald-400 mb-2 block tracking-widest font-bold">Primary Goal</label>
          <input 
            type="text" 
            value={goal} 
            onChange={e => setGoal(e.target.value)} 
            placeholder="e.g. Retirement, House Downpayment..." 
            className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3.5 py-2.5 text-[12px] text-slate-900 focus:outline-none focus:border-[#0284c7]/50 transition-colors" 
          />
        </div>

        <button 
          onClick={submit} 
          className="w-full mt-2 py-3 bg-gradient-to-r from-[#0284c7] to-purple-600 text-white font-extrabold text-[12px] rounded-lg hover:shadow-lg hover:scale-[1.02] transition-all flex items-center justify-center gap-2 uppercase tracking-widest"
        >
          <Sparkles className="w-4 h-4" /> Calculate Asset Allocation
        </button>
      </div>
    </div>
  )
}

export default function FinScopePage() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [attachedFile, setAttachedFile] = useState<File | null>(null)
  const chatEndRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [logs, setLogs] = useState<string[]>([])

  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [pastChats, setPastChats] = useState<StoredChat[]>([])
  const [sessionId, setSessionId] = useState<string>('')

  useEffect(() => {
    setSessionId(newSessionId())
    setPastChats(readChats())
  }, [])

  // Persist the current conversation locally; the backend keeps its own session memory.
  useEffect(() => {
    if (!sessionId || messages.length === 0) return
    const firstUser = messages.find(m => m.role === 'user')
    const chat: StoredChat = {
      id: sessionId,
      title: firstUser ? firstUser.content.slice(0, 40) : 'New chat',
      updatedAt: new Date().toISOString(),
      messages: messages.map(m => ({ ...m, timestamp: m.timestamp.toISOString() })),
    }
    const others = readChats().filter(c => c.id !== sessionId)
    const next = [chat, ...others]
    writeChats(next)
    setPastChats(next)
  }, [messages, sessionId])

  const loadChat = (id: string) => {
    const chat = readChats().find(c => c.id === id)
    if (!chat) return
    setSessionId(id)
    setMessages(chat.messages.map(m => ({ ...m, timestamp: new Date(m.timestamp) })))
    setSidebarOpen(false)
  }

  const startNewChat = () => {
    setMessages([])
    setSessionId(newSessionId())
    setSidebarOpen(false)
  }
  // Initialize Socket.IO connection
  useEffect(() => {
    let socket: any;
    if (!SOCKET_BASE) {
      setLogs((prev) => [...prev, 'Socket URL is not configured.'].slice(-80));
      return;
    }
    import('socket.io-client').then(({ io }) => {
      socket = io(SOCKET_BASE); // Connect to FastAPI socket.io
      
      socket.on('log_stream', (data: { message?: string }) => {
        const rawMessage = typeof data?.message === 'string' ? data.message : '';
        const parsedLogs = rawMessage
          .replace(/\r/g, '\n')
          .split('\n')
          .map((line) => line.trimEnd())
          .filter(Boolean);

        if (parsedLogs.length === 0) return;

        setLogs(prev => {
          const newLogs = [...prev, ...parsedLogs];
          return newLogs.slice(-80); // Keep a richer logs backlog
        });
      });

      socket.on('connect_error', () => {
        setLogs((prev) => [...prev, 'Socket connection error to backend log stream.'].slice(-80));
      });
    });

    return () => {
      if (socket) socket.disconnect();
    };
  }, []);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const fetchWithTimeout = async (url: string, options: RequestInit, timeoutMs = 45000) => {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), timeoutMs)

    try {
      return await fetch(url, { ...options, signal: controller.signal })
    } finally {
      window.clearTimeout(timer)
    }
  }

  const sendMessage = async (overrideInput?: string | any) => {
    let finalInput = input
    if (typeof overrideInput === 'string') {
      finalInput = overrideInput
    }
    
    if ((!finalInput.trim() && !attachedFile) || isLoading) return

    const userContent = finalInput.trim() || (attachedFile ? `Analyze this document: ${attachedFile.name}` : '')

    if (shouldBlockFinScopePrompt(userContent)) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Request blocked by safety policy. Please ask a finance-focused question without jailbreak or harmful instructions.',
        timestamp: new Date(),
      }])
      if (overrideInput === undefined) setInput('')
      return
    }

    const userMsg: ChatMessage = {
      role: 'user',
      content: userContent,
      file: attachedFile?.name,
      timestamp: new Date(),
    }
    setMessages(prev => [...prev, userMsg])
    if (overrideInput === undefined) setInput('')
    setLogs([]) // Clear previous logs
    setIsLoading(true)

    const currentFile = attachedFile
    setAttachedFile(null)
    if (fileInputRef.current) fileInputRef.current.value = ''

    try {
      if (currentFile) {
        // Upload document + analyze
        const formData = new FormData()
        formData.append('document', currentFile)
        formData.append('session_id', sessionId)
        if (finalInput.trim()) formData.append('question', finalInput.trim())
        const res = await fetchWithTimeout(`${API_BASE}/finscope/analyze-document`, {
          method: 'POST',
          body: formData,
        }, 120000)
        const data = await res.json()
        if (!res.ok) throw new Error(data.detail || 'Analysis failed')
        const assistantMsgStr = data.analysis || 'Could not analyze the document.'
        const agentResp = data.agent_used || 'Document Analyzer'
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: assistantMsgStr,
          agent: agentResp,
          timestamp: new Date(),
        }])
      } else {
        // Normal chat — include session_id so backend can pull stored doc context
        const res = await fetchWithTimeout(`${API_BASE}/finscope/chat`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: userContent,
            user_profile: 'beginner',
            session_id: sessionId,
          }),
        }, 60000)
        const data = await res.json()
        if (!res.ok) throw new Error(data.detail || 'Something went wrong')
        const assistantMsgStr = data.answer || 'No response.'
        const agentResp = data.agent_used
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: assistantMsgStr,
          agent: agentResp,
          timestamp: new Date(),
        }])
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error
        ? (err.name === 'AbortError'
            ? 'Request timed out. The agents are taking too long — please try again.'
            : err.message === 'Failed to fetch' ? `Cannot reach the AURA-3 backend at ${API_BASE}. Is it running?` : err.message)
        : `Connection error — is the AURA-3 backend running at ${API_BASE}?`
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: errorMsg,
        timestamp: new Date(),
      }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) setAttachedFile(file)
  }

  const suggestedQuestions = [
    "What is angel investing and how do I start?",
    "How should a retiree build their portfolio?",
    "Explain mutual funds vs ETFs simply",
    "What metrics matter when evaluating a startup?",
  ]

  return (
    <div className="bg-background text-on-surface w-full h-[100vh] grid-bg font-body m-0 p-0 overflow-hidden flex">

      {/* Sidebar for Chat History */}
      <aside className={`fixed inset-y-0 left-0 w-64 bg-white border-r border-slate-200 z-50 transform ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'} transition-transform duration-300 ease-in-out`}>
        <div className="p-4 flex flex-col h-full mt-20">
          <div className="flex justify-between items-center mb-6">
            <h2 className="text-slate-900 font-body tracking-widest uppercase text-sm font-bold">Past Data Links</h2>
            <button onClick={() => setSidebarOpen(false)} className="text-slate-500 hover:text-slate-900">
              <X className="w-5 h-5" />
            </button>
          </div>
          <button onClick={startNewChat} className="mb-4 w-full py-2 bg-slate-50 border border-slate-200 text-[#0284c7] hover:bg-slate-100 text-xs font-mono uppercase tracking-widest transition-colors rounded-sm flex items-center justify-center gap-2 shadow-sm">
            <MessageSquare className="w-4 h-4" /> New Analysis
          </button>
          <div className="flex-1 overflow-y-auto pr-2 space-y-2">
            {pastChats.map(chat => (
              <button key={chat.id} onClick={() => loadChat(chat.id)} className={`w-full text-left p-3 rounded-md border ${sessionId === chat.id ? 'bg-[#f0f9ff] border-[#0284c7]/30 text-slate-900' : 'bg-transparent border-slate-100 text-slate-600 hover:bg-slate-50 hover:text-slate-900'} transition-all group`}>
                <div className="text-xs font-bold line-clamp-1 group-hover:text-[#0284c7] transition-colors">{chat.title}</div>
                <div className="text-[9px] font-mono mt-1 opacity-60 text-slate-500">{new Date(chat.updatedAt).toLocaleDateString()}</div>
              </button>
            ))}
          </div>
        </div>
      </aside>

      {/* Main Chat Interface */}
      <main className="flex-1 flex flex-col h-full relative">
        <button onClick={() => setSidebarOpen(true)} className="absolute top-24 left-4 z-40 p-2 bg-white border border-slate-200 rounded-sm hover:bg-slate-50 transition-colors text-slate-700 hidden md:block">
          <Menu className="w-5 h-5" />
        </button>
      

        <div className="flex-1 overflow-y-auto terminal-scroll pb-28 pt-8" id="chat-container">
          <div className="max-w-5xl mx-auto px-4 md:px-8 flex flex-col gap-10">
            {/* Empty State */}
            {messages.length === 0 && (
              <div className="flex flex-col items-center justify-center pt-[10vh] text-center max-w-2xl mx-auto">
                <div className="w-16 h-16 rounded-xl bg-white border border-slate-200 flex items-center justify-center mb-6 shadow-sm hero-clip">
                  <Brain className="w-8 h-8 text-[#0284c7] animate-pulse" />
                </div>
                <h2 className="text-3xl font-body font-black text-slate-900 mb-3 tracking-tight">System Initialized</h2>
                <p className="text-xs text-slate-600 mb-10 font-mono leading-relaxed max-w-lg">
                  AURA-3 intelligence protocol active. Upload documentation for deep analysis or query market benchmarks to begin synthetic evaluation.
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full">
                  {suggestedQuestions.map((q, i) => (
                    <button
                      key={i}
                      onClick={() => setInput(q)}
                      className="text-left text-[11px] text-slate-600 hover:text-slate-900 px-5 py-4 bg-slate-50 border border-slate-200 hover:border-[#0284c7]/50 rounded-lg transition-all group shadow-sm flex items-center gap-3"
                    >
                      <span className="text-[#0284c7]/50 group-hover:text-[#0284c7] font-mono text-lg">›</span>
                      <span className="font-medium leading-snug">{q}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Messages */}
            {messages.map((msg, i) => {
              let finalOutput = { cleanContent: msg.content, videos: [] as any[], flashcard: null as any, competitorData: null as any, newsData: null as any, hasForm: false }
              
              if (msg.role === 'assistant') {
                const ytExtracted = extractYouTubeVideos(msg.content)
                const fcExtracted = extractFlashcard(ytExtracted.cleanContent)
                const ccExtracted = extractCompetitorChart(fcExtracted.cleanContent)
                const newsExtracted = extractNewsCard(ccExtracted.cleanContent)
                const formExtracted = extractInteractiveForm(newsExtracted.cleanContent)
                
                finalOutput = {
                  videos: ytExtracted.videos,
                  flashcard: fcExtracted.flashcard,
                  competitorData: ccExtracted.competitorData,
                  newsData: newsExtracted.newsData,
                  cleanContent: formExtracted.cleanContent,
                  hasForm: formExtracted.hasForm
                }
              }
              
              const { cleanContent, videos, flashcard, competitorData, newsData, hasForm } = finalOutput

              return (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex flex-col w-full ${msg.role === 'user' ? 'items-end' : 'items-start'} max-w-5xl`}
                >
                  {msg.role === 'user' ? (
                    <div className="flex flex-col items-end gap-3 max-w-xl">
                      <div className="bg-[#f0f9ff] p-5 border border-[#0284c7]/20 rounded-tl-2xl rounded-br-2xl rounded-tr-md rounded-bl-md shadow-sm">
                        {msg.file && (
                          <div className="flex items-center gap-2 mb-3 pb-3 border-b border-[#0284c7]/20">
                            <FileText className="w-3.5 h-3.5 text-[#0284c7]" />
                            <span className="text-[10px] font-mono text-[#0284c7] uppercase">{msg.file}</span>
                          </div>
                        )}
                        <p className="font-body font-medium text-slate-800 text-[13px] leading-relaxed">{msg.content}</p>
                      </div>
                      <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest opacity-70">
                        {msg.timestamp.toLocaleTimeString()} | ENCRYPTED
                      </span>
                    </div>
                  ) : (
                    <div className="flex flex-col items-start gap-4 w-full">
                      <div className="flex items-center gap-3">
                        <div className="w-2 h-6 bg-purple-600"></div>
                        <span className="font-body text-[10px] font-black uppercase tracking-[3px] text-purple-700">
                          FinScope Intelligence
                        </span>
                        <AgentBadge agent={msg.agent} />
                      </div>
                      <div className="bg-white p-6 md:p-8 border border-slate-200 shadow-sm rounded-tr-3xl rounded-bl-3xl w-full max-w-4xl">
                        <div className="text-[13px] leading-relaxed text-slate-800 markdown-content font-body flex flex-col gap-4">
                          {cleanContent && <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanContent}</ReactMarkdown>}
                          {newsData && <ChatNewsCard data={newsData} />}
                          {hasForm && <PortfolioFormCard onSubmit={sendMessage} />}
                          
                          {/* Videos */}
                          {videos.length > 0 && (
                            <div className="mt-8 pt-6 border-t border-white/10 w-full">
                              <p className="text-[10px] font-bold font-mono text-primary-container uppercase tracking-widest mb-4 flex items-center gap-2">
                                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                                Deep-dive Video Analysis
                              </p>
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                {videos.map((v, vi) => (
                                  <YouTubeCard key={vi} video={v} />
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </div>
                      
                      {/* Bento grid for custom blocks */}
                      {(flashcard || competitorData) && (
                        <div className="flex flex-col items-start gap-6 max-w-5xl w-full mt-4">
                          <div className="flex items-center gap-3 ml-2">
                            <div className="w-2 h-6 bg-primary-container"></div>
                            <span className="font-body text-[10px] font-black uppercase tracking-[3px] text-primary-container">Synthesis Result</span>
                          </div>
                          <div className="grid grid-cols-1 md:grid-cols-12 gap-6 w-full">
                            {flashcard && (
                              <div className={competitorData ? "col-span-1 md:col-span-5" : "col-span-1 md:col-span-12"}>
                                <StartupFlashCard flashcard={flashcard} />
                              </div>
                            )}
                            {competitorData && (
                              <div className={flashcard ? "col-span-1 md:col-span-7" : "col-span-1 md:col-span-12"}>
                                <CompetitorChartCard data={competitorData} />
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                      <span className="text-[9px] font-mono text-on-surface-variant uppercase tracking-widest pl-4 opacity-50 mt-1">
                        {msg.timestamp.toLocaleTimeString()} | AURA-3
                      </span>
                    </div>
                  )}
                </motion.div>
              )
            })}
            
            {isLoading && (
              <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-full max-w-4xl mb-4 ml-1 md:ml-6 mt-4">
                <div className="bg-[#f8fafc] border border-slate-200 rounded-md overflow-hidden shadow-sm">
                   <div className="bg-slate-100 px-4 py-2 border-b border-slate-200 flex items-center justify-between">
                     <span className="text-[9px] font-mono font-bold tracking-[3px] text-[#0284c7] uppercase animate-pulse">AURA-3 Subagent Execution Core</span>
                     <div className="flex gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-[#0284c7]/50"></span>
                        <span className="w-2 h-2 rounded-full bg-[#0284c7]/30"></span>
                     </div>
                   </div>
                   <div className="p-4 font-mono text-[10px] text-slate-700 max-h-[250px] overflow-y-auto flex flex-col gap-1 terminal-scroll">
                     {logs.length === 0 && <span className="opacity-50 text-slate-400 italic">Initializing autonomous agents...</span>}
                     {logs.map((log, idx) => (
                       <span key={`${idx}-${log}`} className="text-slate-800 opacity-90 whitespace-pre-wrap break-words"><span className="text-[#0284c7] mr-2">$</span>{log}</span>
                     ))}
                     <span className="text-[#0284c7] animate-pulse inline-block mt-2">_</span>
                   </div>
                </div>
              </motion.div>
            )}
            <div ref={chatEndRef} className="h-10" />
          </div>
        </div>

        {/* Input Tools Area */}
        <div className="absolute bottom-0 left-0 right-0 px-4 md:px-8 py-20 z-20 pointer-events-none bg-gradient-to-t from-white via-white/95 to-transparent">
          <div className="max-w-4xl mx-auto flex flex-col gap-4 pointer-events-auto">
            
            {/* Quick Suggestions - hidden if not empty state or if we have attached file */}
            {messages.length === 0 && !attachedFile && (
              <div className="flex gap-2 overflow-x-auto terminal-scroll pb-2 hidden sm:flex">
                {suggestedQuestions.slice(0, 3).map((q, idx) => (
                  <button key={idx} onClick={() => setInput(q)} className="px-4 py-2 border border-slate-200 bg-white shadow-sm rounded-full text-[10px] font-mono text-slate-600 hover:text-[#0284c7] hover:border-[#0284c7]/30 whitespace-nowrap transition-colors">
                     {q.slice(0, 40)}{q.length > 40 ? '...' : ''}
                  </button>
                ))}
              </div>
            )}
            
            <div className="bg-white border border-slate-200 p-2 md:p-3 rounded-2xl flex flex-col shadow-lg relative group focus-within:border-[#0284c7]/50 transition-colors duration-500">
              {attachedFile && (
                <div className="mb-2 px-3 py-2 bg-amber-50 border border-amber-200 rounded-xl flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <FileText className="w-3.5 h-3.5 text-amber-600" />
                    <span className="text-[11px] font-mono text-amber-700 truncate max-w-[200px]">{attachedFile.name}</span>
                  </div>
                  <button onClick={() => { setAttachedFile(null); if (fileInputRef.current) fileInputRef.current.value = '' }} className="text-amber-500/60 hover:text-amber-600">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              )}
              
              <div className="flex items-end gap-3 relative">
                <input ref={fileInputRef} type="file" accept=".pdf,.docx,.doc,.txt" onChange={handleFileSelect} className="hidden" />
                <button 
                  onClick={() => fileInputRef.current?.click()} 
                  className="w-10 h-10 rounded-xl bg-slate-50 flex items-center justify-center hover:bg-slate-100 text-slate-500 transition-colors border border-slate-200"
                  title="Upload Document"
                >
                  <Paperclip className="w-4 h-4 text-[#0284c7]" />
                </button>
                
                <textarea 
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      sendMessage();
                    }
                  }}
                  placeholder={attachedFile ? "Ask a question about this document..." : "Transmit intelligence protocol parameters..."}
                  className="flex-1 bg-transparent border-0 outline-none resize-none h-10 py-3 text-[13px] text-slate-900 placeholder:text-slate-400 font-body terminal-scroll"
                  disabled={isLoading}
                  rows={1}
                />
                
                <div className="flex items-center gap-2 shrink-0">
                   <button 
                     onClick={() => sendMessage()}
                     disabled={isLoading || (!input.trim() && !attachedFile)}
                     className="bg-[#0284c7] hover:bg-[#0369a1] text-white font-black px-6 h-10 rounded-xl uppercase text-[10px] tracking-widest disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-2"
                   >
                     Submit <Send className="w-3 h-3" />
                   </button>
                </div>
              </div>

              {/* Decorative Corner */}
              <div className="absolute top-0 right-0 w-8 h-8 border-t-2 border-r-2 border-[#0284c7]/0 group-focus-within:border-[#0284c7]/50 rounded-tr-2xl transition-colors duration-500 pointer-events-none"></div>
            </div>
            
            <div className="flex justify-center">
              <span className="text-[9px] font-mono text-slate-500 uppercase tracking-widest text-center mt-1">
                AURA-3 IS A SYNTHETIC INTELLIGENCE. NOT FINANCIAL ADVICE.
              </span>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
