export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp?: Date;  // Frontend display
  created_at?: Date | string;  // Backend response
  sources?: Source[];
  isStreaming?: boolean;
}

export interface Source {
  file_id: string | null;
  file_name: string;
  page_number: number | null;
  page_end?: number | null;
  text_snippet: string;
  relevance_score?: number;
}

export interface Conversation {
  id: string;
  title?: string | null;
  collection_id?: number | null;
  created_at?: Date | string;
  updated_at?: Date | string;
  message_count?: number;
  messages?: Message[];
}

export interface Collection {
  id: number;
  name: string;
  type: 'graphrag';  // Only GraphRAG supported
  file_count: number;
  created_at: Date;
}

export interface IndexingProgress {
  phase: 'chunking' | 'extracting' | 'embedding' | 'complete' | 'error';
  chunks_total: number;
  chunks_done: number;
  entities_found: number;
  eta_seconds: number;
  percent_complete: number;
  files: { name: string; status: 'pending' | 'processing' | 'done'; chunks?: number }[];
  error_message?: string;
}

export interface User {
  id: string;
  username: string;
}

export type Theme = 'light' | 'dark' | 'system';
