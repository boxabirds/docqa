import { useRef, useEffect } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { MessageList } from './MessageList';
import { MessageInput } from './MessageInput';
import { TypingIndicator } from './TypingIndicator';

export function ChatWindow() {
  const { messages, isStreaming, selectedCollectionId, collections, toggleSidebar, isSidebarOpen } = useChatStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: 'smooth',
      });
    }
  }, [messages, isStreaming]);

  const selectedCollection = collections.find((c) => c.id === selectedCollectionId);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="flex items-center justify-between px-6 py-4 border-b border-ink-200/50 dark:border-ink-800/50">
        <div className="flex items-center gap-4">
          {/* Sidebar toggle */}
          <button
            onClick={toggleSidebar}
            className="btn-icon"
            title={isSidebarOpen ? 'Hide sidebar (Cmd+B)' : 'Show sidebar (Cmd+B)'}
          >
            <svg
              className="w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M4 6h16M4 12h16M4 18h16"
              />
            </svg>
          </button>

          {/* Title */}
          <div>
            <h1 className="font-display text-xl font-semibold text-ink-900 dark:text-ink-100">
              DocQA
            </h1>
            {selectedCollection && (
              <p className="text-sm text-ink-500 dark:text-ink-400">
                {selectedCollection.name}
              </p>
            )}
          </div>
        </div>

        {/* File count badge */}
        {selectedCollection && (
          <div className="flex items-center gap-2 text-sm text-ink-500 dark:text-ink-400">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            {selectedCollection.file_count} files
          </div>
        )}
      </header>

      {/* Messages area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 md:px-6 lg:px-8 py-6"
      >
        {messages.length === 0 ? (
          <EmptyState />
        ) : (
          <>
            <MessageList messages={messages} />
            {isStreaming && <TypingIndicator />}
          </>
        )}
      </div>

      {/* Input area */}
      <div className="px-4 md:px-6 lg:px-8 pb-6">
        <MessageInput />
      </div>
    </div>
  );
}

function EmptyState() {
  const { selectedCollectionId, collections, loadDemoCollection, setInputValue } = useChatStore();
  const collection = collections.find((c) => c.id === selectedCollectionId);
  const hasNoCollections = collections.length === 0;

  return (
    <div className="flex flex-col items-center justify-center h-full text-center animate-fade-in">
      {/* Decorative element */}
      <div className="relative mb-8">
        <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-accent-300 to-accent-500 opacity-20 blur-2xl absolute inset-0" />
        <div className="w-20 h-20 rounded-2xl border-2 border-ink-200 dark:border-ink-700 flex items-center justify-center relative">
          <svg
            className="w-10 h-10 text-ink-400 dark:text-ink-500"
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
        </div>
      </div>

      <h2 className="font-display text-2xl font-semibold text-ink-900 dark:text-ink-100 mb-2">
        {collection ? `Ask about ${collection.name}` : 'Document Q&A'}
      </h2>
      <p className="text-ink-500 dark:text-ink-400 max-w-md mb-8">
        {collection
          ? "Ask questions about your documents. I'll search through the collection and provide answers with source references."
          : 'Load documents to start asking questions. GraphRAG will analyze and index your files for intelligent retrieval.'}
      </p>

      {/* Load demo button when no collections */}
      {hasNoCollections && (
        <button
          onClick={loadDemoCollection}
          className="flex items-center gap-3 px-6 py-4 rounded-2xl
            bg-accent-500 hover:bg-accent-600
            text-white font-medium
            shadow-lg shadow-accent-500/25
            hover:shadow-xl hover:shadow-accent-500/30
            active:scale-[0.98]
            transition-all duration-200"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          Load demo documents
        </button>
      )}

      {/* Suggested prompts when collection is loaded */}
      {collection && (
        <div className="flex flex-wrap gap-2 justify-center max-w-lg">
          {[
            'What is CReDO?',
            'Is Cadent cost of heat failures in scope?',
            'What are the key features?',
          ].map((prompt) => (
            <button
              key={prompt}
              className="px-4 py-2 rounded-xl text-sm
                bg-white dark:bg-ink-900
                border border-ink-200 dark:border-ink-700
                text-ink-600 dark:text-ink-300
                hover:border-accent-400 dark:hover:border-accent-500
                hover:text-ink-900 dark:hover:text-ink-100
                transition-all duration-200"
              onClick={() => setInputValue(prompt)}
            >
              {prompt}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
