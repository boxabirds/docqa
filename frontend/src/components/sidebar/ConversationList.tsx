import { useState } from 'react';
import { useChatStore } from '../../stores/chatStore';
import type { Conversation } from '../../types';

export function ConversationList() {
  const { conversations, currentConversationId, selectConversation, deleteConversation, updateConversation } =
    useChatStore();

  if (conversations.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-ink-400 dark:text-ink-500">
          No conversations yet
        </p>
      </div>
    );
  }

  // Group conversations by date
  const grouped = groupByDate(conversations);

  return (
    <div className="space-y-6">
      {Object.entries(grouped).map(([label, convs]) => (
        <div key={label}>
          <h3 className="text-xs font-medium text-ink-400 dark:text-ink-500 uppercase tracking-wider mb-2 px-2">
            {label}
          </h3>
          <div className="space-y-1">
            {convs.map((conv) => (
              <ConversationItem
                key={conv.id}
                conversation={conv}
                isActive={conv.id === currentConversationId}
                onSelect={() => selectConversation(conv.id)}
                onDelete={() => deleteConversation(conv.id)}
                onRename={(title) => updateConversation(conv.id, { title })}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onRename: (title: string) => void;
}

function ConversationItem({ conversation, isActive, onSelect, onDelete, onRename }: ConversationItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(conversation.title);
  const [showMenu, setShowMenu] = useState(false);

  const handleRename = () => {
    if (editValue.trim() && editValue !== conversation.title) {
      onRename(editValue.trim());
    }
    setIsEditing(false);
  };

  return (
    <div
      className={`
        group relative rounded-xl px-3 py-2.5 cursor-pointer
        ${isActive
          ? 'bg-ink-100 dark:bg-ink-800'
          : 'hover:bg-ink-100/50 dark:hover:bg-ink-800/50'
        }
        transition-colors duration-150
      `}
      onClick={() => !isEditing && onSelect()}
    >
      <div className="flex items-center gap-3">
        {/* Icon */}
        <svg
          className={`w-4 h-4 flex-shrink-0 ${isActive ? 'text-accent-500' : 'text-ink-400 dark:text-ink-500'}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={1.5}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
          />
        </svg>

        {/* Title */}
        {isEditing ? (
          <input
            type="text"
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={handleRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleRename();
              if (e.key === 'Escape') setIsEditing(false);
            }}
            className="flex-1 bg-transparent border-b border-accent-400 outline-none text-sm text-ink-900 dark:text-ink-100"
            autoFocus
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className="flex-1 text-sm text-ink-700 dark:text-ink-200 truncate">
            {conversation.title}
          </span>
        )}

        {/* Menu button */}
        <button
          className={`
            p-1 rounded-md
            ${showMenu || isActive ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}
            hover:bg-ink-200 dark:hover:bg-ink-700
            transition-opacity duration-150
          `}
          onClick={(e) => {
            e.stopPropagation();
            setShowMenu(!showMenu);
          }}
        >
          <svg className="w-4 h-4 text-ink-500" fill="currentColor" viewBox="0 0 24 24">
            <path d="M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z" />
          </svg>
        </button>
      </div>

      {/* Dropdown menu */}
      {showMenu && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setShowMenu(false)} />
          <div className="absolute right-2 top-full mt-1 z-20 py-1 rounded-xl bg-white dark:bg-ink-800 border border-ink-200 dark:border-ink-700 shadow-editorial-lg min-w-32">
            <button
              className="w-full px-3 py-2 text-left text-sm text-ink-700 dark:text-ink-200 hover:bg-ink-100 dark:hover:bg-ink-700"
              onClick={(e) => {
                e.stopPropagation();
                setIsEditing(true);
                setShowMenu(false);
              }}
            >
              Rename
            </button>
            <button
              className="w-full px-3 py-2 text-left text-sm text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20"
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
                setShowMenu(false);
              }}
            >
              Delete
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function groupByDate(conversations: Conversation[]): Record<string, Conversation[]> {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 86400000);
  const weekAgo = new Date(today.getTime() - 7 * 86400000);

  const groups: Record<string, Conversation[]> = {};

  for (const conv of conversations) {
    const date = new Date(conv.updated_at);
    let label: string;

    if (date >= today) {
      label = 'Today';
    } else if (date >= yesterday) {
      label = 'Yesterday';
    } else if (date >= weekAgo) {
      label = 'This week';
    } else {
      label = 'Older';
    }

    if (!groups[label]) groups[label] = [];
    groups[label].push(conv);
  }

  return groups;
}
