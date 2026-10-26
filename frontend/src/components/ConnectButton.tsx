'use client'

import { useState, useEffect } from 'react'
import { useAccount, useConnect, useDisconnect, useBalance, useSwitchChain } from 'wagmi'
import { formatEther } from 'viem'
import { LogOut, Wallet, AlertTriangle } from 'lucide-react'
import { sepolia } from 'wagmi/chains'

export function ConnectButton() {
  const [mounted, setMounted] = useState(false)
  useEffect(() => setMounted(true), [])

  const { address, isConnected, chainId } = useAccount()
  const { data: balanceData } = useBalance({ address })
  const { connect, connectors, error, isPending } = useConnect()
  const { disconnect } = useDisconnect()
  const { switchChain } = useSwitchChain()

  // Standardize initial render to avoid hydration mismatch
  if (!mounted) {
    return (
      <button disabled className="btn-pro btn-pro-cyan opacity-50 cursor-wait">
        <Wallet className="w-4 h-4 mr-2" />
        Connect MetaMask
      </button>
    )
  }

  if (isConnected) {
    if (chainId !== sepolia.id) {
      return (
        <div className="flex items-center gap-2 bg-red-950/20 border border-red-900/50 rounded-sm py-1 px-3">
          <span className="text-[10px] font-bold text-red-400 flex items-center gap-1 uppercase tracking-tighter">
            <AlertTriangle className="w-3 h-3" /> Network Error
          </span>
          <button
            onClick={() => switchChain({ chainId: sepolia.id })}
            className="text-[10px] font-bold bg-red-500/10 hover:bg-red-500/20 text-red-200 py-1 px-2 rounded-sm border border-red-500/20 transition-all font-mono"
          >
            Switch to Sepolia
          </button>
          <button
            onClick={() => disconnect()}
            className="text-gray-500 hover:text-white transition-colors p-1"
          >
            <LogOut className="w-3 h-3" />
          </button>
        </div>
      )
    }

    return (
      <div className="flex items-center gap-3 bg-slate-50 border border-slate-200 rounded-sm py-1 px-3">
        <div className="flex flex-col text-right">
          <span className="text-[11px] font-mono font-bold text-slate-900 leading-none">
            {address?.slice(0, 6)}...{address?.slice(-4)}
          </span>
          {balanceData && (
            <span className="text-[9px] text-sky-600 font-mono mt-1">
              {Number(formatEther(balanceData.value)).toFixed(4)} {balanceData.symbol}
            </span>
          )}
        </div>
        <button
          onClick={() => disconnect()}
          className="text-slate-400 hover:text-red-500 transition-colors p-1 border-l border-slate-200 pl-2"
          title="Disconnect Option"
        >
          <LogOut className="w-3.5 h-3.5" />
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      {connectors.slice(0, 1).map((connector) => (
        <button
          key={connector.uid}
          onClick={() => connect({ connector })}
          disabled={isPending}
          className="btn-pro btn-pro-cyan active:scale-95 disabled:opacity-50"
        >
          <Wallet className="w-4 h-4 mr-2" />
          {isPending ? 'Connecting...' : 'Connect MetaMask'}
        </button>
      ))}
      {error && <div className="text-red-500 text-[10px] font-mono">{error.message}</div>}
    </div>
  )
}
