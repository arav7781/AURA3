'use client'

import { useReadContract, useReadContracts } from 'wagmi'
import { VENTUREDAO_ADDRESS, VENTUREDAO_ABI } from '@/constants/abis'
import { formatEther } from 'viem'

export type ProposalDataType = {
  id: number
  founder: `0x${string}`
  fundingAmount: bigint
  valuation: bigint
  description: string
  snapshotBlock: bigint
  voteStart: bigint
  voteEnd: bigint
  forVotes: bigint
  againstVotes: bigint
  executed: boolean
  startupContract: string
  startupToken: string
}

export function useProposals() {
  const { data: proposalCountData } = useReadContract({
    address: VENTUREDAO_ADDRESS,
    abi: VENTUREDAO_ABI,
    functionName: 'proposalCount',
  })

  const count = Number(proposalCountData || 0)

  const contracts = Array.from({ length: count }, (_, i) => ({
    address: VENTUREDAO_ADDRESS,
    abi: VENTUREDAO_ABI,
    functionName: 'proposals',
    args: [i + 1], // proposals are 1-indexed (proposalCount++ runs before storing)
  }))

  const { data: proposalsRaw, isLoading } = useReadContracts({
    contracts,
  })

  const proposals = proposalsRaw?.map((res, i) => {
    if (res.status === 'success' && res.result) {
      const p = res.result as unknown as [
        string, bigint, bigint, string, bigint, bigint, bigint, bigint, bigint, boolean, string, string
      ]
      return {
        id: i + 1, // match the 1-indexed contract ID
        founder: p[0] as `0x${string}`,
        fundingAmount: p[1],
        valuation: p[2],
        description: p[3],
        snapshotBlock: p[4],
        voteStart: p[5],
        voteEnd: p[6],
        forVotes: p[7],
        againstVotes: p[8],
        executed: p[9],
        startupContract: p[10],
        startupToken: p[11],
      }
    }
    return null
  }).filter(Boolean) as ProposalDataType[]

  return {
    proposals: proposals?.reverse() || [],
    isLoading
  }
}
