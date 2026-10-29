import type { Config } from 'tailwindcss';

const config: Config = {
  darkMode: ['class'],
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}', './fixtures/**/*.{ts,tsx}', './lib/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#f8f9fa',
        ink: { DEFAULT: '#0b1e22', soft: '#12292e' },
        surface: {
          DEFAULT: '#ffffff',
          secondary: '#f1f5f9',
          hover: '#e2e8f0',
          dim: '#e2e8f0',
        },
        border: {
          hairline: '#e2e8f0',
          strong: '#cbd5e1',
        },
        brand: {
          teal: '#0e7490',
          'teal-dark': '#155e75',
          'teal-light': '#ecfeff',
        },
        data: {
          blue: '#0284c7',
        },
        status: {
          success: '#059669',
          'success-bg': '#ecfdf5',
          warning: '#d97706',
          'warning-bg': '#fffbeb',
          critical: '#dc2626',
          'critical-bg': '#fef2f2',
          neutral: '#64748b',
        },
        text: {
          primary: '#0f172a',
          secondary: '#475569',
          tertiary: '#64748b',
          muted: '#94a3b8',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'Inter', 'system-ui', 'sans-serif'],
        display: ['var(--font-geist-sans)', 'Geist', 'var(--font-inter)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'JetBrains Mono', 'Fira Code', 'monospace'],
      },
      borderRadius: {
        card: '8px',
        control: '6px',
        pill: '9999px',
      },
    },
  },
  plugins: [],
};
export default config;
