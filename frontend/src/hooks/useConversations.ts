import { useCallback, useEffect, useState } from 'react';
import { useChatStore } from '../stores/chatStore';
import type { Message } from '../types';
import * as api from '../api/client';

export function useConversations() {
  const {
    conversations,
    currentConversationId,
    selectedCollectionId,
    selectConversation,
    setConversations,
    addConversation,
    updateConversation: updateConversationStore,
    deleteConversation: deleteConversationStore,
    setMessages,
  } = useChatStore();

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load conversations from backend when collection changes
  useEffect(() => {
    if (!selectedCollectionId) {
      setConversations([]);
      return;
    }

    const loadConversations = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const convs = await api.getConversations();
        // Filter by selected collection
        const filtered = convs.filter(c => c.collection_id === selectedCollectionId);
        setConversations(filtered);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load conversations');
        console.error('Failed to load conversations:', err);
      } finally {
        setIsLoading(false);
      }
    };

    loadConversations();
  }, [selectedCollectionId, setConversations]);

  // Create new conversation via API
  const createNew = useCallback(
    async (title?: string) => {
      if (!selectedCollectionId) return undefined;

      try {
        const conversation = await api.createConversation(
          selectedCollectionId,
          title || 'New conversation'
        );
        addConversation(conversation);
        selectConversation(conversation.id);
        setMessages([]);
        return conversation;
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to create conversation');
        console.error('Failed to create conversation:', err);
        return undefined;
      }
    },
    [selectedCollectionId, addConversation, selectConversation, setMessages]
  );

  // Load conversation with messages when selected
  const select = useCallback(
    async (id: string | null) => {
      if (!id) {
        selectConversation(null);
        setMessages([]);
        return;
      }

      try {
        const conv = await api.getConversation(id);
        selectConversation(id);
        // Convert API messages to frontend format
        const messages: Message[] = (conv.messages || []).map(m => ({
          id: m.id,
          role: m.role as 'user' | 'assistant',
          content: m.content,
          sources: m.sources,
          timestamp: m.created_at ? new Date(m.created_at as string) : new Date(),
        }));
        setMessages(messages);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load conversation');
        console.error('Failed to load conversation:', err);
        // Still select it locally
        selectConversation(id);
        setMessages([]);
      }
    },
    [selectConversation, setMessages]
  );

  // Rename conversation via API
  const rename = useCallback(
    async (id: string, title: string) => {
      try {
        await api.updateConversation(id, title);
        updateConversationStore(id, { title });
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to rename conversation');
        console.error('Failed to rename conversation:', err);
      }
    },
    [updateConversationStore]
  );

  // Delete conversation via API
  const remove = useCallback(
    async (id: string) => {
      try {
        await api.deleteConversation(id);
        deleteConversationStore(id);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to delete conversation');
        console.error('Failed to delete conversation:', err);
      }
    },
    [deleteConversationStore]
  );

  return {
    conversations,
    currentConversationId,
    isLoading,
    error,
    select,
    create: createNew,
    rename,
    remove,
  };
}
