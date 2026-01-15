import { useState, type CSSProperties } from 'react';
import ReactMarkdown from 'react-markdown';
import type { Message } from '../../types';
import { CodeBlock } from './CodeBlock';
import { SourcesPanel } from '../sources/SourcesPanel';
import { MessageActions } from './MessageActions';

interface MessageItemProps {
  message: Message;
  isLast: boolean;
  style?: CSSProperties;
}

export function MessageItem({ message, isLast, style }: MessageItemProps) {
  const [isHovered, setIsHovered] = useState(false);
  const isUser = message.role === 'user';

  return (
    <div
      className="animate-slide-up"
      style={style}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      <div
        className={`
          rounded-2xl p-5 relative
          ${isUser ? 'message-user' : 'message-assistant'}
        `}
      >
        {/* Role indicator */}
        <div className="flex items-start gap-4">
          {/* Avatar */}
          <div
            className={`
              flex-shrink-0 w-8 h-8 rounded-lg flex items-center justify-center
              ${isUser
                ? 'bg-ink-200 dark:bg-ink-700 text-ink-600 dark:text-ink-300'
                : 'bg-accent-100 dark:bg-accent-900/40 text-accent-700 dark:text-accent-400'
              }
            `}
          >
            {isUser ? (
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z" />
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm-7 12h-2v-2h2v2zm0-4h-2V6h2v4z" />
              </svg>
            )}
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-sm font-medium text-ink-600 dark:text-ink-300">
                {isUser ? 'You' : 'Assistant'}
              </span>
              <span className="text-xs text-ink-400 dark:text-ink-500">
                {formatTime(message.timestamp)}
              </span>
            </div>

            {/* Message content with markdown */}
            <div className="prose prose-ink dark:prose-invert max-w-none prose-code">
              <ReactMarkdown
                components={{
                  code({ className, children, ...props }) {
                    const match = /language-(\w+)/.exec(className || '');
                    const inline = !match;
                    return inline ? (
                      <code className={className} {...props}>
                        {children}
                      </code>
                    ) : (
                      <CodeBlock language={match[1]}>
                        {String(children).replace(/\n$/, '')}
                      </CodeBlock>
                    );
                  },
                }}
              >
                {message.content}
              </ReactMarkdown>

              {/* Streaming cursor */}
              {message.isStreaming && (
                <span className="inline-block w-2 h-5 ml-1 bg-accent-500 animate-pulse-soft" />
              )}
            </div>
          </div>
        </div>

        {/* Sources panel for assistant messages */}
        {!isUser && message.sources && message.sources.length > 0 && (
          <div className="mt-4 ml-12">
            <SourcesPanel sources={message.sources} />
          </div>
        )}

        {/* Actions (show on hover or for last message) */}
        {!isUser && (isHovered || isLast) && !message.isStreaming && (
          <div className="mt-4 ml-12 animate-fade-in">
            <MessageActions messageId={message.id} content={message.content} />
          </div>
        )}
      </div>
    </div>
  );
}

function formatTime(date: Date): string {
  return new Date(date).toLocaleTimeString('en-US', {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}
