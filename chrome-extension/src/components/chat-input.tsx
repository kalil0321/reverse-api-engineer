import { Button } from '@base-ui/react/button'
import { useRef, useEffect } from 'react'

interface ChatInputProps {
  value: string
  onChange: (value: string) => void
  onSend: (message: string) => void
  isStreaming: boolean
  placeholder: string
}

export function ChatInput({ value, onChange, onSend, isStreaming, placeholder }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = `${textareaRef.current.scrollHeight}px`
    }
  }, [value])

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (value.trim()) {
        onSend(value.trim())
      }
    }
  }

  const handleSend = () => {
    if (value.trim()) {
      onSend(value.trim())
    }
  }

  return (
    <div className="p-4">
      <div className="flex items-start gap-3 w-full">
        <span className="text-primary font-bold mt-1 select-none flex-shrink-0">{'>'}</span>
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyPress}
          placeholder={placeholder}
          rows={1}
          className="flex-1 bg-transparent border-none text-sm text-white placeholder:text-text-secondary/50 resize-none focus:outline-none focus:ring-0 p-1 min-h-[28px] max-h-[200px] leading-relaxed w-full"
        />
        {value.trim() && (
          <Button
            onClick={handleSend}
            className="text-primary hover:text-white transition-colors p-1.5 flex-shrink-0"
            title="Send message"
          >
            <SendIcon />
          </Button>
        )}
      </div>
      {isStreaming && (
        <div className="mt-3 ml-6 flex items-center gap-2">
          <div className="w-1.5 h-1.5 bg-primary rounded-full animate-pulse" />
          <span className="text-[11px] text-text-secondary/80 tracking-wide">Processing...</span>
        </div>
      )}
    </div>
  )
}

function SendIcon() {
  return (
    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
    </svg>
  )
}
