import type { Metadata, Viewport } from 'next';
import { Inter, JetBrains_Mono } from 'next/font/google';
import { GeistSans } from 'geist/font/sans';
import { AppProvider } from '@/lib/app-context';
import { AgentProvider } from '@/lib/agent/agent-context';
import { Toasts } from '@/components/shell/Toasts';
import './globals.css';

const inter = Inter({ subsets: ['latin'], variable: '--font-inter', display: 'swap' });
const mono = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono', display: 'swap' });

export const metadata: Metadata = {
  title: { default: 'Sievance · Verified CMO data', template: '%s · Sievance' },
  description: 'Turn the files your CMOs send into one verified dataset. Every value links to its source; nothing is accepted or dropped without a record.',
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
