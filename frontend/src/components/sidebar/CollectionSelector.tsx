import { useState } from 'react';
import { useChatStore } from '../../stores/chatStore';

export function CollectionSelector() {
  const { collections, selectedCollectionId, selectCollection, loadDemoCollection } = useChatStore();
  const [isOpen, setIsOpen] = useState(false);

  const selectedCollection = collections.find((c) => c.id === selectedCollectionId);

  // No collections loaded yet
  if (collections.length === 0) {
    return (
      <div>
        <label className="block text-xs font-medium text-ink-500 dark:text-ink-400 mb-2 uppercase tracking-wider">
          Documents
        </label>
        <button
          onClick={loadDemoCollection}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl
            bg-accent-500 hover:bg-accent-600
            text-white text-sm font-medium
            transition-all duration-200"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          Load demo documents
        </button>
      </div>
    );
  }

  return (
    <div className="relative">
      <label className="block text-xs font-medium text-ink-500 dark:text-ink-400 mb-2 uppercase tracking-wider">
        Documents
      </label>

      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`
          w-full flex items-center justify-between gap-2 px-4 py-3 rounded-xl
          bg-white dark:bg-ink-800
          border-2 ${isOpen ? 'border-accent-400 dark:border-accent-500' : 'border-ink-200 dark:border-ink-700'}
          hover:border-ink-300 dark:hover:border-ink-600
          transition-all duration-200
        `}
      >
        <div className="flex items-center gap-3 min-w-0">
          {/* Document icon */}
          <div className="w-8 h-8 rounded-lg bg-accent-100 dark:bg-accent-900/30 flex items-center justify-center flex-shrink-0">
            <svg
              className="w-4 h-4 text-accent-600 dark:text-accent-400"
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

          {/* Name and count */}
          <div className="min-w-0">
            <p className="text-sm font-medium text-ink-900 dark:text-ink-100 truncate">
              {selectedCollection?.name || 'Select...'}
            </p>
            {selectedCollection && (
              <p className="text-xs text-ink-500 dark:text-ink-400">
                {selectedCollection.file_count} files
              </p>
            )}
          </div>
        </div>

        {/* Chevron */}
        <svg
          className={`w-5 h-5 text-ink-400 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Dropdown */}
      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute left-0 right-0 mt-2 z-20 py-2 rounded-xl bg-white dark:bg-ink-800 border border-ink-200 dark:border-ink-700 shadow-editorial-lg max-h-64 overflow-y-auto">
            {collections.map((collection) => (
              <button
                key={collection.id}
                onClick={() => {
                  selectCollection(collection.id);
                  setIsOpen(false);
                }}
                className={`
                  w-full flex items-center gap-3 px-4 py-3
                  ${collection.id === selectedCollectionId
                    ? 'bg-accent-50 dark:bg-accent-900/20'
                    : 'hover:bg-ink-50 dark:hover:bg-ink-700'
                  }
                  transition-colors duration-150
                `}
              >
                <div className="flex-1 text-left">
                  <p className="text-sm font-medium text-ink-900 dark:text-ink-100">
                    {collection.name}
                  </p>
                  <p className="text-xs text-ink-500 dark:text-ink-400">
                    {collection.file_count} files
                  </p>
                </div>

                {collection.id === selectedCollectionId && (
                  <svg className="w-4 h-4 text-accent-500" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" />
                  </svg>
                )}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
