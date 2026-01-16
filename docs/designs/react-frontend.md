# Plan: Kotaemon Backend/Frontend Separation

## Goal
Separate Kotaemon's RAG backend from its Gradio frontend, expose it via FastAPI, and create a clean React 19.2 frontend with a ChatGPT-like interface.

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  React 19.2 UI  │────▶│   FastAPI       │────▶│  Kotaemon Core  │
│  (ChatGPT-like) │◀────│   REST + SSE    │◀────│  (Reasoning/RAG)│
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

## Phase 1: FastAPI Backend Layer

### 1.1 Core API Structure
Create `/api/` module in kotaemon-fork:

```
libs/ktem/ktem/api/
├── __init__.py
├── main.py           # FastAPI app setup
├── auth.py           # JWT authentication
├── routes/
│   ├── __init__.py
│   ├── chat.py       # Chat/reasoning endpoints
│   ├── conversations.py
│   ├── indices.py    # Index management
│   └── users.py
├── models/
│   ├── __init__.py
│   ├── requests.py   # Pydantic request models
│   └── responses.py  # Pydantic response models
└── services/
    ├── __init__.py
    ├── chat_service.py    # Wraps chat pipeline
    └── retrieval_service.py
```

### 1.2 Key Endpoints

**Authentication:**
- `POST /api/auth/login` → JWT token
- `POST /api/auth/refresh` → Refresh token
- `GET /api/auth/me` → Current user

**Chat (Streaming):**
- `POST /api/chat` → SSE stream of responses
  - Input: `{message, conversation_id, collection_id, settings}`
  - Output: Server-Sent Events with `{type: "chat"|"info"|"plot", content}`
- `POST /api/chat/{message_id}/regenerate` → Regenerate a response
- `PUT /api/chat/{message_id}` → Edit user message and get new response
- `POST /api/chat/{message_id}/feedback` → Thumbs up/down
  - Input: `{rating: "up"|"down", comment?: string}`
- `DELETE /api/chat/abort` → Abort current streaming response

**Conversations:**
- `GET /api/conversations` → List user's conversations
- `POST /api/conversations` → Create new
- `GET /api/conversations/{id}` → Get with messages
- `DELETE /api/conversations/{id}`
- `PATCH /api/conversations/{id}` → Rename

**Indices:**
- `GET /api/indices` → List available indices
- `GET /api/indices/{id}/files` → List files in index

**Collections (Dynamic Creation):**
- `POST /api/collections` → Create new collection on the fly
  - Input: `{name, type: "graphrag"|"vector", files: [multipart]}`
  - Output: `{collection_id, status: "created"}`
- `GET /api/collections` → List user's collections
- `DELETE /api/collections/{id}` → Delete collection

**File Upload & Indexing:**
- `POST /api/collections/{id}/files` → Upload file(s) for indexing
  - Input: multipart/form-data with file(s)
  - Output: SSE stream of indexing progress with ETA
- `DELETE /api/collections/{id}/files/{file_id}` → Remove file
- `GET /api/collections/{id}/status` → Get indexing status

**Source Documents:**
- `GET /api/files/{file_id}` → Get file metadata
- `GET /api/files/{file_id}/content` → Stream PDF/document content
- `GET /api/files/{file_id}/page/{page_num}` → Get specific page as image (for preview)
- Source references include: `{file_id, file_name, page_number, text_snippet, bbox?}`

**Indexing Progress Events (SSE):**
```json
{"event": "started", "data": {"total_files": 3, "total_pages": 45}}
{"event": "chunking", "data": {"file": "doc.pdf", "chunks_done": 10, "chunks_total": 50, "eta_seconds": 120}}
{"event": "extracting", "data": {"chunks_done": 30, "chunks_total": 204, "entities_found": 156, "eta_seconds": 85}}
{"event": "embedding", "data": {"entities_done": 100, "entities_total": 716, "eta_seconds": 30}}
{"event": "complete", "data": {"entities": 716, "relationships": 548, "duration_seconds": 245}}
{"event": "error", "data": {"message": "...", "file": "bad.pdf"}}
```

