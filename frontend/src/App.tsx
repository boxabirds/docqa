import { useEffect } from 'react';
import { useChatStore } from './stores/chatStore';
import { Sidebar } from './components/sidebar/Sidebar';
import { ChatWindow } from './components/chat/ChatWindow';
import { PdfViewer } from './components/sources/PdfViewer';

function App() {
  const { theme, isSidebarOpen, isPdfViewerOpen } = useChatStore();

  // Apply theme to document
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else if (theme === 'light') {
      root.classList.remove('dark');
    } else {
      // System preference
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.classList.toggle('dark', prefersDark);
    }
  }, [theme]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd/Ctrl + B: Toggle sidebar
      if ((e.metaKey || e.ctrlKey) && e.key === 'b') {
        e.preventDefault();
        useChatStore.getState().toggleSidebar();
      }
      // Cmd/Ctrl + Shift + D: Toggle theme
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'd') {
        e.preventDefault();
        const currentTheme = useChatStore.getState().theme;
        useChatStore.getState().setTheme(currentTheme === 'dark' ? 'light' : 'dark');
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  return (
    <div className="flex h-screen overflow-hidden bg-paper-100 dark:bg-ink-950">
      {/* Noise overlay for depth */}
      <div className="noise-overlay" />

      {/* Sidebar */}
      <div
        className={`
          ${isSidebarOpen ? 'w-72' : 'w-0'}
          transition-all duration-300 ease-in-out
          overflow-hidden flex-shrink-0
        `}
      >
        <Sidebar />
      </div>

      {/* Main chat area */}
      <main className="flex-1 flex flex-col min-w-0 relative">
        <ChatWindow />
      </main>

      {/* PDF Viewer slide-over */}
      {isPdfViewerOpen && <PdfViewer />}
    </div>
  );
}

export default App;
