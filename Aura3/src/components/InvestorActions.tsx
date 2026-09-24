'use client'

import { useState } from 'react'
import { useAccount, useReadContract, useWriteContract, useWaitForTransactionReceipt } from 'wagmi'
import { VENTUREDAO_ADDRESS, VENTUREDAO_ABI, GOVTOKEN_ADDRESS, GOVTOKEN_ABI } from '@/constants/abis'
import { parseEther, formatEther } from 'viem'
import { CheckCircle2, ChevronRight, Loader2 } from 'lucide-react'
import { useEthPrice } from '@/hooks/useEthPrice'

export function InvestorActions() {
  const { address } = useAccount()
  const ethPrice = useEthPrice()
  const [depositAmount, setDepositAmount] = useState('')
  const [depositUnit, setDepositUnit] = useState<'eth' | 'usd'>('eth')
  const [step, setStep] = useState<0 | 1 | 2>(0) // 0: input, 1: deposit mining, 2: delegate mining

  const convertToEth = (raw: string, unit: 'eth' | 'usd') => {
    const numeric = Number(raw)
    if (isNaN(numeric) || numeric <= 0) return 0
    if (unit === 'eth') return numeric
    if (!ethPrice || ethPrice <= 0) return 0
    return numeric / ethPrice
  }

  const formatEthString = (amount: number) => {
    if (!Number.isFinite(amount) || amount <= 0) return ''
    return amount.toFixed(8).replace(/\.0+$/, '').replace(/(\.\d*?)0+$/, '$1')
  }

  const convertDisplayUnit = (value: string, from: 'eth' | 'usd', to: 'eth' | 'usd') => {
    if (from === to) return value
    const numeric = Number(value)
    if (isNaN(numeric) || numeric <= 0) return value
    if (!ethPrice || ethPrice <= 0) return value
    const converted = from === 'eth' ? numeric * ethPrice : numeric / ethPrice
    return converted.toFixed(2)
  }

  const getConversionHint = (value: string, unit: 'eth' | 'usd') => {
    const numeric = Number(value)
    if (!value || isNaN(numeric) || numeric <= 0) return ''
    if (!ethPrice || ethPrice <= 0) return 'Live conversion unavailable'

    if (unit === 'eth') {
      const usd = numeric * ethPrice
      return `≈ $${usd.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD`
    }

    const eth = numeric / ethPrice
    return `≈ ${eth.toFixed(6)} ETH`
  }

  const depositEthPreview = formatEthString(convertToEth(depositAmount, depositUnit))

  // Read Balances
  const { data: govBalance } = useReadContract({
    address: GOVTOKEN_ADDRESS,
    abi: GOVTOKEN_ABI,
    functionName: 'balanceOf',
    args: address ? [address] : undefined,
    query: { enabled: !!address, refetchInterval: 5000 }
  })

  const { data: votingPower } = useReadContract({
    address: GOVTOKEN_ADDRESS,
    abi: [{ name: 'getVotes', type: 'function', stateMutability: 'view', inputs: [{ name: 'account', type: 'address' }], outputs: [{ name: '', type: 'uint256' }] }],
    functionName: 'getVotes',
    args: address ? [address] : undefined,
    query: { enabled: !!address, refetchInterval: 5000 }
  })

  // Write Hooks
  const { data: depositHash, writeContract: writeDeposit, isPending: isConfirmingDeposit } = useWriteContract()
  const { isLoading: isMiningDeposit, isSuccess: isDepositSuccess } = useWaitForTransactionReceipt({ hash: depositHash })

  const { data: delegateHash, writeContract: writeDelegate, isPending: isConfirmingDelegate } = useWriteContract()
  const { isLoading: isMiningDelegate, isSuccess: isDelegateSuccess } = useWaitForTransactionReceipt({ hash: delegateHash })

  const handleDeposit = () => {
    if (!depositAmount) return
    const depositEth = convertToEth(depositAmount, depositUnit)
    const depositEthString = formatEthString(depositEth)
    if (!depositEthString) return

    setStep(1)
    writeDeposit({
      address: VENTUREDAO_ADDRESS,
      abi: VENTUREDAO_ABI,
      functionName: 'deposit',
      value: parseEther(depositEthString),
      chainId: 11155111,
    })
  }

  if (isDepositSuccess && step === 1) {
    setStep(2)
    writeDelegate({
      address: GOVTOKEN_ADDRESS,
      abi: [{ name: 'delegate', type: 'function', stateMutability: 'nonpayable', inputs: [{ name: 'delegatee', type: 'address' }], outputs: [] }],
      functionName: 'delegate',
      args: [address as `0x${string}`],
      chainId: 11155111,
    })
  }

  if (isDelegateSuccess && step === 2) {
    setStep(0)
    setDepositAmount('')
  }

  return (
    <div className="flex flex-col h-full bg-white">
      <div className="h-[60px] p-6 border-b border-slate-200 bg-slate-50 flex items-center">
        <h2 className="text-[10px] font-bold font-mono text-slate-900 uppercase tracking-widest flex items-center gap-2">
          <TrendingUp className="w-3.5 h-3.5 text-[#0284c7]" /> Governance Power
        </h2>
      </div>

      <div className="flex-1 p-6">
        <div className="mb-6">
          <div className="grid grid-cols-2 border border-slate-200">
            <div className="p-4 border-r border-slate-200 bg-slate-50">
              <p className="text-[9px] font-bold text-slate-500 uppercase mb-1">Treasury Credits</p>
              <p className="text-sm font-mono text-slate-900 leading-none">
                {govBalance !== undefined ? Number(formatEther(govBalance as bigint)).toFixed(4) : '0.0000'}
              </p>
            </div>
            <div className="p-4 bg-slate-50">
              <p className="text-[9px] font-bold text-slate-500 uppercase mb-1">Active Votes</p>
              <p className="text-sm font-mono text-emerald-600 leading-none">
                {votingPower !== undefined ? Number(formatEther(votingPower as bigint)).toFixed(2) : '0.00'}
              </p>
            </div>
          </div>
        </div>

        <div className="pt-6 border-t border-slate-200">
          <h3 className="text-[9px] font-bold text-slate-500 uppercase mb-4 tracking-widest leading-tight">Increase Stake to Amplify Power</h3>
          {step > 0 ? (
            <div className="space-y-px bg-slate-200 border border-slate-200">
              <div className={`p-4 flex items-center justify-between bg-white ${isDepositSuccess ? 'border-l-2 border-emerald-500' : ''}`}>
                <div className="flex items-center gap-3">
                  {isDepositSuccess ? <CheckCircle2 className="w-3 h-3 text-emerald-500" /> : <Loader2 className="w-3 h-3 animate-spin text-[#0284c7]" />}
                  <span className="text-[10px] font-bold font-mono text-slate-900 uppercase tracking-tighter">I. Credit Transfer ({depositEthPreview || '0'} ETH)</span>
                </div>
                <span className="text-[9px] font-mono text-slate-500 uppercase">{isConfirmingDeposit ? 'Awaiting Sign' : isDepositSuccess ? 'Settled' : 'Mining'}</span>
              </div>
              
              <div className={`p-4 flex items-center justify-between bg-white ${isDelegateSuccess ? 'border-l-2 border-emerald-500' : ''} ${step < 2 ? 'opacity-30' : ''}`}>
                <div className="flex items-center gap-3">
                  {isDelegateSuccess ? <CheckCircle2 className="w-3 h-3 text-emerald-500" /> : step === 2 ? <Loader2 className="w-3 h-3 animate-spin text-[#0284c7]" /> : <div className="w-1 h-1 rounded-full bg-slate-300" />}
                  <span className="text-[10px] font-bold font-mono text-slate-900 uppercase tracking-tighter">II. Power Delegation</span>
                </div>
                {step === 2 && <span className="text-[9px] font-mono text-slate-500 uppercase">{isConfirmingDelegate ? 'Awaiting Sign' : isDelegateSuccess ? 'Settled' : 'Mining'}</span>}
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex items-center justify-between">
                <span className="text-[9px] font-bold text-slate-500 uppercase tracking-widest">Deposit Unit</span>
                <div className="flex border border-slate-200 bg-slate-50 rounded text-slate-500">
                  <button
                    type="button"
                    onClick={() => {
                      setDepositAmount(convertDisplayUnit(depositAmount, depositUnit, 'usd'))
                      setDepositUnit('usd')
                    }}
                    className={`px-2 py-0.5 text-[8px] font-mono font-bold uppercase rounded-l-sm ${depositUnit === 'usd' ? 'text-white bg-[#0284c7]' : 'hover:bg-slate-100 hover:text-slate-700'}`}
                  >
                    USD
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDepositAmount(convertDisplayUnit(depositAmount, depositUnit, 'eth'))
                      setDepositUnit('eth')
                    }}
                    className={`px-2 py-0.5 text-[8px] font-mono font-bold uppercase rounded-r-sm ${depositUnit === 'eth' ? 'text-white bg-[#0284c7]' : 'hover:bg-slate-100 hover:text-slate-700'}`}
                  >
                    ETH
                  </button>
                </div>
              </div>
              <input
                type="number" step="0.01"
                value={depositAmount} onChange={e => setDepositAmount(e.target.value)}
                className="input-field h-10 w-full"
                placeholder={depositUnit === 'eth' ? '0.0000000 ETH' : '0.00 USD'}
              />
              <p className="text-[9px] font-mono text-slate-500 uppercase tracking-tight">{getConversionHint(depositAmount, depositUnit)}</p>
              <button
                onClick={handleDeposit}
                disabled={!depositAmount || convertToEth(depositAmount, depositUnit) <= 0}
                className="btn-pro btn-pro-cyan w-full h-10"
              >
                Initialize Deposit <ChevronRight className="w-3 h-3 ml-1" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function TrendingUp(props: any) {
  return (
    <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" ><polyline points="22 7 13.5 15.5 8.5 10.5 2 17" /><polyline points="16 7 22 7 22 13" /></svg>
  )
}
