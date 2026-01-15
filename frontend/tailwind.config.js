/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      fontFamily: {
        // Display: Playfair Display - elegant serif for headings
        display: ['Playfair Display', 'Georgia', 'serif'],
        // Body: Source Sans 3 - clean, readable sans-serif
        sans: ['Source Sans 3', 'system-ui', 'sans-serif'],
        // Mono: JetBrains Mono - developer-friendly monospace
        mono: ['JetBrains Mono', 'Consolas', 'monospace'],
      },
      colors: {
        // Dark editorial palette
        ink: {
          50: '#f7f7f5',
          100: '#e8e8e3',
          200: '#d4d4cb',
          300: '#b5b5a6',
          400: '#96967f',
          500: '#7b7b64',
          600: '#62624f',
          700: '#4d4d3f',
          800: '#3d3d32',
          900: '#2a2a22',
          950: '#1a1a14',
        },
        // Accent: warm amber/gold
        accent: {
          50: '#fffbeb',
          100: '#fef3c7',
          200: '#fde68a',
          300: '#fcd34d',
          400: '#fbbf24',
          500: '#f59e0b',
          600: '#d97706',
          700: '#b45309',
          800: '#92400e',
          900: '#78350f',
        },
        // Paper tones for light mode
        paper: {
          50: '#fdfcfb',
          100: '#f9f7f4',
          200: '#f3f0ea',
          300: '#e8e3d9',
        },
      },
      boxShadow: {
        'editorial': '0 1px 3px rgba(0,0,0,0.08), 0 4px 12px rgba(0,0,0,0.04)',
        'editorial-lg': '0 4px 6px rgba(0,0,0,0.07), 0 12px 24px rgba(0,0,0,0.06)',
        'glow': '0 0 20px rgba(251, 191, 36, 0.15)',
      },
      animation: {
        'fade-in': 'fadeIn 0.5s ease-out',
        'slide-up': 'slideUp 0.4s ease-out',
        'pulse-soft': 'pulseSoft 2s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(10px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        pulseSoft: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.6' },
        },
      },
    },
  },
  plugins: [],
}
