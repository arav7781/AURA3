'use client'

import { useReadContracts } from 'wagmi'
import { ProposalDataType } from './useProposals'
import { GOVTOKEN_ADDRESS, GOVTOKEN_ABI } from '@/constants/abis'

/**
 * Filter executed proposals to strictly those where the user
 * had voting power at the exact block the proposal was snapshotted.
 * In the VentureDAO model, holding power during a snapshot = investor.
 */
export function useInvestments(userAddress: `0x${string}` | undefined, executedProposals: ProposalDataType[]) {
  
  const contracts = executedProposals.map((p) => ({
    address: GOVTOKEN_ADDRESS,
    abi: GOVTOKEN_ABI,
    functionName: 'getPastVotes',
    args: [userAddress, p.snapshotBlock],
  }))

  const { data: pastVotesData, isLoading } = useReadContracts({
    contracts,
    query: {
        enabled: !!userAddress && executedProposals.length > 0,
    }
  })

  // Filter the input array based on the parallel multicall results
  const investedProposals = executedProposals.filter((p, i) => {
    if (!pastVotesData) return false
    
    const item = (pastVotesData as any[])[i]
    if (!item) return false
    
    // Check if the contract call was successful and returned > 0 voting power
    if (item.status === 'success' && item.result !== undefined) {
      const power = BigInt(item.result)
      return power > BigInt(0)
    }
    
    return false
  })

  return { investedProposals, isLoading }
}
