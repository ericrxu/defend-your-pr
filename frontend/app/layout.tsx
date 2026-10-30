import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = { title: 'OwnIt — Understand the code you ship', description: 'AI understands your code. But do you? Analyze, test, and learn with your actual repository.' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
