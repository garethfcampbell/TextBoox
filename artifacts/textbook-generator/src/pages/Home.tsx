import React, { useState, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { BookOpen, Sparkles, ArrowRight, Download, CheckCircle, Loader2, X } from 'lucide-react';
import { useTextbookIdea, useTextbookGenerator, useTextbookJob } from '@/hooks/use-textbook';
import { BookCover } from '@/components/BookCover';
import { GenerationProgress } from '@/components/GenerationProgress';
import { BookLibrary } from '@/components/BookLibrary';
import { AdminPanel } from '@/components/AdminPanel';
import { useToast } from '@/hooks/use-toast';
import type { BookIdea } from '@workspace/api-client-react';

type FlowStep = 'input' | 'generating-idea' | 'review' | 'generating-book' | 'done';

export default function Home() {
  const isAdmin = new URLSearchParams(window.location.search).has('admin');
  return isAdmin ? <AdminPanel /> : <HomeContent />;
}

function HomeContent() {
  const [step, setStep] = useState<FlowStep>('input');
  const [keyword, setKeyword] = useState('');
  const [idea, setIdea] = useState<BookIdea | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { toast } = useToast();

  const ALL_EXAMPLES = [
    'Asset Pricing',
    'Corporate Finance',
    'Behavioural Finance',
    'Portfolio Management',
    'AI & Finance',
    'Banking',
    'Currencies',
    'Financial Risk Management',
    'Financial History',
  ];

  const suggestedExamples = useMemo(() => {
    const shuffled = [...ALL_EXAMPLES].sort(() => Math.random() - 0.5);
    return shuffled.slice(0, 6);
  }, []);

  const generateIdea = useTextbookIdea();
  const generateBook = useTextbookGenerator();
  const jobStatus = useTextbookJob(jobId);

  const handleGenerateIdea = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyword.trim()) return;
    
    setStep('generating-idea');
    try {
      const result = await generateIdea.mutateAsync({ data: { keyword } });
      setIdea(result);
      setStep('review');
    } catch (error: any) {
      toast({
        title: "Error generating concept",
        description: error.message || "Please try a different keyword.",
        variant: "destructive"
      });
      setStep('input');
    }
  };

  const handleGenerateBook = async () => {
    if (!idea) return;
    setStep('generating-book');
    try {
      const result = await generateBook.mutateAsync({ data: { ...idea, email: email.trim() || undefined } });
      setJobId(result.jobId);
    } catch (error: any) {
      toast({
        title: "Failed to start generation",
        description: error.message || "Could not queue the generation task.",
        variant: "destructive"
      });
      setStep('review');
    }
  };

  const resetFlow = () => {
    setStep('input');
    setKeyword('');
    setIdea(null);
    setJobId(null);
  };

  useEffect(() => {
    if (jobStatus.data?.status === 'completed') {
      setStep('done');
    }
  }, [jobStatus.data?.status]);

  const fadeVariants = {
    initial: { opacity: 0, y: 20 },
    animate: { opacity: 1, y: 0 },
    exit: { opacity: 0, y: -20, transition: { duration: 0.2 } },
    transition: { duration: 0.5, ease: "easeOut" }
  };

  return (
    <div className="relative min-h-screen bg-background text-foreground font-sans selection:bg-accent/30 selection:text-primary flex flex-col overflow-hidden">

      {/* Sidebar backdrop */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
          />
        )}
      </AnimatePresence>

      {/* Sidebar */}
      <AnimatePresence>
        {sidebarOpen && (
          <motion.aside
            key="sidebar"
            initial={{ x: '-100%' }}
            animate={{ x: 0 }}
            exit={{ x: '-100%' }}
            transition={{ type: 'spring', stiffness: 300, damping: 30 }}
            className="fixed top-0 left-0 h-full w-80 bg-background border-r border-border z-50 flex flex-col shadow-2xl"
          >
            <div className="flex items-center justify-end p-4 pb-8 border-b border-border">
              <button
                onClick={() => setSidebarOpen(false)}
                className="w-8 h-8 flex items-center justify-center rounded-lg hover:bg-secondary transition-colors text-muted-foreground hover:text-primary"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-5">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-4">Library</p>
              <BookLibrary />
            </div>
            <div className="p-5 border-t border-border">
              <p className="text-xs text-muted-foreground text-center">
                Inspired by{' '}
                <a
                  href="https://github.com/Bklieger/infinite-bookshelf"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="underline underline-offset-2 hover:text-primary transition-colors"
                >
                  Infinite Bookshelf
                </a>
                {' · '}
                <a
                  href="?admin"
                  className="underline underline-offset-2 hover:text-primary transition-colors"
                >
                  Admin
                </a>
              </p>
            </div>
          </motion.aside>
        )}
      </AnimatePresence>

      {/* Header */}
      <header className="absolute top-0 w-full p-6 z-50 flex justify-between items-center" onClick={() => setSidebarOpen(false)}>
        <div 
          className="flex items-center gap-3 cursor-pointer group"
          onClick={(e) => { e.stopPropagation(); setSidebarOpen(o => !o); }}
        >
          <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center text-background shadow-lg shadow-primary/20 group-hover:bg-accent transition-colors">
            <BookOpen className="w-5 h-5" />
          </div>
          <span className="font-display font-semibold text-2xl tracking-tight text-primary">TextBoox</span>
        </div>
      </header>

      {/* Background Texture — CSS-only paper grain, no external image needed */}
      <div className="absolute inset-0 z-0 pointer-events-none">
        <svg className="absolute inset-0 w-full h-full opacity-[0.18]" xmlns="http://www.w3.org/2000/svg">
          <filter id="paper-noise">
            <feTurbulence type="fractalNoise" baseFrequency="0.75" numOctaves="4" stitchTiles="stitch" />
            <feColorMatrix type="saturate" values="0" />
          </filter>
          <rect width="100%" height="100%" filter="url(#paper-noise)" />
        </svg>
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-background/60 to-background/90" />
      </div>

      <main className="relative z-10 flex-1 flex items-center justify-center p-6 mt-20 pb-10">
        <AnimatePresence mode="wait">
          
          {/* STEP 1: INPUT */}
          {step === 'input' && (
            <motion.div key="input" {...fadeVariants} className="w-full max-w-2xl mx-auto text-center space-y-10">
              <div className="space-y-4">
                <span className="inline-block px-4 py-1.5 rounded-full bg-secondary text-primary font-medium text-sm tracking-wider uppercase mb-2">
                  Textboox.org
                </span>
                <h1 className="font-display text-5xl md:text-6xl font-bold leading-tight text-primary">
                  What subject would you like to explore?
                </h1>
                <p className="text-xl text-muted-foreground max-w-lg mx-auto">
                  Enter any topic, and we'll craft a comprehensive, professionally structured textbook.
                </p>
              </div>

              <form onSubmit={handleGenerateIdea} className="relative max-w-xl mx-auto group">
                <input 
                  type="text" 
                  value={keyword}
                  onChange={(e) => setKeyword(e.target.value)}
                  placeholder="e.g. Asset Pricing, Corporate Finance..."
                  className="w-full text-lg md:text-xl px-8 py-6 bg-white/90 backdrop-blur-md border border-border/80 rounded-2xl shadow-xl shadow-black/5 focus:outline-none focus:border-primary/50 focus:ring-4 focus:ring-primary/10 transition-all font-sans"
                  autoFocus
                />
                <button 
                  type="submit"
                  disabled={!keyword.trim()}
                  className="absolute right-3 top-3 bottom-3 aspect-square bg-primary text-white rounded-xl flex items-center justify-center hover:bg-accent hover:scale-105 disabled:opacity-50 disabled:hover:scale-100 disabled:hover:bg-primary transition-all"
                >
                  <ArrowRight className="w-6 h-6" />
                </button>
              </form>

              <div className="flex flex-wrap justify-center gap-2 max-w-xl mx-auto">
                {suggestedExamples.map((example) => (
                  <button
                    key={example}
                    type="button"
                    onClick={() => setKeyword(example)}
                    className="px-4 py-1.5 rounded-full border border-border/70 bg-white/70 backdrop-blur-sm text-sm text-muted-foreground hover:border-primary/40 hover:text-primary hover:bg-white transition-all"
                  >
                    {example}
                  </button>
                ))}
              </div>
            </motion.div>
          )}

          {/* STEP 2: GENERATING IDEA (LOADING) */}
          {step === 'generating-idea' && (
            <motion.div key="generating-idea" {...fadeVariants} className="flex flex-col items-center text-center -mt-20">
              <div className="relative w-24 h-24 mb-8 flex items-center justify-center">
                <div className="absolute inset-0 border-4 border-secondary rounded-full" />
                <div className="absolute inset-0 border-4 border-accent rounded-full border-t-transparent animate-spin" />
                <Sparkles className="w-8 h-8 text-primary animate-pulse" />
              </div>
              <h2 className="font-display text-3xl font-bold text-primary mb-2">Synthesizing Concept</h2>
              <p className="text-muted-foreground text-lg">Analyzing academic frameworks and curating the syllabus...</p>
            </motion.div>
          )}

          {/* STEP 3: REVIEW IDEA */}
          {step === 'review' && idea && (
            <motion.div key="review" {...fadeVariants} className="w-full max-w-5xl grid grid-cols-1 md:grid-cols-[3fr_7fr] gap-16 items-center -mt-20">
              <div className="order-2 md:order-1 flex justify-center w-full perspective-1000">
                <BookCover title={idea.title} topic={idea.topic} />
              </div>
              <div className="order-1 md:order-2 space-y-8">
                <div>
                  <h2 className="text-xs font-bold tracking-[0.25em] text-accent uppercase mb-4 flex items-center gap-2">
                    <Sparkles className="w-4 h-4" />
                    Concept Proposed
                  </h2>
                  <h1 className="font-display text-4xl sm:text-5xl font-bold leading-tight text-primary mb-6">
                    {idea.title}
                  </h1>
                  <div className="prose prose-lg prose-slate text-muted-foreground leading-relaxed">
                    <p>{idea.description}</p>
                  </div>
                </div>
                
                <div className="space-y-4 pt-4">
                  <div>
                    <label className="block text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-2">
                      Email me when it's done <span className="font-normal normal-case tracking-normal">(optional)</span>
                    </label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@example.com"
                      className="w-full px-4 py-3 bg-white/90 border border-border/80 rounded-xl text-sm focus:outline-none focus:border-primary/50 focus:ring-2 focus:ring-primary/10 transition-all"
                    />
                  </div>
                  <div className="flex flex-col sm:flex-row gap-4">
                    <button 
                      onClick={handleGenerateBook} 
                      className="px-8 py-4 bg-primary text-primary-foreground rounded-full font-medium shadow-xl shadow-primary/20 hover:-translate-y-0.5 hover:shadow-2xl hover:shadow-primary/30 active:translate-y-0 transition-all flex items-center justify-center gap-3 text-lg"
                    >
                      Draft Full Textbook
                      <ArrowRight className="w-5 h-5" />
                    </button>
                    <button 
                      onClick={resetFlow} 
                      className="px-8 py-4 bg-transparent text-primary border-2 border-border/80 rounded-full font-medium hover:bg-secondary/50 hover:border-primary/20 transition-all flex items-center justify-center text-lg"
                    >
                      Start Over
                    </button>
                  </div>
                </div>
              </div>
            </motion.div>
          )}

          {/* STEP 4: GENERATING BOOK */}
          {step === 'generating-book' && (
            <motion.div key="generating-book" {...fadeVariants} className="w-full">
              <GenerationProgress status={jobStatus.data} onReset={resetFlow} />
            </motion.div>
          )}

          {/* STEP 5: DONE */}
          {step === 'done' && idea && jobStatus.data && (
            <motion.div key="done" {...fadeVariants} className="w-full max-w-5xl grid grid-cols-1 md:grid-cols-[3fr_7fr] gap-16 items-center">
              <div className="flex justify-center w-full">
                <BookCover title={idea.title} topic={idea.topic} />
              </div>
              <div className="space-y-8">
                 <div>
                    <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-50 border border-emerald-200 text-emerald-800 font-medium text-sm mb-6 shadow-sm">
                       <CheckCircle className="w-4 h-4" />
                       Ready for Publication
                    </div>
                    <h1 className="font-display text-4xl sm:text-5xl font-bold text-primary mb-6 leading-tight">
                      Your textbook is complete.
                    </h1>
                    <p className="text-muted-foreground text-lg leading-relaxed">
                      We've meticulously structured and written your textbook. It has been formatted and is now available for download.
                    </p>
                 </div>
                 
                 <div className="flex flex-col sm:flex-row flex-wrap gap-4 pt-4">
                    {jobStatus.data.availableFormats?.map(fmt => (
                       <button 
                         key={fmt}
                         onClick={() => window.open(`/api/textbook/download/${jobStatus.data?.jobId}/${fmt}`, '_blank')}
                         className="px-6 py-4 bg-white border border-border shadow-md rounded-2xl flex items-center justify-between hover:border-accent hover:shadow-lg hover:-translate-y-1 transition-all group min-w-[180px]"
                       >
                          <div className="flex items-center gap-4">
                             <div className="w-12 h-12 rounded-xl bg-secondary flex items-center justify-center group-hover:bg-accent/10 transition-colors">
                                <Download className="w-5 h-5 text-primary group-hover:text-accent transition-colors" />
                             </div>
                             <div className="flex flex-col items-start">
                                <span className="font-sans text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-0.5">Download</span>
                                <span className="font-display font-bold text-xl text-primary">{fmt.toUpperCase()}</span>
                             </div>
                          </div>
                       </button>
                    ))}
                 </div>

                 <div className="pt-8 mt-8 border-t border-border/50">
                    <button 
                      onClick={resetFlow} 
                      className="text-primary font-medium hover:text-accent flex items-center gap-2 transition-colors"
                    >
                      <ArrowRight className="w-4 h-4" />
                      Generate another textbook
                    </button>
                 </div>
              </div>
            </motion.div>
          )}

        </AnimatePresence>
      </main>

    </div>
  );
}
