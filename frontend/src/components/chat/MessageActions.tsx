import { useState } from 'react';

interface MessageActionsProps {
  messageId: string;
  content: string;
}

export function MessageActions({ messageId, content }: MessageActionsProps) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'up' | 'down' | null>(null);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRegenerate = async () => {
    // TODO: Implement regenerate via API
    console.log('Regenerate message:', messageId);
  };

  const handleFeedback = async (type: 'up' | 'down') => {
    setFeedback(type);
    // TODO: Send feedback to API
    console.log('Feedback:', messageId, type);
  };

  return (
    <div className="flex items-center gap-1">
      {/* Copy */}
      <button
        onClick={handleCopy}
        className="btn-ghost flex items-center gap-1.5 text-xs"
        title="Copy response"
      >
        {copied ? (
          <>
            <svg className="w-4 h-4 text-emerald-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            Copied
          </>
        ) : (
          <>
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
              />
            </svg>
            Copy
          </>
        )}
      </button>

      {/* Regenerate */}
      <button
        onClick={handleRegenerate}
        className="btn-ghost flex items-center gap-1.5 text-xs"
        title="Regenerate response"
      >
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
          />
        </svg>
        Regenerate
      </button>

      {/* Divider */}
      <div className="w-px h-4 bg-ink-200 dark:bg-ink-700 mx-2" />

      {/* Thumbs up */}
      <button
        onClick={() => handleFeedback('up')}
        className={`btn-icon ${feedback === 'up' ? 'text-emerald-500 bg-emerald-500/10' : ''}`}
        title="Good response"
      >
        <svg className="w-4 h-4" fill={feedback === 'up' ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M14 10h4.764a2 2 0 011.789 2.894l-3.5 7A2 2 0 0115.263 21h-4.017c-.163 0-.326-.02-.485-.06L7 20m7-10V5a2 2 0 00-2-2h-.095c-.5 0-.905.405-.905.905 0 .714-.211 1.412-.608 2.006L7 11v9m7-10h-2M7 20H5a2 2 0 01-2-2v-6a2 2 0 012-2h2.5"
          />
        </svg>
      </button>

      {/* Thumbs down */}
      <button
        onClick={() => handleFeedback('down')}
        className={`btn-icon ${feedback === 'down' ? 'text-rose-500 bg-rose-500/10' : ''}`}
        title="Poor response"
      >
        <svg className="w-4 h-4" fill={feedback === 'down' ? 'currentColor' : 'none'} stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M10 14H5.236a2 2 0 01-1.789-2.894l3.5-7A2 2 0 018.736 3h4.018a2 2 0 01.485.06l3.76.94m-7 10v5a2 2 0 002 2h.096c.5 0 .905-.405.905-.904 0-.715.211-1.413.608-2.008L17 13V4m-7 10h2m5-10h2a2 2 0 012 2v6a2 2 0 01-2 2h-2.5"
          />
        </svg>
      </button>
    </div>
  );
}
