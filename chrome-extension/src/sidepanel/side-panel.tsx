import { useState, useEffect, useRef, useCallback } from 'react'
import { Button } from '@base-ui/react/button'
import { Tooltip } from '@base-ui/react/tooltip'
import { AgentAction } from '../components/agent-action'
import { ChatInput } from '../components/chat-input'
import { SessionSelector } from '../components/session-selector'
import { ModeSelector } from '../components/mode-selector'
import { CodeDisplay } from '../components/code-display'
import type { AppState, AgentEvent, Settings, Session, AppMode } from '../shared/types'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content?: string
  events?: AgentEvent[]
}

interface ExtendedAppState extends AppState {
  sessions?: Session[]
  codegenActive?: boolean
  codegenScript?: string
}

const DEFAULT_STATE: ExtendedAppState = {
  capturing: false,
  runId: null,
  nativeHostConnected: false,
  isStreaming: false,
  stats: { total: 0 },
  current_task: null,
  activeSessionId: null,
  mode: 'capture',
  sessions: [],
  codegenActive: false,
  codegenScript: ''
}

const DEFAULT_SETTINGS: Settings = {
  lastModel: 'claude-sonnet-4-5',
  captureTypes: ['xhr', 'fetch', 'websocket'],
}

export function SidePanel() {
  const [state, setState] = useState<ExtendedAppState>(DEFAULT_STATE)
  const [settings, setSettings] = useState<Settings>(DEFAULT_SETTINGS)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [warningMessage, setWarningMessage] = useState<string | null>(null)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const currentResponseIdRef = useRef<string | null>(null)
  const warningTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  // Initialize: load state and settings
  useEffect(() => {
    const init = async () => {
      try {
        const [stateRes, settingsRes] = await Promise.all([
          chrome.runtime.sendMessage({ type: 'getState' }),
          chrome.runtime.sendMessage({ type: 'getSettings' }),
        ])
        if (stateRes) setState(prev => ({ ...prev, ...stateRes }))
        if (settingsRes) setSettings(prev => ({ ...prev, ...settingsRes }))
      } catch (err) {
        console.error('Failed to initialize:', err)
      }
    }
    init()
  }, [])

  // Cleanup warning timeout on unmount
  useEffect(() => {
    return () => {
      if (warningTimeoutRef.current) clearTimeout(warningTimeoutRef.current)
    }
  }, [])

  // Listen for messages from background
  useEffect(() => {
    const handleMessage = (message: { type: string; event?: AgentEvent | { type: string }; script?: string; session?: Session; mode?: AppMode; newCode?: string }) => {
      switch (message.type) {
        case 'captureEvent':
          // Refresh state to get updated counts
          chrome.runtime.sendMessage({ type: 'getState' }).then(res => {
            if (res) setState(prev => ({ ...prev, ...res }))
          })
          break
        case 'agentEvent':
          handleAgentEvent(message.event as AgentEvent)
          break
        case 'nativeHostDisconnected':
          setState(prev => ({ ...prev, nativeHostConnected: false }))
          break
        case 'sessionCreated':
        case 'sessionSwitched':
        case 'sessionDeleted':
        case 'sessionRenamed':
          // Refresh sessions list
          chrome.runtime.sendMessage({ type: 'getState' }).then(res => {
            if (res) setState(prev => ({ ...prev, ...res }))
          })
          break
        case 'modeChanged':
          if (message.mode) {
            setState(prev => ({ ...prev, mode: message.mode! }))
          }
          break
        case 'codegenStarted':
          setState(prev => ({ ...prev, codegenActive: true, codegenScript: message.script || '' }))
          break
        case 'codegenUpdate':
          setState(prev => ({ ...prev, codegenScript: message.script || '' }))
          break
        case 'codegenStopped':
          setState(prev => ({ ...prev, codegenActive: false, codegenScript: message.script || '' }))
          break
      }
    }

    chrome.runtime.onMessage.addListener(handleMessage)
    return () => chrome.runtime.onMessage.removeListener(handleMessage)
  }, [])

  // Scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom()
  }, [messages, scrollToBottom])

  const handleAgentEvent = useCallback((event: AgentEvent) => {
    // Extract current task from TodoWrite tool events
    if (event.event_type === 'tool_use' && event.tool_name === 'TodoWrite' && event.tool_input) {
      const todos = (event.tool_input as { todos?: Array<{ status: string; content: string; activeForm?: string }> }).todos
      if (todos && Array.isArray(todos)) {
        const inProgressTodo = todos.find(todo => todo.status === 'in_progress')
        if (inProgressTodo) {
          const currentTask = inProgressTodo.activeForm || inProgressTodo.content
          setState(prev => ({ ...prev, current_task: currentTask }))
        } else {
          // Check if all todos are completed
          const allCompleted = todos.every(todo => todo.status === 'completed')
          if (allCompleted) {
            setState(prev => ({ ...prev, current_task: null }))
          }
        }
      }
    }

    setMessages(prev => {
      // Find or create the current assistant message
      let currentId = currentResponseIdRef.current

      if (!currentId) {
        currentId = `assistant-${Date.now()}`
        currentResponseIdRef.current = currentId
        return [...prev, { id: currentId, role: 'assistant', events: [event] }]
      }

      return prev.map(msg => {
        if (msg.id === currentId) {
          return { ...msg, events: [...(msg.events || []), event] }
        }
        return msg
      })
    })

    // Handle done/error events
    if (event.event_type === 'done' || event.event_type === 'error') {
      currentResponseIdRef.current = null
      setState(prev => ({ ...prev, isStreaming: false, current_task: null }))
    }
  }, [])

  const toggleCapture = async () => {
    try {
      if (state.capturing) {
        await chrome.runtime.sendMessage({ type: 'stopCapture' })
      } else {
        await chrome.runtime.sendMessage({ type: 'startCapture' })
      }
      const res = await chrome.runtime.sendMessage({ type: 'getState' })
      if (res) setState(prev => ({ ...prev, ...res }))
    } catch (err) {
      console.error('Capture error:', err)
    }
  }

  const checkNativeHost = async () => {
    try {
      const res = await chrome.runtime.sendMessage({ type: 'checkNativeHost' })
      setState(prev => ({ ...prev, nativeHostConnected: res.connected }))
    } catch (err) {
      console.error('Host check error:', err)
    }
  }

  const showWarning = (msg: string) => {
    if (warningTimeoutRef.current) clearTimeout(warningTimeoutRef.current)
    setWarningMessage(msg)
    warningTimeoutRef.current = setTimeout(() => {
      setWarningMessage(null)
    }, 3000)
  }

  const sendMessage = async (message: string) => {
    if (!message.trim()) return

    if (state.isStreaming) {
      showWarning('Agent is already working...')
      return
    }

    if (!state.nativeHostConnected) {
      showWarning('Native host not connected')
      return
    }

    if (state.stats.total === 0) {
      showWarning('Capture traffic first')
      return
    }

    // Clear current task when starting new query
    setState(prev => ({ ...prev, current_task: null }))

    // Add user message
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: message,
    }
    setMessages(prev => [...prev, userMsg])
    setInputValue('')
    setWarningMessage(null)
    setState(prev => ({ ...prev, isStreaming: true }))

    try {
      await chrome.runtime.sendMessage({
        type: 'chat',
        message,
        model: settings.lastModel,
      })
    } catch (err) {
      console.error('Chat error:', err)
      setState(prev => ({ ...prev, isStreaming: false }))
      showWarning('Failed to send message')
    }
  }

  // Session management handlers
  const handleCreateSession = async (name?: string) => {
    try {
      await chrome.runtime.sendMessage({ type: 'createSession', name })
      const res = await chrome.runtime.sendMessage({ type: 'getState' })
      if (res) setState(prev => ({ ...prev, ...res }))
      // Clear messages for new session
      setMessages([])
    } catch (err) {
      console.error('Create session error:', err)
      showWarning('Failed to create session')
    }
  }

  const handleSwitchSession = async (sessionId: string) => {
    try {
      await chrome.runtime.sendMessage({ type: 'switchSession', sessionId })
      const res = await chrome.runtime.sendMessage({ type: 'getState' })
      if (res) setState(prev => ({ ...prev, ...res }))
      // Load messages for the switched session (TODO: implement message persistence per session)
      setMessages([])
    } catch (err) {
      console.error('Switch session error:', err)
      showWarning((err as Error).message || 'Failed to switch session')
    }
  }

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await chrome.runtime.sendMessage({ type: 'deleteSession', sessionId })
      const res = await chrome.runtime.sendMessage({ type: 'getState' })
      if (res) setState(prev => ({ ...prev, ...res }))
    } catch (err) {
      console.error('Delete session error:', err)
      showWarning((err as Error).message || 'Failed to delete session')
    }
  }

  const handleRenameSession = async (sessionId: string, name: string) => {
    try {
      await chrome.runtime.sendMessage({ type: 'renameSession', sessionId, name })
      const res = await chrome.runtime.sendMessage({ type: 'getState' })
      if (res) setState(prev => ({ ...prev, ...res }))
    } catch (err) {
      console.error('Rename session error:', err)
      showWarning('Failed to rename session')
    }
  }

  // Mode management handlers
  const handleModeChange = async (mode: AppMode) => {
    try {
      await chrome.runtime.sendMessage({ type: 'setMode', mode })
      setState(prev => ({ ...prev, mode }))
    } catch (err) {
      console.error('Mode change error:', err)
    }
  }

  // Codegen handlers
  const toggleCodegen = async () => {
    try {
      if (state.codegenActive) {
        await chrome.runtime.sendMessage({ type: 'stopCodegen' })
      } else {
        await chrome.runtime.sendMessage({ type: 'startCodegen' })
      }
      const res = await chrome.runtime.sendMessage({ type: 'getState' })
      if (res) setState(prev => ({ ...prev, ...res }))
    } catch (err) {
      console.error('Codegen error:', err)
      showWarning((err as Error).message || 'Codegen error')
    }
  }

  return (
    <div className="flex flex-col h-screen bg-[#0a0a0a] text-text-primary selection:bg-primary/30">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-3 border-b border-border/50 bg-[#0a0a0a]/95 backdrop-blur-md sticky top-0 z-10">
        <div className="flex items-center gap-3 overflow-hidden flex-1 min-w-0">
          <div className="w-2 h-2 rounded-full bg-primary animate-pulse flex-shrink-0" />
          <h1 className="text-xs font-semibold tracking-wide text-white font-sans truncate">reverse-api-engineer</h1>
          {state.current_task && (
            <div className="flex items-center gap-2 ml-4 px-3 py-1 bg-primary/10 border border-primary/20 text-[10px] text-primary/90 font-medium truncate max-w-md">
              <span className="opacity-60">Current:</span>
              <span className="truncate">{state.current_task}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Mode Toggle */}
          <ModeSelector
            mode={state.mode}
            onModeChange={handleModeChange}
            disabled={state.capturing || state.codegenActive}
          />
        </div>
      </header>

      {/* Sub-header with session selector and action button */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-border/30 bg-[#0a0a0a]/90">
        <SessionSelector
          sessions={state.sessions || []}
          activeSessionId={state.activeSessionId}
          isCapturing={state.capturing}
          onCreateSession={handleCreateSession}
          onSwitchSession={handleSwitchSession}
          onDeleteSession={handleDeleteSession}
          onRenameSession={handleRenameSession}
        />

        {/* Action Button based on mode */}
        {state.mode === 'capture' ? (
          <Tooltip.Root>
            <Tooltip.Trigger
              render={
                <Button
                  onClick={toggleCapture}
                  className={`px-3 py-1.5 rounded text-[11px] font-bold uppercase tracking-widest transition-all ${state.capturing
                    ? 'text-primary bg-primary/10 hover:bg-primary/20'
                    : 'text-white/60 hover:text-white hover:bg-white/10'
                  }`}
                >
                  {state.capturing ? 'Stop Capture' : 'Start Capture'}
                </Button>
              }
            />
            <Tooltip.Portal>
              <Tooltip.Positioner sideOffset={4}>
                <Tooltip.Popup className="bg-background-secondary text-white text-[10px] px-2 py-1 rounded shadow-lg border border-border z-[100] font-mono">
                  {state.capturing ? 'Stop recording' : 'Start recording'}
                  {state.stats.total > 0 && ` (${state.stats.total} requests)`}
                </Tooltip.Popup>
              </Tooltip.Positioner>
            </Tooltip.Portal>
          </Tooltip.Root>
        ) : (
          <Button
            onClick={toggleCodegen}
            className={`px-3 py-1.5 rounded text-[11px] font-bold uppercase tracking-widest transition-all ${state.codegenActive
              ? 'text-green-400 bg-green-400/10 hover:bg-green-400/20'
              : 'text-white/60 hover:text-white hover:bg-white/10'
            }`}
          >
            {state.codegenActive ? 'Stop Recording' : 'Start Recording'}
          </Button>
        )}
      </div>

      {/* Native host warning */}
      {!state.nativeHostConnected && state.mode === 'capture' && (
        <div className="mx-4 mt-4 p-3 border border-primary/50 bg-primary/5 rounded">
          <div className="flex items-start gap-3">
            <WarningIcon />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold text-primary uppercase tracking-tighter">Connection Error</p>
              <p className="text-[10px] text-text-secondary mt-1 leading-relaxed">
                Native host not found. Execute:
                <code className="block mt-1 bg-black p-1.5 rounded text-primary border border-primary/20">reverse-api-engineer install-host</code>
              </p>
              <Button
                onClick={checkNativeHost}
                className="mt-2 text-[10px] text-white hover:text-primary transition-colors font-bold underline font-sans"
              >
                {'>'} Retry connection
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Traffic Count indicator (when capturing) */}
      {state.mode === 'capture' && state.stats.total > 0 && (
        <div className="px-4 pt-4 pb-0 flex justify-end">
          <div className="text-[9px] font-bold text-text-secondary uppercase tracking-widest border border-border/50 px-2 py-0.5 rounded-full bg-white/5">
            Traffic captured: <span className="text-white">{state.stats.total}</span>
          </div>
        </div>
      )}

      {/* Main content area - conditional based on mode */}
      {state.mode === 'codegen' ? (
        /* Codegen Mode - Show code display */
        <div className="flex-1 overflow-hidden p-4">
          <CodeDisplay
            code={state.codegenScript || ''}
            language="python"
            title="Playwright Script"
            isLive={state.codegenActive}
          />
        </div>
      ) : (
        /* Capture Mode - Show chat area */
        <>
          <div className="flex-1 overflow-y-auto px-6 pb-4 pt-6 custom-scrollbar">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-full">
                <div className="w-24 h-24 text-white/10">
                  <svg viewBox="0 0 400 400" className="w-full h-full" fill="none" stroke="currentColor" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M 170 110 Q 150 110 140 120 Q 130 130 130 150 L 130 185 Q 130 195 120 195 L 110 195 L 110 205 L 120 205 Q 130 205 130 215 L 130 250 Q 130 270 140 280 Q 150 290 170 290" />
                    <path d="M 230 110 Q 250 110 260 120 Q 270 130 270 150 L 270 185 Q 270 195 280 195 L 290 195 L 290 205 L 280 205 Q 270 205 270 215 L 270 250 Q 270 270 260 280 Q 250 290 230 290" />
                    <circle cx="185" cy="200" r="5" fill="currentColor" stroke="none" />
                    <circle cx="200" cy="200" r="5" fill="currentColor" stroke="none" />
                    <circle cx="215" cy="200" r="5" fill="currentColor" stroke="none" />
                  </svg>
                </div>
              </div>
            ) : (
              <div className="space-y-8 max-w-full">
                {messages.map((msg, msgIdx) => (
                  <div key={msg.id} className="animate-in fade-in duration-500 w-full">
                    {msg.role === 'user' ? (
                      <>
                        {msgIdx > 0 && (
                          <div className="border-t border-primary/30 my-6"></div>
                        )}
                        <div className="flex items-start gap-3 w-full">
                          <span className="text-primary font-bold mt-0.5 select-none flex-shrink-0">{'>'}</span>
                          <div className="flex-1 text-sm text-white font-normal break-words leading-relaxed min-w-0">
                            {msg.content}
                          </div>
                        </div>
                      </>
                    ) : (
                      <div className="space-y-4 pl-6 w-full">
                        {msg.events?.map((event, idx) => {
                          const previousEvent = idx > 0 ? msg.events?.[idx - 1] : undefined
                          return <AgentAction key={`${msg.id}-${idx}`} event={event} previousEvent={previousEvent} />
                        })}
                      </div>
                    )}
                  </div>
                ))}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Chat input */}
          <div className="relative border-t border-border/30 bg-[#0a0a0a]">
            {warningMessage && (
              <div className="absolute bottom-full left-0 right-0 px-4 py-2 bg-primary/20 backdrop-blur-sm border-t border-primary/30 animate-in slide-in-from-bottom-2 duration-200">
                <div className="flex items-center gap-2">
                  <div className="w-1 h-1 bg-primary rounded-full" />
                  <span className="text-[10px] font-medium text-primary uppercase tracking-wider">{warningMessage}</span>
                </div>
              </div>
            )}
            <ChatInput
              value={inputValue}
              onChange={setInputValue}
              onSend={sendMessage}
              isStreaming={state.isStreaming}
              placeholder={
                !state.nativeHostConnected
                  ? 'Native host disconnected'
                  : state.stats.total === 0
                    ? 'Capture traffic to begin'
                    : 'Build an API client...'
              }
            />
          </div>
        </>
      )}
    </div>
  )
}

function WarningIcon(): JSX.Element {
  return (
    <div className="text-primary flex-shrink-0">
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    </div>
  )
}
