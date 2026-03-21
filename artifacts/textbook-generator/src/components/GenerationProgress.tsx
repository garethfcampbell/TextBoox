import React from 'react';
import { motion } from 'framer-motion';
import { AlertCircle, RefreshCw, Loader2 } from 'lucide-react';
import type { JobStatus } from '@workspace/api-client-react';

interface GenerationProgressProps {
  status?: JobStatus;
  onReset: () => void;
}

export function GenerationProgress({ status, onReset }: GenerationProgressProps) {
  if (!status) {
    return (
      <div className="w-full max-w-xl mx-auto bg-card p-8 rounded-3xl shadow-xl shadow-black/5 border border-border/50 flex flex-col items-center py-16">
        <Loader2 className="w-10 h-10 text-accent animate-spin mb-6" />
        <h3 className="font-display text-2xl font-bold text-foreground mb-2">Connecting...</h3>
        <p className="text-muted-foreground text-center">Initializing the generation engine.</p>
      </div>
    );
  }

  if (status.status === 'failed') {
    return (
      <div className="w-full max-w-xl mx-auto bg-[#FEF2F2] border border-[#FECACA] p-8 rounded-3xl shadow-xl flex flex-col items-center text-center">
        <div className="w-16 h-16 bg-red-100 rounded-full flex items-center justify-center mb-6">
          <AlertCircle className="w-8 h-8 text-red-600" />
        </div>
        <h3 className="font-display text-2xl font-bold text-red-950 mb-3">Generation Failed</h3>
        <p className="text-red-800/80 mb-8 max-w-md">{status.error || "An unexpected error occurred during synthesis."}</p>
        
        <button 
          onClick={onReset}
          className="px-6 py-3 bg-red-600 text-white rounded-full font-medium hover:bg-red-700 transition-colors flex items-center gap-2"
        >
          <RefreshCw className="w-4 h-4" />
          Start Over
        </button>
      </div>
    );
  }

  const total = status.totalChapters || 10;
  const completed = status.completedChapters || 0;
  const percent = status.progressPercent !== undefined
    ? Math.min(100, Math.max(0, status.progressPercent))
    : Math.min(100, Math.max(0, (completed / Math.max(1, total)) * 100));

  return (
    <div className="w-full max-w-xl mx-auto bg-card p-10 rounded-3xl shadow-2xl shadow-black/5 border border-border/50">
      <div className="flex justify-between items-end mb-6">
        <h3 className="font-display text-2xl font-bold text-foreground">Drafting Textbook</h3>
        <span className="font-mono text-sm text-muted-foreground font-medium bg-secondary px-3 py-1 rounded-md">
          {completed} / {total} Chapters
        </span>
      </div>
      
      <div className="h-3 w-full bg-secondary/80 rounded-full overflow-hidden mb-8 relative">
        <motion.div 
          className="absolute inset-y-0 left-0 bg-primary"
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.8, ease: "easeOut" }}
        />
      </div>

      <div className="space-y-3 bg-secondary/30 p-6 rounded-2xl border border-secondary">
        <p className="font-sans text-sm font-semibold text-accent uppercase tracking-wider">
          Current Activity
        </p>
        <p className="font-sans text-base font-medium text-foreground">
          {status.progress || "Initializing cognitive frameworks..."}
        </p>
        {status.currentChapter && (
          <p className="font-display text-lg italic text-muted-foreground mt-2 border-l-2 border-accent/30 pl-4">
            "{status.currentChapter}"
          </p>
        )}
      </div>
    </div>
  );
}
