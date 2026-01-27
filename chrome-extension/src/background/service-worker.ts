/**
 * Background service worker for Reverse API Engineer extension
 */

import { captureManager, generateRunId } from '../shared/capture'
import { nativeHost } from '../shared/native-host'
import {
  getSettings,
  saveSettings,
  getCurrentSession,
  clearCapturedRequests,
  addCapturedRequest,
  getAllSessions,
  getSession,
  saveSession,
  deleteSession as deleteSessionFromStorage,
  getActiveSessionId,
  setActiveSessionId,
  getAppMode,
  setAppMode
} from '../shared/storage'
import type { Session, AppMode } from '../shared/types'

let currentRunId: string | null = null
let activeSessionId: string | null = null
let nativeHostConnected = false
let currentMode: AppMode = 'capture'

// Codegen state
let codegenActive = false
let codegenScript = ''
let codegenTabId: number | null = null

async function initialize(): Promise<void> {
  console.log('Reverse API Engineer: Initializing...')
  chrome.sidePanel.setPanelBehavior({ openPanelOnActionClick: true })

  // Restore active session
  activeSessionId = await getActiveSessionId()
  if (activeSessionId) {
    const session = await getSession(activeSessionId)
    if (session) {
      currentRunId = session.runId
      console.log('Restored session:', currentRunId)
    }
  }

  // Restore mode
  currentMode = await getAppMode()

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
    addCapturedRequest(event.request, activeSessionId || undefined)
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
    // Session management
    case 'getSessions':
      return getAllSessions()
    case 'createSession':
      return createSession(message.name as string | undefined)
    case 'switchSession':
      return switchSession(message.sessionId as string)
    case 'deleteSession':
      return deleteSession(message.sessionId as string)
    case 'renameSession':
      return renameSession(message.sessionId as string, message.name as string)
    // Mode management
    case 'setMode':
      return setMode(message.mode as AppMode)
    case 'startCodegen':
      return startCodegen()
    case 'stopCodegen':
      return stopCodegen()
    // Codegen state for content script
    case 'getCodegenState':
      return { codegenActive, codegenTabId }
    default:
      throw new Error(`Unknown message type: ${message.type}`)
  }
}

async function getState(): Promise<Record<string, unknown>> {
  const session = await getCurrentSession()
  const sessions = await getAllSessions()
  const settings = await getSettings()
  const stats = captureManager.getStats()

  return {
    capturing: captureManager.isCapturing(),
    runId: currentRunId,
    session,
    sessions,
    settings,
    stats,
    nativeHostConnected,
    activeSessionId,
    mode: currentMode,
    codegenActive,
    codegenScript
  }
}

// Session management functions
async function createSession(name?: string): Promise<{ success: boolean; session: Session }> {
  const runId = generateRunId()
  const sessionId = `session_${Date.now()}`
  const sessionName = name || `Session ${new Date().toLocaleString()}`

  const newSession: Session = {
    id: sessionId,
    runId,
    name: sessionName,
    tabId: 0,
    startTime: new Date().toISOString(),
    requestCount: 0,
    isActive: true,
    messages: []
  }

  await saveSession(newSession)

  // Don't switch if currently capturing - just create the session
  if (!captureManager.isCapturing()) {
    await setActiveSessionId(sessionId)
    activeSessionId = sessionId
    currentRunId = runId
  }

  broadcastMessage({ type: 'sessionCreated', session: newSession })

  return { success: true, session: newSession }
}

async function switchSession(sessionId: string): Promise<{ success: boolean; session: Session | null }> {
  // Don't allow switching if capturing on current session
  if (captureManager.isCapturing()) {
    throw new Error('Cannot switch sessions while capturing. Stop capture first.')
  }

  const session = await getSession(sessionId)
  if (!session) {
    throw new Error('Session not found')
  }

  await setActiveSessionId(sessionId)
  activeSessionId = sessionId
  currentRunId = session.runId

  broadcastMessage({ type: 'sessionSwitched', session })

  return { success: true, session }
}

