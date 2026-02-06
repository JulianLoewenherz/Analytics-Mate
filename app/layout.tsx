import React from "react"
import type { Metadata, Viewport } from 'next'
import { Inter, JetBrains_Mono } from 'next/font/google'

import './globals.css'

const _inter = Inter({ subsets: ['latin'], variable: '--font-inter' })
const _jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains-mono',
})

export const metadata: Metadata = {
  title: 'Analytics Mate',
  description: 'Cursor-style workspace for video analytics',
}

export const viewport: Viewport = {
  themeColor: '#111214',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <body className="font-sans antialiased overflow-hidden">
        {children}
      </body>
    </html>
  )
}
