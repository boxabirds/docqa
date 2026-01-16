import type { Source } from '../../types';
import { useChatStore } from '../../stores/chatStore';

interface SourceItemProps {
  source: Source;
}

export function SourceItem({ source }: SourceItemProps) {
  const { openPdfViewer } = useChatStore();

  const handleViewSource = () => {
    // Only open viewer if we have a file_id
    if (!source.file_id) return;

    openPdfViewer({
      id: source.file_id,
      name: source.file_name,
      page: source.page_number || 1,
    });
  };

  return (
    <div className="source-card group flex flex-col gap-2 m-2">
      {/* File info */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          {/* PDF icon */}
          <div className="flex-shrink-0 w-8 h-8 rounded-lg bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center">
            <svg
              className="w-4 h-4 text-rose-600 dark:text-rose-400"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm-1 7V3.5L18.5 9H13zM9.17 15.24c-.49-.04-.98-.07-1.18-.07-.12 0-.25.01-.37.03v2.46c.09.01.2.02.34.02.48 0 .92-.13 1.21-.38.31-.26.48-.65.48-1.14 0-.44-.15-.74-.48-.92zm2.86-.09c-.31 0-.6.05-.82.12v4.34c.22.07.51.11.86.11.73 0 1.28-.2 1.65-.6.39-.41.58-1.03.58-1.85 0-.72-.17-1.28-.51-1.67-.31-.37-.8-.54-1.76-.45zM18 9h-4V4H7v16h10V9z" />
            </svg>
          </div>

          {/* File name and page */}
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink-800 dark:text-ink-200 truncate">
              {source.file_name}
            </p>
            <p className="text-xs text-ink-500 dark:text-ink-400">
              {source.page_number ? `Page ${source.page_number}` : 'Page unknown'}
              {source.relevance_score != null && (
                <span className="ml-2 text-accent-600 dark:text-accent-400">
                  {Math.round(source.relevance_score * 100)}% relevant
                </span>
              )}
            </p>
          </div>
        </div>

        {/* View button - only show if PDF is available */}
        {source.file_id && (
        <button
          onClick={handleViewSource}
          className="flex-shrink-0 opacity-0 group-hover:opacity-100
            flex items-center gap-1 px-2.5 py-1.5 rounded-lg
            text-xs font-medium
            bg-accent-100 dark:bg-accent-900/30
            text-accent-700 dark:text-accent-400
            hover:bg-accent-200 dark:hover:bg-accent-900/50
            transition-all duration-200"
        >
          View
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
        )}
      </div>

      {/* Text snippet */}
      {source.text_snippet && (
        <p className="text-sm text-ink-600 dark:text-ink-300 line-clamp-2 pl-10">
          "{source.text_snippet}"
        </p>
      )}
    </div>
  );
}
