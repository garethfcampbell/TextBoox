import React from 'react';
import { motion } from 'framer-motion';

interface BookCoverProps {
  title: string;
  topic: string;
  author?: string;
}

export function BookCover({ title, topic, author = "AI Synthesized Edition" }: BookCoverProps) {
  return (
    <motion.div 
      initial={{ rotateY: -20, opacity: 0, x: -50 }}
      animate={{ rotateY: 0, opacity: 1, x: 0 }}
      transition={{ duration: 0.8, type: "spring", bounce: 0.4 }}
      className="relative aspect-[3/4] w-full max-w-[320px] mx-auto rounded-r-2xl rounded-l-md bg-primary text-primary-foreground shadow-[20px_20px_40px_-10px_rgba(0,0,0,0.3)] flex flex-col justify-between border-l-[12px] border-l-[#080d18] overflow-hidden"
      style={{ transformPerspective: 1000 }}
    >
      {/* Spine highlight and texture overlays */}
      <div className="absolute top-0 bottom-0 left-0 w-8 bg-gradient-to-r from-white/10 to-transparent pointer-events-none z-0" />
      <div className="absolute inset-0 opacity-10 mix-blend-overlay pointer-events-none bg-[url('https://www.transparenttextures.com/patterns/stucco.png')]" />
      
      <div className="p-8 z-10 flex flex-col h-full">
        <div>
          <h3 className="font-display text-3xl sm:text-4xl font-bold leading-tight mb-6 tracking-tight text-white">{title}</h3>
          <div className="h-[2px] w-16 bg-accent mb-6" />
          <p className="font-sans text-xs tracking-[0.2em] uppercase text-white/70 font-semibold">{topic}</p>
        </div>
        
        <div className="mt-auto pt-8 border-t border-white/10">
          <p className="font-sans text-[10px] tracking-widest uppercase text-white/50 mb-1">Published by</p>
          <p className="font-display text-lg text-white/90">{author}</p>
        </div>
      </div>
    </motion.div>
  );
}
