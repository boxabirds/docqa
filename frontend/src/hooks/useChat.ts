import { useRef, useCallback } from 'react';
import { useChatStore } from '../stores/chatStore';
import { streamChat, abortChat, sendFeedback, regenerateMessage, createConversation } from '../api/client';
import { generateId } from '../utils/uuid';

export function useChat() {
  const abortControllerRef = useRef<AbortController | null>(null);

  const {
    messages,
    sources,
    isStreaming,
    selectedCollectionId,
    currentConversationId,
    addMessage,
    updateMessage,
    appendToMessage,
    setSources,
    setIsStreaming,
    addConversation,
    selectConversation,
  } = useChatStore();

  const sendMessage = useCallback(
    async (content: string) => {
      if (!selectedCollectionId || isStreaming) return;

      const trimmed = content.trim();
      if (!trimmed) return;

      // Auto-create conversation if one doesn't exist
      let conversationId = currentConversationId;
      if (!conversationId) {
        try {
          const conv = await createConversation(selectedCollectionId, 'New conversation');
          conversationId = conv.id;
          addConversation(conv);
          selectConversation(conv.id);
        } catch (error) {
          console.error('Failed to create conversation:', error);
          // Continue without conversation - messages won't be saved
        }
      }

      // Add user message
      const userMessage = {
        id: generateId(),
        role: 'user' as const,
        content: trimmed,
        timestamp: new Date(),
      };
      addMessage(userMessage);

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
      abortControllerRef.current = new AbortController();

      try {
        const stream = streamChat(
          {
            message: trimmed,
            conversation_id: conversationId || undefined,
            collection_id: selectedCollectionId,
          },
          abortControllerRef.current.signal
        );

        for await (const event of stream) {
          switch (event.type) {
            case 'chat':
              if (event.content) {
                appendToMessage(assistantId, event.content);
              }
              break;

            case 'info':
              if (event.sources) {
                setSources(event.sources);
                updateMessage(assistantId, { sources: event.sources });
              }
              break;

            case 'done':
              updateMessage(assistantId, {
                isStreaming: false,
                id: event.message_id || assistantId,
              });
              break;

            case 'error':
              updateMessage(assistantId, {
                content: `Error: ${event.error || 'Unknown error'}`,
                isStreaming: false,
              });
              break;
          }
        }
      } catch (error) {
        if ((error as Error).name === 'AbortError') {
          // User cancelled
          appendToMessage(assistantId, ' [stopped]');
          updateMessage(assistantId, { isStreaming: false });
        } else {
          console.error('Chat error:', error);
          updateMessage(assistantId, {
            content: `Error: ${(error as Error).message}`,
            isStreaming: false,
          });
        }
      } finally {
        setIsStreaming(false);
        abortControllerRef.current = null;
      }
    },
    [
      selectedCollectionId,
      currentConversationId,
      isStreaming,
      addMessage,
      updateMessage,
      appendToMessage,
      setSources,
      setIsStreaming,
      addConversation,
      selectConversation,
    ]
  );

  const stopGeneration = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    // Also notify server
    try {
      await abortChat();
    } catch {
      // Ignore abort errors
    }
    setIsStreaming(false);
  }, [setIsStreaming]);

  const handleRegenerate = useCallback(
    async (messageId: string) => {
      if (isStreaming) return;

      // Find the message to regenerate
      const messageIndex = messages.findIndex((m) => m.id === messageId);
      if (messageIndex === -1) return;

      // Clear the message content and mark as streaming
      updateMessage(messageId, { content: '', isStreaming: true });
      setIsStreaming(true);

      try {
        await regenerateMessage(messageId);
        // The response would come through SSE, but for now just mark as done
        updateMessage(messageId, { isStreaming: false });
      } catch (error) {
        updateMessage(messageId, {
          content: `Error regenerating: ${(error as Error).message}`,
          isStreaming: false,
        });
      } finally {
        setIsStreaming(false);
      }
    },
    [messages, isStreaming, updateMessage, setIsStreaming]
  );

  const handleFeedback = useCallback(
    async (messageId: string, rating: 'up' | 'down', comment?: string) => {
      try {
        await sendFeedback(messageId, rating, comment);
      } catch (error) {
        console.error('Failed to send feedback:', error);
      }
    },
    []
  );

  return {
    messages,
    sources,
    isStreaming,
    sendMessage,
    stopGeneration,
    regenerate: handleRegenerate,
    feedback: handleFeedback,
  };
}
