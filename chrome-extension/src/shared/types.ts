export interface AppState {
  capturing: boolean
  runId: string | null
  nativeHostConnected: boolean
  isStreaming: boolean
  stats: {
    total: number
  }
  current_task?: string | null
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

export interface CaptureEvent {
  type: 'complete' | 'failed' | 'started'
  request?: unknown
}
