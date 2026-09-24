import React from 'react'

/**
 * Deterministic generative avatar for Startups based on their unique ID/address.
 * Uses the DiceBear API to generate high-quality pixel-art avatars that look
 * exactly like NFT profile pictures, matching the tensor.trade aesthetic perfectly.
 */
export function StartupAvatar({ seed, size = 32 }: { seed: string | number, size?: number }) {
  const seedString = encodeURIComponent(`crypto-synthetic-venture-seed-${String(seed)}`)
  const avatarUrl = `https://api.dicebear.com/7.x/pixel-art/svg?seed=${seedString}`

  return (
    <div 
      style={{ width: size, height: size }} 
      className="border border-[#222] group-hover:border-[#333] bg-[#050505] flex-shrink-0 flex items-center justify-center transition-colors"
    >
      <img 
        src={avatarUrl} 
        alt={`Avatar for ${seedString}`}
        width={size} 
        height={size}
        className="w-full h-full object-cover opacity-80 group-hover:opacity-100 transition-opacity"
      />
    </div>
  )
}
