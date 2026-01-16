import { useChatStore } from '../../stores/chatStore';
import { useConversations } from '../../hooks/useConversations';
import { ConversationList } from './ConversationList';
import { CollectionSelector } from './CollectionSelector';
import { ThemeToggle } from './ThemeToggle';

export function Sidebar() {
  const { user, selectedCollectionId } = useChatStore();
  const { create } = useConversations();

  const handleNewChat = async () => {
    if (selectedCollectionId) {
      await create();
    }
  };

  return (
    <div className="h-full w-72 flex flex-col bg-paper-50 dark:bg-ink-900 border-r border-ink-200/50 dark:border-ink-800/50">
      {/* Header */}
      <div className="p-4 border-b border-ink-200/50 dark:border-ink-800/50">
        <div className="flex items-center justify-between mb-4">
          <h1 className="font-display text-lg font-semibold text-ink-900 dark:text-ink-100">
            DocQA
          </h1>
          <ThemeToggle />
        </div>

        {/* New chat button */}
        <button
          onClick={handleNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl
            border-2 border-dashed border-ink-300 dark:border-ink-700
            text-ink-600 dark:text-ink-400
            hover:border-accent-400 dark:hover:border-accent-500
            hover:text-ink-900 dark:hover:text-ink-100
            hover:bg-accent-50 dark:hover:bg-accent-900/20
            transition-all duration-200"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New conversation
        </button>
      </div>

      {/* Collection selector */}
      <div className="p-4 border-b border-ink-200/50 dark:border-ink-800/50">
        <CollectionSelector />
      </div>

      {/* Conversations list */}
      <div className="flex-1 overflow-y-auto p-4">
        <ConversationList />
      </div>

      {/* User section */}
      <div className="p-4 border-t border-ink-200/50 dark:border-ink-800/50">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-ink-200 dark:bg-ink-700 flex items-center justify-center">
            <span className="text-sm font-medium text-ink-600 dark:text-ink-300">
              {user?.username?.[0]?.toUpperCase() || 'U'}
            </span>
          </div>
          <span className="text-sm font-medium text-ink-700 dark:text-ink-300">
            {user?.username || 'User'}
          </span>
        </div>
      </div>
    </div>
  );
}
