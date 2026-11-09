import type { Metadata, Viewport } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import { GeistSans } from 'geist/font/sans';
import { AppProvider } from '@/lib/app-context';
import { AgentProvider } from '@/lib/agent/agent-context';
import { Toasts } from '@/components/shell/Toasts';
import './globals.css';
import './entry.css';
import './workspace.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const mono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono', display: 'swap' });

export const metadata: Metadata = {
  icons: { icon: { url: "/brand/favicon-transparent.svg", type: "image/svg+xml" }, apple: "/brand/symbol-transparent.png" },
  title: { default: 'Sievance · Pharmaceutical manufacturing intelligence', template: '%s · Sievance' },
  description: 'Connect manufacturing evidence, investigate process questions and compare next steps. AI for pharmaceutical teams and CDMOs, with traceable sources and human review.',
};

export const viewport: Viewport = { themeColor: '#0e7490' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable} ${GeistSans.variable}`}>
      <body>
        <AppProvider>
          <AgentProvider>
            {children}
            <Toasts />
          </AgentProvider>
        </AppProvider>
      </body>
    </html>
  );
}
