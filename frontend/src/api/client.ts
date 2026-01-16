import type { Collection, Conversation, Message, Source, IndexingProgress } from '../types';

const API_BASE = '/api';

// Helper to get auth token
function getToken(): string | null {
  const stored = localStorage.getItem('docqa-storage');
  if (stored) {
    try {
      const parsed = JSON.parse(stored);
      return parsed.state?.token || null;
    } catch {
      return null;
    }
  }
  return null;
}

// Helper for authenticated fetch
async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = getToken();
  const headers = new Headers(options.headers);

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  if (!headers.has('Content-Type') && !(options.body instanceof FormData)) {
    headers.set('Content-Type', 'application/json');
  }

  return fetch(`${API_BASE}${url}`, {
    ...options,
    headers,
  });
}

// ============ Auth ============

export interface LoginResponse {
  access_token: string;
  token_type: string;
  user: { id: string; username: string };
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const response = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    throw new Error('Invalid credentials');
  }

  return response.json();
}

export async function getCurrentUser() {
  const response = await authFetch('/auth/me');
  if (!response.ok) throw new Error('Not authenticated');
  return response.json();
}

// ============ Collections ============

export async function getCollections(): Promise<Collection[]> {
  const response = await authFetch('/collections');
  if (!response.ok) throw new Error('Failed to fetch collections');
  return response.json();
}

export async function createCollection(
  name: string,
  type: 'graphrag' | 'vector',
  files: File[],
  onProgress?: (progress: IndexingProgress) => void
): Promise<Collection> {
  const formData = new FormData();
  formData.append('name', name);
  formData.append('type', type);
  files.forEach((file) => formData.append('files', file));

  const response = await authFetch('/collections', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) throw new Error('Failed to create collection');

  // Handle SSE stream for progress
  if (response.headers.get('content-type')?.includes('text/event-stream') && onProgress) {
    const reader = response.body?.getReader();
    if (reader) {
      await processSSEStream(reader, (event, data) => {
        if (['chunking', 'extracting', 'embedding', 'complete', 'error'].includes(event)) {
          onProgress(data as IndexingProgress);
        }
      });
    }
  }

  return response.json();
}

export async function deleteCollection(id: number): Promise<void> {
  const response = await authFetch(`/collections/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error('Failed to delete collection');
}

// ============ Conversations ============

export async function getConversations(): Promise<Conversation[]> {
  const response = await authFetch('/conversations');
  if (!response.ok) throw new Error('Failed to fetch conversations');
  return response.json();
}

export async function createConversation(collectionId: number, title?: string): Promise<Conversation> {
  const response = await authFetch('/conversations', {
    method: 'POST',
    body: JSON.stringify({ collection_id: collectionId, title }),
  });
  if (!response.ok) throw new Error('Failed to create conversation');
  return response.json();
}

export async function getConversation(id: string): Promise<Conversation & { messages?: Message[] }> {
  const response = await authFetch(`/conversations/${id}`);
  if (!response.ok) throw new Error('Failed to fetch conversation');
  return response.json();
}

export async function updateConversation(id: string, title: string): Promise<Conversation> {
  const response = await authFetch(`/conversations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error('Failed to update conversation');
  return response.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const response = await authFetch(`/conversations/${id}`, { method: 'DELETE' });
  if (!response.ok) throw new Error('Failed to delete conversation');
}

// ============ Chat (Streaming) ============

export interface ChatRequest {
  message: string;
  conversation_id?: string;
  collection_id: number;
}

export interface ChatEvent {
  type: 'chat' | 'info' | 'done' | 'error';
  content?: string;
  message_id?: string;
  sources?: Source[];
  tokens_used?: number;
  error?: string;
}

export async function* streamChat(
  request: ChatRequest,
  signal?: AbortSignal
): AsyncGenerator<ChatEvent> {
  const response = await authFetch('/chat', {
    method: 'POST',
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    throw new Error('Failed to start chat');
  }

  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();

    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event:')) {
        continue; // Skip event type line, data follows
      }

      if (line.startsWith('data:')) {
        const data = line.slice(5).trim();
        if (data) {
          try {
            const parsed = JSON.parse(data);
            yield parsed as ChatEvent;
          } catch {
            // Ignore parse errors
          }
        }
      }
    }
  }
}

export async function abortChat(): Promise<void> {
  await authFetch('/chat/abort', { method: 'DELETE' });
}

export async function regenerateMessage(messageId: string): Promise<void> {
  const response = await authFetch(`/chat/${messageId}/regenerate`, { method: 'POST' });
  if (!response.ok) throw new Error('Failed to regenerate');
}

export async function sendFeedback(messageId: string, rating: 'up' | 'down', comment?: string): Promise<void> {
  await authFetch(`/chat/${messageId}/feedback`, {
    method: 'POST',
    body: JSON.stringify({ rating, comment }),
  });
}

// ============ Files ============

export async function getFileContent(fileId: string): Promise<Blob> {
  const response = await authFetch(`/files/${fileId}/content`);
  if (!response.ok) throw new Error('Failed to fetch file');
  return response.blob();
}

export async function getFilePage(fileId: string, pageNum: number): Promise<Blob> {
  const response = await authFetch(`/files/${fileId}/page/${pageNum}`);
  if (!response.ok) throw new Error('Failed to fetch page');
  return response.blob();
}

// ============ SSE Helpers ============

async function processSSEStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onEvent: (event: string, data: unknown) => void
): Promise<void> {
  const decoder = new TextDecoder();
  let buffer = '';
  let currentEvent = 'message';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        const data = line.slice(5).trim();
        if (data) {
          try {
            const parsed = JSON.parse(data);
            onEvent(currentEvent, parsed);
          } catch {
            onEvent(currentEvent, data);
          }
        }
      }
    }
  }
}

// Parse SSE string (for simpler use cases)
export function parseSSE(text: string): Array<{ event: string; data: unknown }> {
  const results: Array<{ event: string; data: unknown }> = [];
  const lines = text.split('\n');
  let currentEvent = 'message';

  for (const line of lines) {
    if (line.startsWith('event:')) {
      currentEvent = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      const data = line.slice(5).trim();
      if (data) {
        try {
          results.push({ event: currentEvent, data: JSON.parse(data) });
        } catch {
          results.push({ event: currentEvent, data });
        }
      }
    }
  }

  return results;
}
