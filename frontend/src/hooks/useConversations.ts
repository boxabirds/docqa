import { useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import type { Conversation } from '../types';
import { generateId } from '../utils/uuid';

export function useConversations() {
  const {
    conversations,
    currentConversationId,
    selectedCollectionId,
    selectConversation,
    addConversation,
    updateConversation,
    deleteConversation,
    setMessages,
  } = useChatStore();

  const createNew = useCallback(
    (title?: string) => {
      if (!selectedCollectionId) return;

      const conversation: Conversation = {
        id: generateId(),
        title: title || 'New conversation',
        collection_id: selectedCollectionId,
        updated_at: new Date(),
        message_count: 0,
      };

      addConversation(conversation);
      selectConversation(conversation.id);
      setMessages([]);
      return conversation;
    },
    [selectedCollectionId, addConversation, selectConversation, setMessages]
  );

  const rename = useCallback(
    (id: string, title: string) => {
      updateConversation(id, { title });
    },
    [updateConversation]
  );

  const remove = useCallback(
    (id: string) => {
      deleteConversation(id);
    },
    [deleteConversation]
  );

  return {
    conversations,
    currentConversationId,
    select: selectConversation,
    create: createNew,
    rename,
    remove,
  };
}