async function deleteSession(sessionId: string): Promise<{ success: boolean }> {
  // Don't allow deleting active session while capturing
  if (sessionId === activeSessionId && captureManager.isCapturing()) {
    throw new Error('Cannot delete active session while capturing.')
  }

  await deleteSessionFromStorage(sessionId)

  // If we deleted the active session, clear the active state
  if (sessionId === activeSessionId) {
    await setActiveSessionId(null)
    activeSessionId = null
    currentRunId = null
  }

  broadcastMessage({ type: 'sessionDeleted', sessionId })

  return { success: true }
}

async function renameSession(sessionId: string, name: string): Promise<{ success: boolean; session: Session | null }> {
  const session = await getSession(sessionId)
  if (!session) {
    throw new Error('Session not found')
  }

  session.name = name
  await saveSession(session)

  broadcastMessage({ type: 'sessionRenamed', session })

  return { success: true, session }
}

// Mode management
async function setMode(mode: AppMode): Promise<{ success: boolean; mode: AppMode }> {
  currentMode = mode
  await setAppMode(mode)
  broadcastMessage({ type: 'modeChanged', mode })
  return { success: true, mode }
}

// Codegen functions
async function startCodegen(): Promise<{ success: boolean }> {
  if (codegenActive) {
    throw new Error('Codegen already active')
  }

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
  if (!tab?.id) throw new Error('No active tab')
  codegenTabId = tab.id

  codegenActive = true
  codegenScript = `from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.goto("${tab.url || 'about:blank'}")

`

  // Send message to content script to start recording
  try {
    await chrome.tabs.sendMessage(codegenTabId, { type: 'startCodegenRecording' })
  } catch (error) {
    console.error('Failed to start content script recording:', error)
  }

  broadcastMessage({ type: 'codegenStarted', script: codegenScript })

  return { success: true }
}

async function stopCodegen(): Promise<{ success: boolean; script: string }> {
  if (!codegenActive) {
    throw new Error('Codegen not active')
  }

  // Close the script
  codegenScript += `        browser.close()

if __name__ == "__main__":
    run()
`

  // Send message to content script to stop recording
  if (codegenTabId) {
    try {
      await chrome.tabs.sendMessage(codegenTabId, { type: 'stopCodegenRecording' })
    } catch (error) {
      console.error('Failed to stop content script recording:', error)
    }
  }

  codegenActive = false
  const finalScript = codegenScript

  // Save to active session if exists
  if (activeSessionId) {
    const session = await getSession(activeSessionId)
    if (session) {
      session.codegenScript = finalScript
      await saveSession(session)
    }
  }

  broadcastMessage({ type: 'codegenStopped', script: finalScript })

  codegenTabId = null

  return { success: true, script: finalScript }
}

// Listen for codegen events from content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'codegenAction' && codegenActive && sender.tab?.id === codegenTabId) {
    const { action, selector, value, url } = message
    let code = ''

    switch (action) {
      case 'click':
        code = `        page.click("${selector}")\n`
        break
      case 'fill':
        code = `        page.fill("${selector}", "${value}")\n`
        break
      case 'navigate':
        code = `        page.goto("${url}")\n`
        break
      case 'select':
        code = `        page.select_option("${selector}", "${value}")\n`
        break
    }

    if (code) {
      codegenScript += code
      broadcastMessage({ type: 'codegenUpdate', script: codegenScript, newCode: code })
    }

    sendResponse({ success: true })
    return true
  }
  return false
})

async function startCapture(tabId?: number): Promise<{ success: boolean; runId: string; tabId: number }> {
  if (captureManager.isCapturing()) {
    throw new Error('Already capturing')
  }

  if (!tabId) {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab?.id) throw new Error('No active tab')
    tabId = tab.id
  }

  // Create a new session if none exists
  if (!activeSessionId) {
    const { session } = await createSession()
    activeSessionId = session.id
    currentRunId = session.runId
  }

  currentRunId = generateRunId()
  const settings = await getSettings()
  await clearCapturedRequests(activeSessionId || undefined)

  await captureManager.start(tabId, { captureTypes: settings.captureTypes })

  // Update the active session
  const session = await getSession(activeSessionId)
  if (session) {
    session.runId = currentRunId
    session.tabId = tabId
    session.startTime = new Date().toISOString()
    session.requestCount = 0
    session.isActive = true
    await saveSession(session)
  }

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
    session.isActive = false
    await saveSession(session)
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