**Chat Response Events (SSE):**
```json
{"event": "chat", "data": {"content": "CReDO is a platform...", "message_id": "abc123"}}
{"event": "info", "data": {"sources": [
  {
    "file_id": "4c71d38b-...",
    "file_name": "PRD.pdf",
    "page_number": 15,
    "text_snippet": "Epic 4: Other partners for MVP...",
    "relevance_score": 0.92
  },
  {
    "file_id": "4c71d38b-...",
    "file_name": "PRD.pdf",
    "page_number": 2,
    "text_snippet": "CReDO+ Digital Twin MVP Master PRD...",
    "relevance_score": 0.87
  }
]}}
{"event": "done", "data": {"message_id": "abc123", "tokens_used": 1234}}
```
### 1.3 Critical Files to Modify/Reference

| Purpose | File |
|---------|------|
| Chat pipeline entry | `libs/ktem/ktem/pages/chat/__init__.py` (lines 1266-1368: `chat_fn`) |
| Reasoning pipelines | `libs/ktem/ktem/reasoning/simple.py` (`FullQAPipeline.stream`) |
| Retrieval | `libs/ktem/ktem/index/file/pipelines.py` |
| GraphRAG retrieval | `libs/ktem/ktem/index/file/graph/pipelines.py` |
| DB models | `libs/ktem/ktem/db/base_models.py` |
| Conversation control | `libs/ktem/ktem/pages/chat/control.py` |

### 1.4 Streaming Implementation

```python
# routes/chat.py
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

@router.post("/chat")
async def chat(request: ChatRequest, user: User = Depends(get_current_user)):
    async def event_generator():
        pipeline = create_pipeline(request.settings, request.index_id)
        for doc in pipeline.stream(request.message, request.conversation_id, request.history):
            yield {
                "event": doc.metadata.get("channel", "chat"),
                "data": json.dumps({"content": doc.text, "metadata": doc.metadata})
            }
    return EventSourceResponse(event_generator())
```

## Phase 2: React 19.2 Frontend

### 2.1 Project Structure

```
frontend/
├── package.json
├── vite.config.ts
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/
│   │   └── client.ts       # API client with SSE support
│   ├── components/
│   │   ├── chat/
│   │   │   ├── ChatWindow.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageItem.tsx       # Individual message with actions
│   │   │   ├── MessageActions.tsx    # Copy, regenerate, edit, feedback
│   │   │   ├── MessageInput.tsx      # Auto-resize textarea
│   │   │   ├── StopButton.tsx        # Stop generation
│   │   │   ├── TypingIndicator.tsx
│   │   │   └── CodeBlock.tsx         # Syntax highlight + copy button
│   │   ├── sources/
│   │   │   ├── SourcesPanel.tsx      # Collapsible retrieved context
│   │   │   ├── SourceItem.tsx        # Clickable source with page number
│   │   │   └── PdfViewer.tsx         # PDF viewer with page navigation
│   │   ├── sidebar/
│   │   │   ├── Sidebar.tsx
│   │   │   ├── ConversationList.tsx
│   │   │   ├── CollectionSelector.tsx
│   │   │   └── ThemeToggle.tsx       # Dark/light mode
│   │   ├── collections/
│   │   │   ├── CreateCollection.tsx
│   │   │   ├── FileUpload.tsx
│   │   │   └── IndexingProgress.tsx
│   │   └── common/
│   │       ├── ErrorBoundary.tsx
│   │       ├── RetryButton.tsx
│   │       └── LoadingSpinner.tsx
│   ├── hooks/
│   │   ├── useChat.ts        # SSE streaming hook
│   │   ├── useConversations.ts
│   │   ├── useCollections.ts
│   │   └── useIndexing.ts    # SSE indexing progress with ETA
│   ├── stores/
│   │   └── chatStore.ts    # Zustand or similar
│   └── types/
│       └── index.ts
```

### 2.2 Minimal UI Components

**ChatGPT-like layout:**
```
┌──────────┬─────────────────────────────────┐
│          │                                 │
│ Sidebar  │         Chat Window             │
│          │                                 │
│ + New    │  ┌─────────────────────────┐   │
│ - Conv 1 │  │ User: What is Credo?    │   │
│ - Conv 2 │  │                         │   │
│          │  │ Assistant: CReDO is...  │   │
│          │  │                         │   │
│          │  │ ▼ Sources (3)           │   │
│ ──────── │  │ ┌─────────────────────┐ │   │
│ Collection│  │ │ • Page 15: Epic 4...│ │   │
│ [Credo4 ▼]│  │ └─────────────────────┘ │   │
│ + New    │  └─────────────────────────┘   │
│          │                                 │
│          │  ┌─────────────────────────┐   │
│          │  │ Type your message...    │   │
└──────────┴──┴─────────────────────────┴───┘
```

