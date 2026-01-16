import { useState } from 'react';
import { useChatStore } from '../stores/chatStore';
import type { IndexingProgress, Collection } from '../types';

export function useCollections() {
  const { collections, selectedCollectionId, setCollections, selectCollection } = useChatStore();
  const [indexingProgress, setIndexingProgress] = useState<IndexingProgress | null>(null);
  const [isIndexing, setIsIndexing] = useState(false);

  const create = async (name: string, files: File[]) => {
    setIsIndexing(true);
    setIndexingProgress(null);

    // Simulate indexing progress for demo
    const totalChunks = files.length * 50;
    for (let i = 0; i <= 100; i += 10) {
      await new Promise((r) => setTimeout(r, 200));
      setIndexingProgress({
        phase: i < 30 ? 'chunking' : i < 70 ? 'extracting' : 'embedding',
        chunks_total: totalChunks,
        chunks_done: Math.floor((i / 100) * totalChunks),
        entities_found: Math.floor(i * 5),
        eta_seconds: Math.max(0, 10 - i / 10),
        percent_complete: i,
        files: files.map((f) => ({
          name: f.name,
          status: i > 50 ? 'done' : 'processing',
          chunks: Math.floor((i / 100) * 50),
        })),
      });
    }

    // Create the collection
    const newCollection: Collection = {
      id: Math.max(0, ...collections.map((c) => c.id)) + 1,
      name,
      type: 'graphrag',
      file_count: files.length,
      created_at: new Date(),
    };

    setCollections([...collections, newCollection]);
    selectCollection(newCollection.id);
    setIsIndexing(false);

    return newCollection;
  };

  const remove = (id: number) => {
    const updated = collections.filter((c) => c.id !== id);
    setCollections(updated);

    if (selectedCollectionId === id && updated.length > 0) {
      selectCollection(updated[0].id);
    }
  };

  return {
    collections,
    selectedCollectionId,
    select: selectCollection,
    create,
    remove,
    isIndexing,
    indexingProgress,
  };
}
