'use client'

import { motion } from 'framer-motion'
import { useState, useEffect } from 'react'

export function GlitchText({ text, className = '' }: { text: string, className?: string }) {
  const [displayText, setDisplayText] = useState('')
  const [isDone, setIsDone] = useState(false)
  
  useEffect(() => {
    let iteration = 0
    const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789!@#$%^&*'
    
    const interval = setInterval(() => {
      setDisplayText(
        text
          .split('')
          .map((letter, index) => {
            if (index < iteration) return text[index]
            return chars[Math.floor(Math.random() * chars.length)]
          })
          .join('')
      )
      
      if (iteration >= text.length) {
        clearInterval(interval)
        setIsDone(true)
      }
      
      // Speed of decryption
      iteration += 1 / 3
    }, 30)
    
    return () => clearInterval(interval)
  }, [text])
  
  return (
    <span className={`${className} relative inline-block`}>
      {displayText}
      {!isDone && (
        <motion.span 
          animate={{ opacity: [1, 0] }} 
          transition={{ repeat: Infinity, duration: 0.1, ease: 'linear' }} 
          className="absolute -right-3 top-[10%] bottom-[10%] w-[10px] bg-[#03e1ff] shadow-[0_0_10px_#03e1ff]" 
        />
      )}
    </span>
  )
}
