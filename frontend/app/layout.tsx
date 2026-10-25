import type { Metadata, Viewport } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import { AppProvider } from '@/lib/app-context';
import { AgentProvider } from '@/lib/agent/agent-context';
import { Toasts } from '@/components/shell/Toasts';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const mono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono', display: 'swap' });

export const metadata: Metadata = {
  title: { default: 'Manufacturing OS', template: '%s · Manufacturing OS' },
  description: 'Biomanufacturing intelligence that starts from your existing systems, shows its evidence, and routes every consequential action to a named human reviewer.',
};

export const viewport: Viewport = { themeColor: '#0e7490' };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
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