**Create Collection Modal:**
```
┌─────────────────────────────────────────┐
│  Create New Collection            [X]   │
├─────────────────────────────────────────┤
│  Name: [________________________]       │
│                                         │
│  Type: (•) GraphRAG  ( ) Vector         │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │     Drop files here or click    │   │
│  │         to browse               │   │
│  │     📄 doc1.pdf (2.3 MB)        │   │
│  │     📄 doc2.pdf (1.1 MB)        │   │
│  └─────────────────────────────────┘   │
│                                         │
│              [Create & Index]           │
└─────────────────────────────────────────┘
```

**Indexing Progress (shown after Create):**
```
┌─────────────────────────────────────────┐
│  Indexing "My Collection"               │
├─────────────────────────────────────────┤
│  Phase: Extracting entities             │
│                                         │
│  ████████████░░░░░░░░  58%              │
│                                         │
│  Chunks: 119/204                        │
│  Entities found: 423                    │
│  ETA: ~1 min 25 sec                     │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │ ✓ doc1.pdf - 89 chunks          │   │
│  │ ⟳ doc2.pdf - 30/115 chunks      │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

**Message with Actions:**
```
┌─────────────────────────────────────────┐
│ 👤 User                          [Edit] │
│ What is Credo?                          │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ 🤖 Assistant                            │
│                                         │
│ CReDO (Climate Resilience Decision      │
│ Optimiser) is a platform that...        │
│                                         │
│ ```python                         [📋] │
│ def example():                          │
│     return "code with copy button"      │
│ ```                                     │
│                                         │
│ ▼ Sources (3)                           │
│ ┌─────────────────────────────────────┐ │
│ │ 📄 PRD.pdf, Page 15                 │ │
│ │    "Epic 4: Other partners for MVP" │ │
│ │                            [View →] │ │
│ ├─────────────────────────────────────┤ │
│ │ 📄 PRD.pdf, Page 2                  │ │
│ │    "CReDO+ Digital Twin MVP..."     │ │
│ │                            [View →] │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ [📋 Copy] [🔄 Regenerate] [👍] [👎]    │
└─────────────────────────────────────────┘
```

**PDF Viewer (slide-over panel):**
```
┌────────────────────────────────────────────────────┐
│  PRD.pdf                              [X] Close   │
├────────────────────────────────────────────────────┤
│  [◀ Prev] Page 15 of 22 [Next ▶]    [🔍 Zoom]    │
├────────────────────────────────────────────────────┤
│ ┌────────────────────────────────────────────────┐ │
│ │                                                │ │
│ │  Epic 4: Other partners for MVP               │ │
│ │  ═══════════════════════════════              │ │
│ │                                                │ │
│ │  This epic enables Cadent and NGT users to    │ │
│ │  browse their respective assets and look at   │ │
│ │  flood and heat failure scenarios.            │ │
│ │                                                │ │
│ │  For MVP the constraints are:                 │ │
│ │  ▶ • No cost of failure data for Cadent      │ │
│ │      nor NGT.  ← [highlighted passage]        │ │
│ │                                                │ │
│ └────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────┘
```

**Streaming with Stop Button:**
```
┌─────────────────────────────────────────┐
│ 🤖 Assistant                            │
│                                         │
│ CReDO is a comprehensive platform█      │
│                                         │
│            [■ Stop generating]          │
└─────────────────────────────────────────┘
```

### 2.3 Key Dependencies

```json
{
  "dependencies": {
    "react": "^19.2.0",
    "react-dom": "^19.2.0",
    "react-router-dom": "^7.x",
    "zustand": "^5.x",
    "react-markdown": "^9.x",
    "react-syntax-highlighter": "^15.x",
    "eventsource-parser": "^3.x",
    "@react-pdf-viewer/core": "^3.x",
    "tailwindcss": "^4.x"
  },
  "devDependencies": {
    "vite": "^6.x",
    "typescript": "^5.x",
    "@types/react": "^19.x"
  }
}
```

### 2.4 Keyboard Shortcuts & UI Behaviors

| Action | Shortcut | Behavior |
|--------|----------|----------|
| Send message | `Enter` | Submit message (when input focused) |
| New line | `Shift+Enter` | Insert newline in message |
| Stop generation | `Esc` | Abort current streaming response |
| New conversation | `Cmd/Ctrl+Shift+N` | Create new conversation |
| Search conversations | `Cmd/Ctrl+K` | Focus conversation search |
| Copy message | `Cmd/Ctrl+C` | Copy selected message (when message focused) |
| Toggle sidebar | `Cmd/Ctrl+B` | Show/hide sidebar |
| Toggle dark mode | `Cmd/Ctrl+Shift+D` | Switch theme |

**Auto-behaviors:**
- Auto-scroll to bottom on new message chunks
- Auto-resize textarea as user types (max 200px)
- Auto-focus input after sending
- Persist dark/light mode preference to localStorage
- Show typing indicator during streaming
- Debounce conversation rename (500ms)

### 2.6 SSE Streaming Hook (with abort)

```typescript
// hooks/useChat.ts
export function useChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [sources, setSources] = useState<Source[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  const sendMessage = async (content: string, conversationId: string, collectionId: number) => {
    setIsStreaming(true);
    abortControllerRef.current = new AbortController();

    try {
      const response = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ message: content, conversation_id: conversationId, collection_id: collectionId }),
        signal: abortControllerRef.current.signal
      });

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        parseSSE(decoder.decode(value), (event, data) => {
          if (event === 'chat') {
            setMessages(prev => appendToLast(prev, data.content));
          } else if (event === 'info') {
            // Sources include file_id, page_number, text_snippet
            setSources(data.sources);
          }
        });
      }
    } catch (err) {
      if (err.name === 'AbortError') {
        // User cancelled - append partial message indicator
        setMessages(prev => appendToLast(prev, ' [stopped]'));
      } else {
        throw err;
      }
    } finally {
      setIsStreaming(false);
      abortControllerRef.current = null;
    }
  };

  const stopGeneration = () => {
    abortControllerRef.current?.abort();
    fetch('/api/chat/abort', { method: 'DELETE' }); // Server-side cleanup
  };

  const regenerate = async (messageId: string) => {
    // ... similar to sendMessage but POST to /api/chat/{messageId}/regenerate
  };

  return { messages, sources, isStreaming, sendMessage, stopGeneration, regenerate };
}
```

### 2.7 Indexing Progress Hook

```typescript
// hooks/useIndexing.ts
interface IndexingProgress {
  phase: 'chunking' | 'extracting' | 'embedding' | 'complete' | 'error';
  chunksTotal: number;
  chunksDone: number;
  entitiesFound: number;
  etaSeconds: number;
  percentComplete: number;
  files: { name: string; status: 'pending' | 'processing' | 'done'; chunks?: number }[];
}

