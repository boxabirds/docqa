-- DocQA Database Schema
-- PostgreSQL + pgvector for GraphRAG data

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================================
-- Collections (document sets)
-- ============================================================
CREATE TABLE IF NOT EXISTS collections (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Documents (source PDFs)
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(64) PRIMARY KEY,  -- GraphRAG uses string IDs
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    title VARCHAR(500),
    source VARCHAR(1000),  -- Original file path
    original_filename VARCHAR(500),  -- Original PDF filename
    pdf_path VARCHAR(1000),  -- Path to stored PDF for viewing
    raw_content TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_collection ON documents(collection_id);

-- ============================================================
-- Text Units (chunks with embeddings)
-- ============================================================
CREATE TABLE IF NOT EXISTS text_units (
    id VARCHAR(64) PRIMARY KEY,  -- GraphRAG uses string IDs
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    document_ids TEXT[],  -- Array of document IDs
    text TEXT NOT NULL,
    n_tokens INTEGER,
    page_start INTEGER,  -- First page this chunk appears on
    page_end INTEGER,  -- Last page this chunk appears on
    source_file VARCHAR(500),  -- Original source filename
    embedding vector(1024),  -- BGE-M3 embeddings
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_text_units_collection ON text_units(collection_id);
CREATE INDEX IF NOT EXISTS idx_text_units_embedding ON text_units USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- Entities (graph nodes)
-- ============================================================
CREATE TABLE IF NOT EXISTS entities (
    id VARCHAR(64) PRIMARY KEY,  -- GraphRAG uses string IDs
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    name VARCHAR(500) NOT NULL,
    type VARCHAR(100),
    description TEXT,
    text_unit_ids TEXT[],  -- Array of text unit IDs where entity appears
    embedding vector(1024),  -- Entity description embedding
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_entities_collection ON entities(collection_id);
CREATE INDEX IF NOT EXISTS idx_entities_embedding ON entities USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities USING gin(name gin_trgm_ops);

-- ============================================================
-- Nodes (entity metadata for communities)
-- ============================================================
CREATE TABLE IF NOT EXISTS nodes (
    id VARCHAR(64) PRIMARY KEY,  -- Same as entity ID
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    community INTEGER,  -- Community cluster ID
    level INTEGER DEFAULT 0,
    degree INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nodes_collection ON nodes(collection_id);
CREATE INDEX IF NOT EXISTS idx_nodes_community ON nodes(collection_id, community);

-- ============================================================
-- Relationships (graph edges)
-- ============================================================
CREATE TABLE IF NOT EXISTS relationships (
    id VARCHAR(64) PRIMARY KEY,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    source VARCHAR(500) NOT NULL,  -- Source entity name
    target VARCHAR(500) NOT NULL,  -- Target entity name
    description TEXT,
    weight REAL DEFAULT 1.0,
    text_unit_ids TEXT[],  -- Array of text unit IDs where relationship appears
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_relationships_collection ON relationships(collection_id);
CREATE INDEX IF NOT EXISTS idx_relationships_source ON relationships(source);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target);

-- ============================================================
-- Communities (entity clusters)
-- ============================================================
CREATE TABLE IF NOT EXISTS communities (
    id VARCHAR(64) PRIMARY KEY,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    community INTEGER NOT NULL,  -- Community number
    level INTEGER DEFAULT 0,
    title VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_communities_collection ON communities(collection_id);

-- ============================================================
-- Community Reports (LLM-generated summaries)
-- ============================================================
CREATE TABLE IF NOT EXISTS community_reports (
    id VARCHAR(64) PRIMARY KEY,
    collection_id INTEGER NOT NULL REFERENCES collections(id) ON DELETE CASCADE,
    community INTEGER NOT NULL,
    level INTEGER DEFAULT 0,
    title VARCHAR(500),
    summary TEXT,
    full_content TEXT,
    rank REAL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_community_reports_collection ON community_reports(collection_id);
CREATE INDEX IF NOT EXISTS idx_community_reports_rank ON community_reports(collection_id, rank DESC);

-- ============================================================
-- Helper function to update timestamps
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER collections_updated_at
    BEFORE UPDATE ON collections
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Migrations for existing databases (safe to run multiple times)
-- ============================================================

-- Add page tracking columns to text_units
DO $$ BEGIN
    ALTER TABLE text_units ADD COLUMN page_start INTEGER;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE text_units ADD COLUMN page_end INTEGER;
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE text_units ADD COLUMN source_file VARCHAR(500);
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- Add PDF storage columns to documents
DO $$ BEGIN
    ALTER TABLE documents ADD COLUMN original_filename VARCHAR(500);
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

DO $$ BEGIN
    ALTER TABLE documents ADD COLUMN pdf_path VARCHAR(1000);
EXCEPTION WHEN duplicate_column THEN NULL;
END $$;

-- ============================================================
-- Conversations (chat sessions)
-- ============================================================
CREATE TABLE IF NOT EXISTS conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    collection_id INTEGER REFERENCES collections(id) ON DELETE CASCADE,
    user_id VARCHAR(64) DEFAULT 'anonymous',  -- Future: auth user
    title VARCHAR(255),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON conversations(user_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_collection ON conversations(collection_id);

CREATE OR REPLACE TRIGGER conversations_updated_at
    BEFORE UPDATE ON conversations
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- ============================================================
-- Messages (chat history)
-- ============================================================
CREATE TABLE IF NOT EXISTS messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,  -- 'user' | 'assistant'
    content TEXT NOT NULL,
    sources JSONB,  -- Stored retrieval sources for assistant messages
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);
