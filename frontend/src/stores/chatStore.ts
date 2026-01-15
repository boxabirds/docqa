import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Message, Conversation, Collection, Theme, Source } from '../types';

// Demo collection - Digital Twin PRD GraphRAG (id=10 matches the actual database)
const CREDO4_DEMO: Collection = {
  id: 10,
  name: 'Digital Twin PRD',
  type: 'graphrag',
  file_count: 204,
  created_at: new Date(),
};

interface ChatState {
  // Auth (optional - defaults to anonymous)
  user: { id: string; username: string } | null;

  // Theme
  theme: Theme;
  setTheme: (theme: Theme) => void;

  // Collections (GraphRAG only)
  collections: Collection[];
  selectedCollectionId: number | null;
  setCollections: (collections: Collection[]) => void;
  selectCollection: (id: number) => void;
  loadDemoCollection: () => void;

  // Conversations
  conversations: Conversation[];
  currentConversationId: string | null;
  setConversations: (conversations: Conversation[]) => void;
  selectConversation: (id: string | null) => void;
  addConversation: (conversation: Conversation) => void;
  updateConversation: (id: string, updates: Partial<Conversation>) => void;
  deleteConversation: (id: string) => void;

  // Messages
  messages: Message[];
  sources: Source[];
  setMessages: (messages: Message[]) => void;
  addMessage: (message: Message) => void;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  appendToMessage: (id: string, content: string) => void;
  setSources: (sources: Source[]) => void;

  // UI State
  isStreaming: boolean;
  isSidebarOpen: boolean;
  isPdfViewerOpen: boolean;
  pdfViewerFile: { id: string; name: string; page: number } | null;
  inputValue: string;
  setIsStreaming: (isStreaming: boolean) => void;
  toggleSidebar: () => void;
  openPdfViewer: (file: { id: string; name: string; page: number }) => void;
  closePdfViewer: () => void;
  setInputValue: (value: string) => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set) => ({
      // Auth (anonymous by default)
      user: { id: 'anonymous', username: 'User' },

      // Theme
      theme: 'dark',
      setTheme: (theme) => set({ theme }),

      // Collections (GraphRAG only - starts empty, user loads demo)
      collections: [],
      selectedCollectionId: null,
      setCollections: (collections) => set({ collections }),
      selectCollection: (id) => set({ selectedCollectionId: id, currentConversationId: null, messages: [] }),
      loadDemoCollection: () => {
        set({
          collections: [CREDO4_DEMO],
          selectedCollectionId: CREDO4_DEMO.id,
          currentConversationId: null,
          messages: [],
        });
      },

      // Conversations
      conversations: [],
      currentConversationId: null,
      setConversations: (conversations) => set({ conversations }),
      selectConversation: (id) => set({ currentConversationId: id, messages: [], sources: [] }),
      addConversation: (conversation) =>
        set((state) => ({ conversations: [conversation, ...state.conversations] })),
      updateConversation: (id, updates) =>
        set((state) => ({
          conversations: state.conversations.map((c) =>
            c.id === id ? { ...c, ...updates } : c
          ),
        })),
      deleteConversation: (id) =>
        set((state) => ({
          conversations: state.conversations.filter((c) => c.id !== id),
          currentConversationId:
            state.currentConversationId === id ? null : state.currentConversationId,
        })),

      // Messages
      messages: [],
      sources: [],
      setMessages: (messages) => set({ messages }),
      addMessage: (message) =>
        set((state) => ({ messages: [...state.messages, message] })),
      updateMessage: (id, updates) =>
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, ...updates } : m
          ),
        })),
      appendToMessage: (id, content) =>
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, content: m.content + content } : m
          ),
        })),
      setSources: (sources) => set({ sources }),

      // UI State
      isStreaming: false,
      isSidebarOpen: true,
      isPdfViewerOpen: false,
      pdfViewerFile: null,
      inputValue: '',
      setIsStreaming: (isStreaming) => set({ isStreaming }),
      toggleSidebar: () => set((state) => ({ isSidebarOpen: !state.isSidebarOpen })),
      openPdfViewer: (file) => set({ isPdfViewerOpen: true, pdfViewerFile: file }),
      closePdfViewer: () => set({ isPdfViewerOpen: false, pdfViewerFile: null }),
      setInputValue: (value) => set({ inputValue: value }),
    }),
    {
      name: 'docqa-storage',
      partialize: (state) => ({
        theme: state.theme,
        // Also persist collections so selectedCollectionId stays valid
        collections: state.collections,
        selectedCollectionId: state.selectedCollectionId,
      }),
    }
  )
);
