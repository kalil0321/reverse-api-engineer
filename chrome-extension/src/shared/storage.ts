/**
 * Storage management for the extension
 */

import type { Settings } from './types'

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

interface Session {
  runId: string
  tabId: number
  startTime: string
  endTime?: string
  requestCount: number
}

export async function getCurrentSession(): Promise<Session | null> {
  const result = await chrome.storage.local.get('currentSession')
  return result.currentSession || null
}

export async function saveCurrentSession(session: Session): Promise<void> {
  await chrome.storage.local.set({ currentSession: session })
}

export async function clearCurrentSession(): Promise<void> {
  await chrome.storage.local.remove('currentSession')
}

export async function getCapturedRequests(): Promise<unknown[]> {
  const result = await chrome.storage.local.get('capturedRequests')
  return result.capturedRequests || []
}

export async function addCapturedRequest(request: unknown): Promise<void> {
  const requests = await getCapturedRequests()
  requests.push(request)
  await chrome.storage.local.set({ capturedRequests: requests })
}

export async function clearCapturedRequests(): Promise<void> {
  await chrome.storage.local.set({ capturedRequests: [] })
}

interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
  timestamp: string
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
