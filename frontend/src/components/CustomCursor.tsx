'use client'

import { useState, useEffect } from 'react'
import { motion, useSpring, useMotionValue } from 'framer-motion'

export function CustomCursor() {
  const [isMounted, setIsMounted] = useState(false)
  const [isClicking, setIsClicking] = useState(false)
  const [isHovering, setIsHovering] = useState(false)
  
  // Outer ring (follows with lag)
  const cursorX = useSpring(-100, { stiffness: 350, damping: 28 })
  const cursorY = useSpring(-100, { stiffness: 350, damping: 28 })
  
  // Inner dot (follows instantly)
  const dotX = useSpring(-100, { stiffness: 1000, damping: 20 })
  const dotY = useSpring(-100, { stiffness: 1000, damping: 20 })
  
  useEffect(() => {
    setIsMounted(true)
    const moveCursor = (e: MouseEvent) => {
      cursorX.set(e.clientX - 16)
      cursorY.set(e.clientY - 16)
      dotX.set(e.clientX - 4)
      dotY.set(e.clientY - 4)
      
      const target = e.target as HTMLElement
      const isClickable = window.getComputedStyle(target).cursor === 'pointer' || target.tagName.toLowerCase() === 'a' || target.tagName.toLowerCase() === 'button'
      setIsHovering(isClickable)
    }
    
    const handleMouseDown = () => setIsClicking(true)
    const handleMouseUp = () => setIsClicking(false)
    
    window.addEventListener('mousemove', moveCursor)
    window.addEventListener('mousedown', handleMouseDown)
    window.addEventListener('mouseup', handleMouseUp)
    
    return () => {
      window.removeEventListener('mousemove', moveCursor)
      window.removeEventListener('mousedown', handleMouseDown)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [cursorX, cursorY, dotX, dotY])

  if (!isMounted) return null

  return (
    <>
      <style dangerouslySetInnerHTML={{__html: `* { cursor: none !important; }`}} />
      
      {/* Outer Ring */}
      <motion.div
        className="fixed top-0 left-0 w-8 h-8 rounded-full pointer-events-none z-[9999] border border-[#0284c7] bg-[#0284c7]/[0.06] mix-blend-normal overflow-hidden"
        style={{ x: cursorX, y: cursorY }}
        animate={{
          scale: isClicking ? 0.8 : isHovering ? 1.5 : 1,
          borderColor: isHovering ? "rgba(2,132,199,1)" : "rgba(2,132,199,0.7)",
          boxShadow: isHovering ? "0 0 20px rgba(2,132,199,0.35), inset 0 0 10px rgba(2,132,199,0.15)" : "0 0 12px rgba(2,132,199,0.2)"
        }}
        transition={{ type: 'spring', stiffness: 400, damping: 28 }}
      />
      
      {/* Inner Energy Core */}
      <motion.div
        className="fixed top-0 left-0 w-2 h-2 rounded-full pointer-events-none z-[9999] bg-[#0369a1] mix-blend-normal"
        style={{ x: dotX, y: dotY }}
        animate={{
          scale: isClicking ? 0.5 : 1,
          boxShadow: isHovering ? "0 0 12px rgba(2,132,199,0.5)" : "0 0 10px rgba(3,105,161,0.4)",
          backgroundColor: isHovering ? "#0284c7" : "#0369a1"
        }}
      />
    </>
  )
}
