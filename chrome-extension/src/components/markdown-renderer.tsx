import React from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

interface MarkdownRendererProps {
  content: string
  className?: string
}

export function MarkdownRenderer({ content, className = '' }: MarkdownRendererProps) {
  return (
    <div className={`text-[14px] text-white/90 leading-relaxed space-y-4 prose prose-invert prose-sm max-w-none ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          code({ node, inline, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '')
            const language = match ? match[1] : ''
            return !inline && match ? (
              <div className="my-4 border-l-2 border-border/40 bg-black/50 overflow-hidden">
                {language && (
                  <div className="bg-white/5 px-4 py-2 text-[10px] font-semibold uppercase tracking-wide text-text-secondary border-b border-border/30">
                    {language}
                  </div>
                )}
                <SyntaxHighlighter
                  style={vscDarkPlus}
                  language={language}
                  PreTag="div"
                  className="!bg-transparent !p-4 !m-0"
                  customStyle={{
                    margin: 0,
                    padding: 0,
                    background: 'transparent',
                  }}
                  {...props}
                >
                  {String(children).replace(/\n$/, '')}
                </SyntaxHighlighter>
              </div>
            ) : (
              <code className="px-1.5 py-0.5 bg-primary/10 text-primary text-[13px] font-mono" {...props}>
                {children}
              </code>
            )
          },
          p({ children }: { children?: React.ReactNode }) {
            return <p className="mb-4 last:mb-0">{children}</p>
          },
          h1({ children }: { children?: React.ReactNode }) {
            return <h1 className="text-xl font-semibold mb-3 mt-6 first:mt-0">{children}</h1>
          },
          h2({ children }: { children?: React.ReactNode }) {
            return <h2 className="text-lg font-semibold mb-2 mt-5 first:mt-0">{children}</h2>
          },
          h3({ children }: { children?: React.ReactNode }) {
            return <h3 className="text-base font-semibold mb-2 mt-4 first:mt-0">{children}</h3>
          },
          ul({ children }: { children?: React.ReactNode }) {
            return <ul className="list-disc list-inside mb-4 space-y-1 ml-2">{children}</ul>
          },
          ol({ children }: { children?: React.ReactNode }) {
            return <ol className="list-decimal list-inside mb-4 space-y-1 ml-2">{children}</ol>
          },
          li({ children }: { children?: React.ReactNode }) {
            return <li className="ml-2">{children}</li>
          },
          blockquote({ children }: { children?: React.ReactNode }) {
            return <blockquote className="border-l-4 border-primary/30 pl-4 italic my-4 text-text-secondary">{children}</blockquote>
          },
          a({ href, children }: { href?: string; children?: React.ReactNode }) {
            return <a href={href} className="text-primary hover:underline" target="_blank" rel="noopener noreferrer">{children}</a>
          },
          strong({ children }: { children?: React.ReactNode }) {
            return <strong className="font-semibold text-white">{children}</strong>
          },
          em({ children }: { children?: React.ReactNode }) {
            return <em className="italic">{children}</em>
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}
