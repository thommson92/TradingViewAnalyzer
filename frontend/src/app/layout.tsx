import type { Metadata } from 'next';
import type { ReactNode } from 'react';

import { Datenzugang } from '@/components/Datenzugang';

import './globals.css';

export const metadata: Metadata = {
  title: 'AI Trading Analyst',
  description: 'Persoenliches Analyse-Dashboard fuer Long-Swing-Trades',
};

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>): ReactNode {
  return (
    <html lang="de">
      <body>
        {/* Ausserhalb des Servers liegt statt der API ein Datenbaum; er wird
            hier geoeffnet und der Stand darueber angezeigt (ADR 0060). Im
            eigenen Netz reicht die Komponente ihre Kinder durch. */}
        <Datenzugang>{children}</Datenzugang>
      </body>
    </html>
  );
}
