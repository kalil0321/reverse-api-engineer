export interface Session {
  id: string
  runId: string
  name: string
  tabId: number
  startTime: string
  endTime?: string
  requestCount: number
  isActive: boolean
  messages: ChatMessage[]
  codegenScript?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content?: string
  events?: AgentEvent[]
  timestamp: string
}

export type AppMode = 'capture' | 'codegen'

export interface AppState {
  capturing: boolean
  runId: string | null
  nativeHostConnected: boolean
  isStreaming: boolean
  stats: {
    total: number
  }
  current_task?: string | null
  activeSessionId: string | null
  mode: AppMode
}

export interface AgentEvent {
  event_type: 'thinking' | 'tool_use' | 'tool_result' | 'text' | 'done' | 'error'
  content?: string
  tool_name?: string
  tool_input?: Record<string, unknown>
  is_error?: boolean
  output?: string
  message?: string
  cost?: number
  duration_ms?: number
}

export interface Settings {
  lastModel: string
  captureTypes: string[]
}

export type MessageType =
  | { type: 'getState' }
  | { type: 'startCapture'; tabId?: number }
  | { type: 'stopCapture' }
  | { type: 'checkNativeHost' }
  | { type: 'chat'; message: string; model?: string }
  | { type: 'getSettings' }
  | { type: 'saveSettings'; settings: Settings }
  | { type: 'getSessions' }
  | { type: 'createSession'; name?: string }
  | { type: 'switchSession'; sessionId: string }
  | { type: 'deleteSession'; sessionId: string }
  | { type: 'renameSession'; sessionId: string; name: string }
  | { type: 'setMode'; mode: AppMode }
  | { type: 'startCodegen' }
  | { type: 'stopCodegen' }

export interface CaptureEvent {
  type: 'complete' | 'failed' | 'started'
  request?: unknown
}