export function useIndexing() {
  const [progress, setProgress] = useState<IndexingProgress | null>(null);
  const [isIndexing, setIsIndexing] = useState(false);

  const createAndIndex = async (name: string, type: string, files: File[]) => {
    setIsIndexing(true);

    const formData = new FormData();
    formData.append('name', name);
    formData.append('type', type);
    files.forEach(f => formData.append('files', f));

    const response = await fetch('/api/collections', {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
      body: formData
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      parseSSE(decoder.decode(value), (event, data) => {
        if (event === 'extracting' || event === 'chunking' || event === 'embedding') {
          setProgress({
            phase: event,
            chunksTotal: data.chunks_total,
            chunksDone: data.chunks_done,
            entitiesFound: data.entities_found || 0,
            etaSeconds: data.eta_seconds,
            percentComplete: Math.round((data.chunks_done / data.chunks_total) * 100),
            files: data.files || []
          });
        } else if (event === 'complete') {
          setProgress({ ...progress, phase: 'complete', percentComplete: 100 });
          setIsIndexing(false);
        }
      });
    }
  };

  return { progress, isIndexing, createAndIndex };
}
```

## Phase 3: Integration

### 3.1 Docker Compose Update

```yaml
services:
  # Existing ollama service...

  kotaemon-api:
    build:
      context: ./kotaemon-fork
      dockerfile: Dockerfile.api
    ports:
      - "8000:8000"
    environment:
      - KH_DATABASE=sqlite:///app/ktem_app_data/database.db
      - JWT_SECRET=your-secret-key
    volumes:
      - kotaemon_data:/app/ktem_app_data
    depends_on:
      - ollama

  frontend:
    build:
      context: ./frontend
    ports:
      - "3001:80"
    depends_on:
      - kotaemon-api
```

### 3.2 CORS Configuration

```python
# api/main.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Implementation Order

### Phase 1: Core Backend API
- [ ] Set up FastAPI app structure in `libs/ktem/ktem/api/`
- [ ] Implement JWT auth (replace SHA256 with bcrypt)
- [ ] Create chat streaming endpoint (SSE)
- [ ] Create conversation CRUD endpoints
- [ ] Create collection CRUD endpoints (dynamic creation)
- [ ] Create file upload endpoint with SSE progress + ETA
- [ ] Add indexing progress tracking (chunks → entities → embeddings)
- [ ] Create Dockerfile.api

### Phase 2: Core Frontend
- [ ] Set up Vite + React 19.2 + Tailwind project
- [ ] Implement SSE streaming client with abort support
- [ ] Build MessageList and MessageItem components
- [ ] Build MessageInput with auto-resize and keyboard shortcuts
- [ ] Build Sidebar with conversation list
- [ ] Build CollectionSelector dropdown
- [ ] Implement dark/light mode toggle with persistence

### Phase 3: Chat Features
- [ ] Add stop generation button
- [ ] Add message actions (copy, regenerate, feedback)
- [ ] Add edit user message and resubmit
- [ ] Add CodeBlock with syntax highlighting + copy button
- [ ] Add typing indicator animation
- [ ] Add auto-scroll behavior

### Phase 4: Sources & PDF Viewing
- [ ] Build collapsible SourcesPanel
- [ ] Build SourceItem with file name + page number
- [ ] Build PDF viewer slide-over panel
- [ ] Implement page navigation in PDF viewer
- [ ] Add passage highlighting in PDF (if bbox available)
- [ ] Add `/api/files/{id}/content` and `/api/files/{id}/page/{num}` endpoints

### Phase 5: Collection Management
- [ ] Build CreateCollection modal
- [ ] Build FileUpload with drag-drop
- [ ] Build IndexingProgress with status bar and ETA
- [ ] Add retry on indexing errors

### Phase 6: Polish & Integration
- [ ] Update docker-compose with new services
- [ ] Configure CORS and networking
- [ ] Add error boundaries and retry buttons
- [ ] Mobile responsive design
- [ ] Keyboard shortcut implementation
- [ ] End-to-end testing: upload → index → chat → view source

## Verification

1. **API Testing:**
   ```bash
   # Login
   curl -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"username": "admin", "password": "admin"}'

   # Create collection with files (streams progress)
   curl -N -X POST http://localhost:8000/api/collections \
     -H "Authorization: Bearer <token>" \
     -F "name=TestCollection" \
     -F "type=graphrag" \
     -F "files=@doc1.pdf" \
     -F "files=@doc2.pdf"

   # Stream chat
   curl -N http://localhost:8000/api/chat \
     -H "Authorization: Bearer <token>" \
     -H "Content-Type: application/json" \
     -d '{"message": "What is Credo?", "conversation_id": "...", "collection_id": 4}'
   ```

2. **Frontend Testing:**
   - Open http://localhost:3001
   - Login with admin/admin
   - Click "+ New Collection"
   - Drag-drop PDF files, name it "Test"
   - Click "Create & Index" - watch progress bar with ETA
   - Once complete, select the new collection
   - Ask "What is Credo?" - should stream response
   - Ask "Is Cadent cost of heat failures in scope?" - should answer "No"

## Design Decisions

- **Deployment**: Separate Docker container for API (cleaner separation, independent scaling)
- **File Upload**: Yes, API endpoint for uploading/indexing documents
- **Sources Display**: Collapsible panel showing retrieved context (like ChatGPT)
- **Dynamic Collections**: Users can create new collections on the fly from the UI
- **Indexing Progress**: Real-time progress bar with ETA during chunk → entity extraction
- **PDF Viewing**: Slide-over panel with page navigation, jumps directly to cited page
- **Message Actions**: Copy, regenerate, edit, thumbs up/down feedback
- **Streaming Control**: Stop generation button with Esc shortcut
- **Code Rendering**: Syntax highlighting with per-block copy button
- **Theming**: Dark/light mode with localStorage persistence
- **Keyboard-first**: Full keyboard navigation (Enter, Shift+Enter, Esc, Cmd+K, etc.)
