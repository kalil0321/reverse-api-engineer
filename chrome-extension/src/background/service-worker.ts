/**
 * Background service worker for Reverse API Engineer extension
 */

import { captureManager, generateRunId } from '../shared/capture'
import { nativeHost } from '../shared/native-host'
import {
  getSettings,
  saveSettings,
  getCurrentSession,
  saveCurrentSession,
  clearCapturedRequests,
  addCapturedRequest
} from '../shared/storage'

let currentRunId: string | null = null
let nativeHostConnected = false

async function initialize(): Promise<void> {
  console.log('Reverse API Engineer: Initializing...')
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })

  const session = await getCurrentSession()
  if (session) {
    currentRunId = session.runId
    console.log('Restored session:', currentRunId)
  }

  await checkNativeHost()
  captureManager.addListener(handleCaptureEvent)
  console.log('Reverse API Engineer: Ready')
}

async function checkNativeHost(): Promise<boolean> {
  try {
    nativeHostConnected = await nativeHost.connect()
    console.log('Native host connected:', nativeHostConnected)
  } catch (error) {
    console.log('Native host not available:', (error as Error).message)
    nativeHostConnected = false
  }
  return nativeHostConnected
}

function handleCaptureEvent(event: { type: string; request?: unknown }): void {
  broadcastMessage({ type: 'captureEvent', event })
  if (event.type === 'complete' || event.type === 'failed') {
    addCapturedRequest(event.request)
  }
}

function broadcastMessage(message: Record<string, unknown>): void {
  chrome.runtime.sendMessage(message).catch(() => {})
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  handleMessage(message)
    .then(sendResponse)
    .catch((error) => {
      console.error('Message handler error:', error)
      sendResponse({ error: error.message })
    })
  return true
})

async function handleMessage(message: { type: string; [key: string]: unknown }): Promise<unknown> {
  switch (message.type) {
    case 'getState':
      return getState()
    case 'startCapture':
      return startCapture(message.tabId as number | undefined)
    case 'stopCapture':
      return stopCapture()
    case 'getSettings':
      return getSettings()
    case 'saveSettings':
      await saveSettings(message.settings as { lastModel: string; captureTypes: string[] })
      return { success: true }
    case 'checkNativeHost':
      return { connected: await checkNativeHost() }
    case 'getNativeHostStatus':
      if (!nativeHostConnected) return { connected: false }
      return nativeHost.getStatus()
    case 'chat':
      return handleChat(message.message as string, message.model as string | undefined)
    default:
      throw new Error(`Unknown message type: ${message.type}`)
  }
}

async function getState(): Promise<Record<string, unknown>> {
  const session = await getCurrentSession()
  const settings = await getSettings()
  const stats = captureManager.getStats()

  return {
    capturing: captureManager.isCapturing(),
    runId: currentRunId,
    session,
    settings,
    stats,
    nativeHostConnected
  }
}

async function startCapture(tabId?: number): Promise<{ success: boolean; runId: string; tabId: number }> {
  if (captureManager.isCapturing()) {
    throw new Error('Already capturing')
  }

  if (!tabId) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab?.id) throw new Error('No active tab')
    tabId = tab.id
  }

  currentRunId = generateRunId()
  const settings = await getSettings()
  await clearCapturedRequests()

  await captureManager.start(tabId, { captureTypes: settings.captureTypes })

  await saveCurrentSession({
    runId: currentRunId,
    tabId,
    startTime: new Date().toISOString(),
    requestCount: 0
  })

  chrome.action.setBadgeText({ text: 'REC' })
  chrome.action.setBadgeBackgroundColor({ color: '#ff0000' })

  return { success: true, runId: currentRunId, tabId }
}

async function stopCapture(): Promise<{ success: boolean; runId: string | null; entryCount: number; harPath: string | null }> {
  if (!captureManager.isCapturing()) {
    throw new Error('Not capturing')
  }

  const har = await captureManager.stop()
  chrome.action.setBadgeText({ text: '' })

  const session = await getCurrentSession()
  if (session && har) {
    session.endTime = new Date().toISOString()
    session.requestCount = har.log.entries.length
    await saveCurrentSession(session)
  }

  let harPath: string | null = null
  if (nativeHostConnected && har) {
    try {
      const response = await new Promise<{ path?: string }>((resolve) => {
        nativeHost.sendMessage({ type: 'saveHar', run_id: currentRunId, har }, resolve as (r: Record<string, unknown>) => void)
      })
      harPath = response.path || null
    } catch (error) {
      console.error('Failed to save HAR via native host:', error)
    }
  }

  return {
    success: true,
    runId: currentRunId,
    entryCount: har?.log.entries.length || 0,
    harPath
  }
}

async function handleChat(message: string, model?: string): Promise<Record<string, unknown>> {
  if (!nativeHostConnected) {
    throw new Error('Native host not connected')
  }
  if (!currentRunId) {
    throw new Error('No capture session. Please capture some traffic first.')
  }

  const settings = await getSettings()
  return nativeHost.chat(message, currentRunId, model || settings.lastModel)
}

// Handle native host events
nativeHost.onMessage('agent_event', (message) => {
  broadcastMessage({ type: 'agentEvent', event: message })
})

nativeHost.onMessage('progress', (message) => {
  broadcastMessage({ type: 'generationProgress', progress: message })
})

nativeHost.onMessage('disconnect', () => {
  nativeHostConnected = false
  broadcastMessage({ type: 'nativeHostDisconnected' })
})

initialize()
