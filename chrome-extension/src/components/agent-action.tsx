import type { AgentEvent } from '../shared/types'
import { Terminal } from './terminal'
import { Plan } from './plan'
import { MarkdownRenderer } from './markdown-renderer'

interface AgentActionProps {
  event: AgentEvent
  previousEvent?: AgentEvent
}

export function AgentAction({ event, previousEvent }: AgentActionProps) {
  switch (event.event_type) {
    case 'thinking':
      return <MarkdownRenderer content={event.content || ''} className="py-1" />
    case 'tool_use':
      if (event.tool_name === 'TodoWrite') {
        return <TodoWriteAction toolInput={event.tool_input} />
      }
      // For Bash, don't show tool_use separately - it will be shown in tool_result
      if (event.tool_name === 'Bash') {
        return null
      }
      return <ToolUseAction toolName={event.tool_name || ''} toolInput={event.tool_input} />
    case 'tool_result':
      // For Bash, combine with previous tool_use to show Terminal
      if (event.tool_name === 'Bash' && previousEvent?.event_type === 'tool_use' && previousEvent.tool_name === 'Bash') {
        const command = previousEvent.tool_input?.command as string || ''
        return (
          <Terminal
            command={command}
            stdout={event.output}
            exitCode={event.is_error ? 1 : 0}
            className="my-2"
          />
        )
      }
      // Don't show tool result output for other tools
      return null
    case 'text':
      return <MarkdownRenderer content={event.content || ''} className="text-white/95" />
    case 'done':
      return <DoneAction cost={event.cost} durationMs={event.duration_ms} isError={event.is_error} />
    case 'error':
      return <ErrorAction message={event.message || 'Unknown error'} />
    default:
      return null
  }
}

function ToolUseAction({ toolName, toolInput }: { toolName: string; toolInput?: Record<string, unknown> }) {
  // Minimal display for tools
  const getToolDisplay = () => {
    switch (toolName) {
      case 'Read':
        return toolInput?.file_path as string || 'file'
      case 'Write':
        return toolInput?.file_path as string || 'file'
      case 'Edit':
        return toolInput?.file_path as string || 'file'
      default:
        if (toolInput && Object.keys(toolInput).length > 0) {
          const firstKey = Object.keys(toolInput)[0]
          const firstValue = String(toolInput[firstKey] || '').slice(0, 30)
          return firstValue || toolName.toLowerCase()
        }
        return toolName.toLowerCase()
    }
  }
  
  return (
    <div className="text-[11px] text-text-secondary/70">
      <span className="text-primary/80">→</span> <span className="font-medium">{toolName}</span>
      <span className="text-text-secondary/50 ml-2">{getToolDisplay()}</span>
    </div>
  )
}

function DoneAction({ cost, durationMs, isError }: { cost?: number; durationMs?: number; isError?: boolean }) {
  const statusText = isError ? 'Execution failed' : 'Process completed'
  const details: string[] = []
  if (cost) details.push(`Cost: $${cost.toFixed(4)}`)
  if (durationMs) details.push(`Time: ${(durationMs / 1000).toFixed(1)}s`)
  
  return (
    <div className={`py-3 border-y-2 border-border/30 my-6 ${isError ? 'text-primary' : 'text-green-500/90'}`}>
      <div className="text-[12px] font-semibold tracking-wide">{statusText}</div>
      {details.length > 0 && (
        <div className="text-[11px] text-text-secondary/80 mt-1.5 tracking-wide">
          {details.join(' • ')}
        </div>
      )}
    </div>
  )
}

function ErrorAction({ message }: { message: string }) {
  return (
    <div className="bg-primary/10 border-l-2 border-primary/50 p-4 space-y-2">
      <div className="text-[12px] font-semibold text-primary tracking-wide uppercase">Critical Error</div>
      <div className="text-sm text-primary/90">{message}</div>
    </div>
  )
}

function TodoWriteAction({ toolInput }: { toolInput?: Record<string, unknown> }) {
  const todos = (toolInput?.todos as Array<{ content: string; status: string; activeForm?: string }> | undefined) || []
  
  if (todos.length === 0) return null

  // Convert to Plan component format
  const planTodos = todos.map((todo, idx) => ({
    id: String(idx),
    label: todo.activeForm && todo.status === 'in_progress' ? todo.activeForm : todo.content,
    status: todo.status as 'pending' | 'in_progress' | 'completed' | 'cancelled',
  }))

  return (
    <Plan
      todos={planTodos}
      className="my-2"
    />
  )
}
