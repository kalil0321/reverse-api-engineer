/**
 * Storage management for the extension
 */

import type { Settings, Session, ChatMessage, AppMode } from './types'

const DEFAULT_SETTINGS: Settings = {
  captureTypes: ['xhr', 'fetch', 'websocket'],
  lastModel: 'claude-sonnet-4-5'
}

export async function getSettings(): Promise<Settings> {
  const result = await chrome.storage.local.get('settings')
  return { ...DEFAULT_SETTINGS, ...result.settings }
}

export async function saveSettings(settings: Partial<Settings>): Promise<void> {
  const current = await getSettings()
  await chrome.storage.local.set({
    settings: { ...current, ...settings }
  })
}

// Multi-session storage functions

export async function getAllSessions(): Promise<Session[]> {
  const result = await chrome.storage.local.get('sessions')
  return result.sessions || []
}

export async function saveAllSessions(sessions: Session[]): Promise<void> {
  await chrome.storage.local.set({ sessions })
}

export async function getSession(sessionId: string): Promise<Session | null> {
  const sessions = await getAllSessions()
  return sessions.find(s => s.id === sessionId) || null
}

export async function saveSession(session: Session): Promise<void> {
  const sessions = await getAllSessions()
  const index = sessions.findIndex(s => s.id === session.id)
  if (index >= 0) {
    sessions[index] = session
  } else {
    sessions.push(session)
  }
  await saveAllSessions(sessions)
}

export async function deleteSession(sessionId: string): Promise<void> {
  const sessions = await getAllSessions()
  const filtered = sessions.filter(s => s.id !== sessionId)
  await saveAllSessions(filtered)
  // Also clean up captured requests for this session
  await chrome.storage.local.remove(`capturedRequests_${sessionId}`)
}

export async function getActiveSessionId(): Promise<string | null> {
  const result = await chrome.storage.local.get('activeSessionId')
  return result.activeSessionId || null
}

export async function setActiveSessionId(sessionId: string | null): Promise<void> {
  if (sessionId) {
    await chrome.storage.local.set({ activeSessionId: sessionId })
  } else {
    await chrome.storage.local.remove('activeSessionId')
  }
}

export async function getActiveSession(): Promise<Session | null> {
  const activeId = await getActiveSessionId()
  if (!activeId) return null
  return getSession(activeId)
}

export async function updateSessionMessages(sessionId: string, messages: ChatMessage[]): Promise<void> {
  const session = await getSession(sessionId)
  if (session) {
    session.messages = messages
    await saveSession(session)
  }
}

export async function updateSessionCodegenScript(sessionId: string, script: string): Promise<void> {
  const session = await getSession(sessionId)
  if (session) {
    session.codegenScript = script
    await saveSession(session)
  }
}

// Mode storage
export async function getAppMode(): Promise<AppMode> {
  const result = await chrome.storage.local.get('appMode')
  return result.appMode || 'capture'
}

export async function setAppMode(mode: AppMode): Promise<void> {
  await chrome.storage.local.set({ appMode: mode })
}

// Legacy functions for backward compatibility
export async function getCurrentSession(): Promise<Session | null> {
  return getActiveSession()
}

export async function saveCurrentSession(session: Partial<Session> & { runId: string; tabId: number; startTime: string; requestCount: number }): Promise<void> {
  const existingSession = await getActiveSession()
  if (existingSession) {
    const updatedSession: Session = {
      ...existingSession,
      ...session,
    }
    await saveSession(updatedSession)
  }
}

export async function clearCurrentSession(): Promise<void> {
  await setActiveSessionId(null)
}

export async function getCapturedRequests(sessionId?: string): Promise<unknown[]> {
  const key = sessionId ? `capturedRequests_${sessionId}` : 'capturedRequests'
  const result = await chrome.storage.local.get(key)
  return result[key] || []
}

export async function addCapturedRequest(request: unknown, sessionId?: string): Promise<void> {
  const key = sessionId ? `capturedRequests_${sessionId}` : 'capturedRequests'
  const requests = await getCapturedRequests(sessionId)
  requests.push(request)
  await chrome.storage.local.set({ [key]: requests })
}

export async function clearCapturedRequests(sessionId?: string): Promise<void> {
  const key = sessionId ? `capturedRequests_${sessionId}` : 'capturedRequests'
  await chrome.storage.local.set({ [key]: [] })
}

export async function getChatHistory(runId: string): Promise<ChatMessage[]> {
  const result = await chrome.storage.local.get(`chat_${runId}`)
  return result[`chat_${runId}`] || []
}

export async function addChatMessage(runId: string, message: ChatMessage): Promise<void> {
  const history = await getChatHistory(runId)
  history.push(message)
  await chrome.storage.local.set({ [`chat_${runId}`]: history })
}
