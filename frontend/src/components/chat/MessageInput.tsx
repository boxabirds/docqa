import { useRef, useEffect, type KeyboardEvent } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { generateId } from '../../utils/uuid';
import { streamChat } from '../../api/backend';

export function MessageInput() {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { isStreaming, selectedCollectionId, addMessage, setIsStreaming, inputValue: value, setInputValue: setValue } = useChatStore();

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [value]);

  // Focus on mount
  useEffect(() => {
    textareaRef.current?.focus();
  }, []);

  const handleSubmit = async () => {
    const trimmed = value.trim();
    if (!trimmed || isStreaming || !selectedCollectionId) return;

    // Add user message
    const userMessage = {
      id: generateId(),
      role: 'user' as const,
      content: trimmed,
      timestamp: new Date(),
    };
    addMessage(userMessage);
    setValue('');

    // Add placeholder for assistant
    const assistantId = generateId();
    addMessage({
      id: assistantId,
      role: 'assistant',
      content: '',
      timestamp: new Date(),
      isStreaming: true,
    });

    setIsStreaming(true);

    try {
      // Call FastAPI backend
      for await (const event of streamChat(trimmed, selectedCollectionId)) {
        if (event.type === 'chat' && event.content) {
          useChatStore.getState().appendToMessage(assistantId, event.content);
        } else if (event.type === 'info' && event.sources) {
          useChatStore.getState().updateMessage(assistantId, { sources: event.sources });
        } else if (event.type === 'error') {
          useChatStore.getState().appendToMessage(assistantId, `Error: ${event.error || 'Unknown error'}`);
        }
      }
    } catch (error) {
      console.error('Chat error:', error);
      useChatStore.getState().appendToMessage(
        assistantId,
        `Error: ${error instanceof Error ? error.message : 'Unknown error'}`
      );
    } finally {
      useChatStore.getState().updateMessage(assistantId, { isStreaming: false });
      setIsStreaming(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter to submit, Shift+Enter for new line
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
    // Escape to stop generation
    if (e.key === 'Escape' && isStreaming) {
      // TODO: Abort streaming
      setIsStreaming(false);
    }
  };

  const handleStop = () => {
    // TODO: Abort the streaming request
    setIsStreaming(false);
  };

  const isDisabled = !selectedCollectionId;

  return (
    <div className="max-w-4xl mx-auto">
      {/* Stop button */}
      {isStreaming && (
        <div className="flex justify-center mb-4 animate-fade-in">
          <button
            onClick={handleStop}
            className="flex items-center gap-2 px-4 py-2 rounded-xl
              bg-ink-900 dark:bg-ink-100
              text-white dark:text-ink-900
              hover:bg-ink-800 dark:hover:bg-ink-200
              shadow-editorial
              transition-all duration-200"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <rect x="6" y="6" width="12" height="12" rx="1" />
            </svg>
            Stop generating
          </button>
        </div>
      )}

      {/* Input container */}
      <div
        className={`
          relative rounded-2xl
          bg-white dark:bg-ink-900
          border-2 ${isDisabled ? 'border-ink-200 dark:border-ink-800' : 'border-ink-300 dark:border-ink-700'}
          focus-within:border-accent-400 dark:focus-within:border-accent-500
          focus-within:ring-4 focus-within:ring-accent-400/10 dark:focus-within:ring-accent-500/10
          shadow-editorial
          transition-all duration-200
          ${isDisabled ? 'opacity-60 cursor-not-allowed' : ''}
        `}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={isDisabled ? 'Select a collection to start...' : 'Ask a question about your documents...'}
          disabled={isDisabled || isStreaming}
          rows={1}
          className="w-full px-5 py-4 pr-14 resize-none
            bg-transparent
            text-ink-900 dark:text-ink-100
            placeholder:text-ink-400 dark:placeholder:text-ink-500
            outline-none
            disabled:cursor-not-allowed"
        />

        {/* Send button */}
        <button
          onClick={handleSubmit}
          disabled={!value.trim() || isStreaming || isDisabled}
          className={`
            absolute right-3 bottom-3
            w-10 h-10 rounded-xl
            flex items-center justify-center
            transition-all duration-200
            ${value.trim() && !isStreaming && !isDisabled
              ? 'bg-ink-900 dark:bg-ink-100 text-white dark:text-ink-900 hover:scale-105 active:scale-95 shadow-editorial'
              : 'bg-ink-200 dark:bg-ink-800 text-ink-400 dark:text-ink-500 cursor-not-allowed'
            }
          `}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
            />
          </svg>
        </button>
      </div>

      {/* Hints */}
      <div className="flex items-center justify-center gap-4 mt-3 text-xs text-ink-400 dark:text-ink-500">
        <span className="flex items-center gap-1">
          <kbd className="px-1.5 py-0.5 rounded bg-ink-100 dark:bg-ink-800 font-mono text-[10px]">Enter</kbd>
          to send
        </span>
        <span className="flex items-center gap-1">
          <kbd className="px-1.5 py-0.5 rounded bg-ink-100 dark:bg-ink-800 font-mono text-[10px]">Shift+Enter</kbd>
          for new line
        </span>
        {isStreaming && (
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 rounded bg-ink-100 dark:bg-ink-800 font-mono text-[10px]">Esc</kbd>
            to stop
          </span>
        )}
      </div>
    </div>
  );
}
