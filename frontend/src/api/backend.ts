// FastAPI backend client

export interface Collection {
  id: number;
  name: string;
  type: string;
}

export interface Source {
  file_id: string | null;
  file_name: string;
  page_number: number | null;
  page_end?: number | null;
  text_snippet: string;
  relevance_score: number;
}

export async function getCollections(): Promise<Collection[]> {
  const response = await fetch('/api/collections');
  if (!response.ok) {
    throw new Error(`Failed to fetch collections: ${response.statusText}`);
  }
  return response.json();
}

export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch('/api/health');
    return response.ok;
  } catch {
    return false;
  }
}

export interface ChatEvent {
  type: 'chat' | 'info' | 'done' | 'error';
  content?: string;
  sources?: Source[];
  error?: string;
}

export async function* streamChat(
  message: string,
  collectionId: number
): AsyncGenerator<ChatEvent> {
  const response = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, collection_id: collectionId }),
  });

  if (!response.ok) {
    throw new Error(`Chat request failed: ${response.statusText}`);
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
      if (line.startsWith('data:')) {
        const data = line.slice(5).trim();
        if (data) {
          try {
            const event = JSON.parse(data) as ChatEvent;
            yield event;
          } catch {
            // Ignore parse errors
          }
        }
      }
    }
  }
}
