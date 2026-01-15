export function TypingIndicator() {
  return (
    <div className="flex items-center gap-3 py-4 px-5 max-w-4xl mx-auto animate-fade-in">
      <div className="w-8 h-8 rounded-lg bg-accent-100 dark:bg-accent-900/40 flex items-center justify-center">
        <svg className="w-4 h-4 text-accent-700 dark:text-accent-400" fill="currentColor" viewBox="0 0 24 24">
          <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7 12h-2v-2h2v2zm0-4h-2V6h2v4z" />
        </svg>
      </div>
      <div className="flex items-center gap-1.5 px-4 py-3 rounded-xl bg-white dark:bg-ink-900 border border-ink-200/50 dark:border-ink-700/50">
        <div className="typing-dot" />
        <div className="typing-dot" />
        <div className="typing-dot" />
      </div>
    </div>
  );
}
