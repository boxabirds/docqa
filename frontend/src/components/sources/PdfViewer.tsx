import { useState, useEffect, useCallback } from 'react';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';
import { useChatStore } from '../../stores/chatStore';

// Set up PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

export function PdfViewer() {
  const { pdfViewerFile, closePdfViewer } = useChatStore();
  const [currentPage, setCurrentPage] = useState(pdfViewerFile?.page || 1);
  const [totalPages, setTotalPages] = useState(1);
  const [zoom, setZoom] = useState(100);
  const [error, setError] = useState<string | null>(null);

  // Update page when file changes
  useEffect(() => {
    if (pdfViewerFile?.page) {
      setCurrentPage(pdfViewerFile.page);
    }
  }, [pdfViewerFile?.page]);

  // Reset state when file changes
  useEffect(() => {
    setError(null);
  }, [pdfViewerFile?.id]);

  // Handle PDF load success
  const onDocumentLoadSuccess = useCallback(({ numPages }: { numPages: number }) => {
    setTotalPages(numPages);
    setError(null);
  }, []);

  // Handle PDF load error
  const onDocumentLoadError = useCallback((err: Error) => {
    console.error('PDF load error:', err);
    setError('Failed to load PDF');
  }, []);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closePdfViewer();
      } else if (e.key === 'ArrowLeft') {
        setCurrentPage((p) => Math.max(1, p - 1));
      } else if (e.key === 'ArrowRight') {
        setCurrentPage((p) => Math.min(totalPages, p + 1));
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [closePdfViewer, totalPages]);

  if (!pdfViewerFile) return null;

  // Construct PDF URL from file_id
  const pdfUrl = pdfViewerFile.id ? `/api/documents/${pdfViewerFile.id}/pdf` : null;

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-ink-950/50 backdrop-blur-sm z-40 animate-fade-in"
        onClick={closePdfViewer}
      />

      {/* Slide-over panel */}
      <div
        className="fixed right-0 top-0 bottom-0 w-full max-w-3xl z-50
          bg-white dark:bg-ink-900
          border-l border-ink-200 dark:border-ink-800
          shadow-2xl
          flex flex-col
          animate-slide-in-right"
        style={{
          animation: 'slideInRight 0.3s ease-out',
        }}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-ink-200/50 dark:border-ink-800/50">
          <div className="flex items-center gap-3 min-w-0">
            {/* PDF icon */}
            <div className="w-10 h-10 rounded-xl bg-rose-100 dark:bg-rose-900/30 flex items-center justify-center">
              <svg className="w-5 h-5 text-rose-600 dark:text-rose-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm-1 7V3.5L18.5 9H13z" />
              </svg>
            </div>
            <div className="min-w-0">
              <h2 className="font-display text-lg font-semibold text-ink-900 dark:text-ink-100 truncate">
                {pdfViewerFile.name}
              </h2>
              <p className="text-sm text-ink-500 dark:text-ink-400">
                {totalPages} pages
              </p>
            </div>
          </div>

          <button
            onClick={closePdfViewer}
            className="btn-icon"
            title="Close (Esc)"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Navigation bar */}
        <div className="flex items-center justify-between px-6 py-3 bg-paper-50 dark:bg-ink-800/50 border-b border-ink-200/50 dark:border-ink-700/50">
          {/* Page navigation */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
              disabled={currentPage <= 1}
              className="btn-icon disabled:opacity-30 disabled:cursor-not-allowed"
              title="Previous page"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>

            <div className="flex items-center gap-2">
              <input
                type="number"
                value={currentPage}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  if (val >= 1 && val <= totalPages) {
                    setCurrentPage(val);
                  }
                }}
                className="w-14 px-2 py-1 text-center text-sm font-mono
                  bg-white dark:bg-ink-900
                  border border-ink-200 dark:border-ink-700
                  rounded-lg
                  focus:border-accent-400 dark:focus:border-accent-500
                  outline-none"
                min={1}
                max={totalPages}
              />
              <span className="text-sm text-ink-500 dark:text-ink-400">
                of {totalPages}
              </span>
            </div>

            <button
              onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
              disabled={currentPage >= totalPages}
              className="btn-icon disabled:opacity-30 disabled:cursor-not-allowed"
              title="Next page"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
              </svg>
            </button>
          </div>

          {/* Zoom controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setZoom((z) => Math.max(50, z - 25))}
              className="btn-icon"
              title="Zoom out"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20 12H4" />
              </svg>
            </button>
            <span className="text-sm font-mono text-ink-600 dark:text-ink-300 w-12 text-center">
              {zoom}%
            </span>
            <button
              onClick={() => setZoom((z) => Math.min(200, z + 25))}
              className="btn-icon"
              title="Zoom in"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>
        </div>

        {/* PDF content area */}
        <div className="flex-1 overflow-auto p-6 bg-ink-100 dark:bg-ink-950">
          {error ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-4 text-center">
                <div className="w-16 h-16 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <svg className="w-8 h-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                  </svg>
                </div>
                <div>
                  <p className="text-lg font-semibold text-ink-900 dark:text-ink-100">{error}</p>
                  <p className="text-sm text-ink-500 dark:text-ink-400 mt-1">
                    {pdfUrl ? 'The PDF file may not be available.' : 'No PDF available for this source.'}
                  </p>
                </div>
              </div>
            </div>
          ) : !pdfUrl ? (
            <div className="flex items-center justify-center h-full">
              <div className="flex flex-col items-center gap-4 text-center">
                <div className="w-16 h-16 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center">
                  <svg className="w-8 h-8 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                </div>
                <div>
                  <p className="text-lg font-semibold text-ink-900 dark:text-ink-100">PDF Not Available</p>
                  <p className="text-sm text-ink-500 dark:text-ink-400 mt-1">
                    This collection may need to be re-indexed to enable PDF viewing.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div
              className="mx-auto flex justify-center"
              style={{
                transform: `scale(${zoom / 100})`,
                transformOrigin: 'top center',
              }}
            >
              <Document
                file={pdfUrl}
                onLoadSuccess={onDocumentLoadSuccess}
                onLoadError={onDocumentLoadError}
                loading={
                  <div className="flex items-center justify-center py-20">
                    <div className="flex flex-col items-center gap-4">
                      <div className="w-8 h-8 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
                      <p className="text-sm text-ink-500 dark:text-ink-400">Loading document...</p>
                    </div>
                  </div>
                }
                className="pdf-document"
              >
                <Page
                  pageNumber={currentPage}
                  renderTextLayer={true}
                  renderAnnotationLayer={true}
                  className="shadow-editorial-lg rounded-lg overflow-hidden"
                  loading={
                    <div className="flex items-center justify-center py-20 bg-white dark:bg-ink-800 min-h-[600px] min-w-[450px]">
                      <div className="w-6 h-6 border-2 border-accent-500 border-t-transparent rounded-full animate-spin" />
                    </div>
                  }
                />
              </Document>
            </div>
          )}
        </div>

        {/* Footer with hints */}
        <div className="px-6 py-3 border-t border-ink-200/50 dark:border-ink-800/50 bg-paper-50 dark:bg-ink-800/50">
          <div className="flex items-center justify-center gap-6 text-xs text-ink-400 dark:text-ink-500">
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 rounded bg-ink-100 dark:bg-ink-700 font-mono text-[10px]">←</kbd>
              <kbd className="px-1.5 py-0.5 rounded bg-ink-100 dark:bg-ink-700 font-mono text-[10px]">→</kbd>
              Navigate
            </span>
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 rounded bg-ink-100 dark:bg-ink-700 font-mono text-[10px]">Esc</kbd>
              Close
            </span>
          </div>
        </div>
      </div>

      <style>{`
        @keyframes slideInRight {
          from {
            transform: translateX(100%);
          }
          to {
            transform: translateX(0);
          }
        }
        .pdf-document .react-pdf__Page__canvas {
          background: white;
        }
        .pdf-document .react-pdf__Page__textContent {
          user-select: text;
        }
      `}</style>
    </>
  );
}
