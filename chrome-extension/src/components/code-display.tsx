import { useRef, useEffect, useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { Button } from '@base-ui/react/button'

interface CodeDisplayProps {
  code: string
  language?: string
  title?: string
  isLive?: boolean
  onCopy?: () => void
}

export function CodeDisplay({
  code,
  language = 'python',
  title = 'Generated Script',
  isLive = false,
  onCopy
}: CodeDisplayProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [copied, setCopied] = useState(false)
  const [autoScroll, setAutoScroll] = useState(true)

  // Auto-scroll to bottom when new code is added
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [code, autoScroll])

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      onCopy?.()
    } catch (err) {
      console.error('Failed to copy:', err)
    }
  }

  const handleScroll = () => {
    if (containerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = containerRef.current
      // If user scrolls up, disable auto-scroll
      // If they scroll to bottom, re-enable it
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50
      setAutoScroll(isAtBottom)
    }
  }

  const lineCount = code.split('\n').length

  return (
    <div className="flex flex-col h-full bg-[#0d0d0d] rounded border border-white/10 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-white/5 border-b border-white/10">
        <div className="flex items-center gap-2">
          <CodeIcon />
          <span className="text-[11px] font-bold text-white/80 uppercase tracking-wider">{title}</span>
          {isLive && (
            <span className="flex items-center gap-1.5 px-2 py-0.5 bg-green-500/20 text-green-400 text-[9px] font-bold uppercase tracking-wider rounded">
              <span className="w-1.5 h-1.5 bg-green-400 rounded-full animate-pulse" />
              Live
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-white/40">{lineCount} lines</span>
          <Button
            onClick={handleCopy}
            className="flex items-center gap-1 px-2 py-1 text-[10px] text-white/60 hover:text-white hover:bg-white/10 rounded transition-colors"
          >
            {copied ? <CheckIcon /> : <CopyIcon />}
            {copied ? 'Copied!' : 'Copy'}
          </Button>
        </div>
      </div>

      {/* Code content */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-auto custom-scrollbar"
      >
        {code ? (
          <SyntaxHighlighter
            style={vscDarkPlus}
            language={language}
            PreTag="div"
            showLineNumbers
            lineNumberStyle={{
              minWidth: '3em',
              paddingRight: '1em',
              color: 'rgba(255, 255, 255, 0.2)',
              textAlign: 'right',
              userSelect: 'none'
            }}
            customStyle={{
              margin: 0,
              padding: '1rem',
              background: 'transparent',
              fontSize: '12px',
              lineHeight: '1.6'
            }}
          >
            {code}
          </SyntaxHighlighter>
        ) : (
          <div className="flex flex-col items-center justify-center h-full text-white/30 p-8">
            <EmptyCodeIcon />
            <p className="mt-4 text-[11px] text-center">
              {isLive ? 'Waiting for actions...' : 'No code generated yet'}
            </p>
            {isLive && (
              <p className="mt-1 text-[10px] text-white/20">
                Interact with the page to record actions
              </p>
            )}
          </div>
        )}
      </div>

      {/* Auto-scroll indicator */}
      {!autoScroll && code && (
        <div className="px-3 py-1.5 bg-primary/10 border-t border-primary/20">
          <button
            onClick={() => {
              setAutoScroll(true)
              if (containerRef.current) {
                containerRef.current.scrollTop = containerRef.current.scrollHeight
              }
            }}
            className="text-[10px] text-primary hover:text-primary/80 transition-colors"
          >
            Resume auto-scroll
          </button>
        </div>
      )}
    </div>
  )
}

function CodeIcon() {
  return (
    <svg className="w-4 h-4 text-primary" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
    </svg>
  )
}

function CopyIcon() {
  return (
    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg className="w-3 h-3 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
    </svg>
  )
}

function EmptyCodeIcon() {
  return (
    <svg className="w-12 h-12 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <polyline strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} points="14 2 14 8 20 8" />
      <line strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} x1="16" y1="13" x2="8" y2="13" />
      <line strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} x1="16" y1="17" x2="8" y2="17" />
      <polyline strokeLinecap="round" strokeLinejoin="round" strokeWidth={1} points="10 9 9 9 8 9" />
    </svg>
  )
}
