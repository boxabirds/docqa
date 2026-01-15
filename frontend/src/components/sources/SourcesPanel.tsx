import { useState } from 'react';
import type { Source } from '../../types';
import { SourceItem } from './SourceItem';

interface SourcesPanelProps {
  sources: Source[];
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  if (sources.length === 0) return null;

  return (
    <div className="border border-ink-200/50 dark:border-ink-700/50 rounded-xl overflow-hidden">
      {/* Header - clickable to toggle */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between gap-2 px-4 py-3
          bg-paper-50 dark:bg-ink-800/50
          hover:bg-ink-100 dark:hover:bg-ink-800
          transition-colors duration-150"
      >
        <div className="flex items-center gap-2">
          <svg
            className="w-4 h-4 text-accent-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <span className="text-sm font-medium text-ink-700 dark:text-ink-200">
            Sources
          </span>
          <span className="px-1.5 py-0.5 rounded-md text-xs font-medium bg-ink-200 dark:bg-ink-700 text-ink-600 dark:text-ink-300">
            {sources.length}
          </span>
        </div>
        <svg
          className={`w-4 h-4 text-ink-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Sources list */}
      {isExpanded && (
        <div className="divide-y divide-ink-200/50 dark:divide-ink-700/50 animate-fade-in">
          {sources.map((source, index) => (
            <SourceItem key={`${source.file_id}-${source.page_number}-${index}`} source={source} />
          ))}
        </div>
      )}
    </div>
  );
}
