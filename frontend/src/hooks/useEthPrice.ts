"use client"
import { useState, useEffect, useRef } from 'react'

// Module-level cache so all component instances share one value
let sharedPrice: number | null = null
let sharedFetchPromise: Promise<void> | null = null

export function useEthPrice() {
  const [price, setPrice] = useState<number | null>(sharedPrice)
  const isMounted = useRef(true)

  useEffect(() => {
    isMounted.current = true

    async function fetchPrice() {
      // If another instance is already fetching, wait for it
      if (sharedFetchPromise) {
        await sharedFetchPromise
        if (isMounted.current && sharedPrice !== null) {
          setPrice(sharedPrice)
        }
        return
      }

      sharedFetchPromise = (async () => {
        try {
          const res = await fetch('/api/eth-price')
          if (!res.ok) return
          const data = await res.json()
          if (data?.ethereum?.usd) {
            sharedPrice = data.ethereum.usd
          }
        } catch (err) {
          console.error('Failed to fetch ETH price:', err)
        } finally {
          sharedFetchPromise = null
        }
      })()

      await sharedFetchPromise

      if (isMounted.current && sharedPrice !== null) {
        setPrice(sharedPrice)
      }
    }

    fetchPrice()
    const interval = setInterval(fetchPrice, 120_000) // refresh every 2 minutes

    return () => {
      isMounted.current = false
      clearInterval(interval)
    }
  }, [])

  return price
}
