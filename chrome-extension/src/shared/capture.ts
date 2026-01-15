/**
 * HAR capture logic using Chrome Debugger API
 */

export function generateRunId(): string {
  // Generate short UUID with crx prefix
  // Format: crx-xxxxxxxx (8 hex characters)
  const shortUuid = Math.random().toString(16).substring(2, 10).padEnd(8, '0')
  return `crx-${shortUuid}`
}

interface CaptureSettings {
  captureTypes: string[]
}

interface HarEntry {
  requestId: string
  startedDateTime: string
  time: number
  request: {
    method: string
    url: string
    httpVersion: string
    cookies: Array<{ name: string; value: string }>
    headers: Array<{ name: string; value: string }>
    queryString: Array<{ name: string; value: string }>
    postData?: { mimeType: string; text: string }
    headersSize: number
    bodySize: number
  }
  response: {
    status: number
    statusText: string
    httpVersion: string
    cookies: Array<{ name: string; value: string }>
    headers: Array<{ name: string; value: string }>
    content: { size: number; mimeType: string; text: string; encoding?: string }
    redirectURL: string
    headersSize: number
    bodySize: number
  } | null
  cache: Record<string, unknown>
  timings: {
    blocked?: number
    dns?: number
    connect?: number
    ssl?: number
    send: number
    wait: number
    receive: number
  }
  _resourceType: string
  _initiator?: unknown
  _error?: string
  _canceled?: boolean
  _webSocketMessages?: Array<{ type: string; time: number; opcode: number; data: string }>
}

type CaptureEventCallback = (event: CaptureEvent) => void

interface CaptureEvent {
  type: string
  tabId?: number
  har?: HarData
  request?: RequestSummary
}

interface RequestSummary {
  id: string
  method: string
  url: string
  status?: number
  statusText?: string
  type: string
  time: number
  size: number
}

interface HarData {
  log: {
    version: string
    creator: { name: string; version: string }
    browser: { name: string; version: string }
    pages: Array<{
      startedDateTime: string
      id: string
      title: string
      pageTimings: { onContentLoad: number; onLoad: number }
    }>
    entries: HarEntry[]
  }
}

class HarCaptureManager {
  private capturing = false
  private tabId: number | null = null
  private requests = new Map<string, HarEntry>()
  private entries: HarEntry[] = []
  private startTime: Date | null = null
  private listeners = new Set<CaptureEventCallback>()
  private settings: CaptureSettings = {
    captureTypes: ['xhr', 'fetch', 'websocket']
  }

  async start(tabId: number, settings: Partial<CaptureSettings> = {}): Promise<void> {
    if (this.capturing) {
      throw new Error('Already capturing')
    }

    const tab = await chrome.tabs.get(tabId)
    if (this.isRestrictedUrl(tab.url || '')) {
      throw new Error(
        `Cannot capture traffic from ${new URL(tab.url || '').protocol} pages. Please navigate to a regular website (http:// or https://).`
      )
    }

    this.tabId = tabId
    this.settings = { ...this.settings, ...settings }
    this.requests.clear()
    this.entries = []
    this.startTime = new Date()

    await chrome.debugger.attach({ tabId }, '1.3')
    await chrome.debugger.sendCommand({ tabId }, 'Network.enable', {
      maxTotalBufferSize: 100000000,
      maxResourceBufferSize: 50000000
    })

    chrome.debugger.onEvent.addListener(this.handleDebuggerEvent)
    this.capturing = true
    this.notifyListeners({ type: 'started', tabId })
  }

  async stop(): Promise<HarData | null> {
    if (!this.capturing || !this.tabId) {
      return null
    }

    try {
      await chrome.debugger.detach({ tabId: this.tabId })
    } catch (error) {
      console.warn('Error detaching debugger:', error)
    }

    chrome.debugger.onEvent.removeListener(this.handleDebuggerEvent)
    this.capturing = false
    const har = this.buildHar()
    this.notifyListeners({ type: 'stopped', har })
    return har
  }

  private handleDebuggerEvent = (
    source: chrome.debugger.Debuggee,
    method: string,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    params?: any
  ): void => {
    if (source.tabId !== this.tabId || !params) return

    switch (method) {
      case 'Network.requestWillBeSent':
        this.handleRequestWillBeSent(params)
        break
      case 'Network.responseReceived':
        this.handleResponseReceived(params)
        break
      case 'Network.loadingFinished':
        this.handleLoadingFinished(params)
        break
      case 'Network.loadingFailed':
        this.handleLoadingFailed(params)
        break
    }
  }

  private handleRequestWillBeSent(params: Record<string, unknown>): void {
    const { requestId, request, timestamp, type, initiator } = params as {
      requestId: string
      request: { method: string; url: string; headers: Record<string, string>; postData?: string }
      timestamp: number
      type: string
      initiator: unknown
    }

    if (!this.shouldCapture(type)) return

    const entry: HarEntry = {
      requestId,
      startedDateTime: new Date(timestamp * 1000).toISOString(),
      time: 0,
      request: {
        method: request.method,
        url: request.url,
        httpVersion: 'HTTP/1.1',
        cookies: this.parseCookies(request.headers.Cookie || ''),
        headers: this.formatHeaders(request.headers),
        queryString: this.parseQueryString(request.url),
        postData: request.postData
          ? { mimeType: request.headers['Content-Type'] || 'application/octet-stream', text: request.postData }
          : undefined,
        headersSize: -1,
        bodySize: request.postData ? request.postData.length : 0
      },
      response: null,
      cache: {},
      timings: { send: 0, wait: 0, receive: 0 },
      _resourceType: type,
      _initiator: initiator
    }

    this.requests.set(requestId, entry)
    this.notifyListeners({ type: 'request', request: this.summarizeRequest(entry) })
  }

  private handleResponseReceived(params: Record<string, unknown>): void {
    const { requestId, response } = params as {
      requestId: string
      response: {
        status: number
        statusText: string
        headers: Record<string, string>
        mimeType: string
        encodedDataLength: number
        timing?: {
          dnsStart: number
          dnsEnd: number
          connectStart: number
          connectEnd: number
          sslStart: number
          sslEnd: number
          sendStart: number
          sendEnd: number
          receiveHeadersEnd: number
        }
      }
    }

    const entry = this.requests.get(requestId)
    if (!entry) return

    entry.response = {
      status: response.status,
      statusText: response.statusText,
      httpVersion: 'HTTP/1.1',
      cookies: [],
      headers: this.formatHeaders(response.headers),
      content: { size: response.encodedDataLength || 0, mimeType: response.mimeType || 'application/octet-stream', text: '' },
      redirectURL: response.headers.location || '',
      headersSize: -1,
      bodySize: response.encodedDataLength || 0
    }

    if (response.timing) {
      entry.timings = {
        blocked: response.timing.dnsStart > 0 ? response.timing.dnsStart : 0,
        dns: response.timing.dnsEnd - response.timing.dnsStart,
        connect: response.timing.connectEnd - response.timing.connectStart,
        ssl: response.timing.sslEnd - response.timing.sslStart,
        send: response.timing.sendEnd - response.timing.sendStart,
        wait: response.timing.receiveHeadersEnd - response.timing.sendEnd,
        receive: 0
      }
    }

    this.notifyListeners({ type: 'response', request: this.summarizeRequest(entry) })
  }

  private async handleLoadingFinished(params: Record<string, unknown>): Promise<void> {
    const { requestId, timestamp } = params as { requestId: string; timestamp: number }
    const entry = this.requests.get(requestId)
    if (!entry) return

    const startTime = new Date(entry.startedDateTime).getTime()
    entry.time = timestamp * 1000 - startTime
    entry.timings.receive = entry.time - entry.timings.wait - entry.timings.send

    try {
      const response = await chrome.debugger.sendCommand({ tabId: this.tabId! }, 'Network.getResponseBody', { requestId })
      if (entry.response && response) {
        const body = response as { body: string; base64Encoded: boolean }
        entry.response.content.text = body.body
        entry.response.content.encoding = body.base64Encoded ? 'base64' : undefined
      }
    } catch {
      // Body might not be available
    }

    this.entries.push(entry)
    this.requests.delete(requestId)
    this.notifyListeners({ type: 'complete', request: this.summarizeRequest(entry) })
  }

  private handleLoadingFailed(params: Record<string, unknown>): void {
    const { requestId, errorText, canceled } = params as { requestId: string; errorText: string; canceled: boolean }
    const entry = this.requests.get(requestId)
    if (!entry) return

    entry._error = errorText
    entry._canceled = canceled

    if (!entry.response) {
      entry.response = {
        status: 0,
        statusText: errorText,
        httpVersion: 'HTTP/1.1',
        cookies: [],
        headers: [],
        content: { size: 0, mimeType: 'text/plain', text: '' },
        redirectURL: '',
        headersSize: -1,
        bodySize: 0
      }
    }

    this.entries.push(entry)
    this.requests.delete(requestId)
    this.notifyListeners({ type: 'failed', request: this.summarizeRequest(entry) })
  }

  private shouldCapture(type: string): boolean {
    const typeMap: Record<string, string> = {
      XHR: 'xhr',
      Fetch: 'fetch',
      WebSocket: 'websocket',
      Document: 'document'
    }
    const mappedType = typeMap[type] || 'other'
    if (mappedType === 'xhr' || mappedType === 'fetch') {
      return this.settings.captureTypes.includes('xhr') || this.settings.captureTypes.includes('fetch')
    }
    return this.settings.captureTypes.includes(mappedType)
  }

  private formatHeaders(headers: Record<string, string>): Array<{ name: string; value: string }> {
    if (!headers) return []
    return Object.entries(headers).map(([name, value]) => ({ name, value }))
  }

  private parseCookies(cookieHeader: string): Array<{ name: string; value: string }> {
    if (!cookieHeader) return []
    return cookieHeader
      .split(';')
      .map((c) => {
        const [name, ...rest] = c.trim().split('=')
        return { name, value: rest.join('=') }
      })
      .filter((c) => c.name)
  }

  private parseQueryString(url: string): Array<{ name: string; value: string }> {
    try {
      const urlObj = new URL(url)
      return Array.from(urlObj.searchParams.entries()).map(([name, value]) => ({ name, value }))
    } catch {
      return []
    }
  }

  private buildHar(): HarData {
    this.requests.forEach((entry) => {
      if (entry._resourceType === 'WebSocket') {
        this.entries.push(entry)
      }
    })

    return {
      log: {
        version: '1.2',
        creator: { name: 'Reverse API Engineer', version: '0.1.0' },
        browser: { name: 'Chrome', version: navigator.userAgent.match(/Chrome\/([0-9.]+)/)?.[1] || 'unknown' },
        pages: [
          {
            startedDateTime: this.startTime?.toISOString() || new Date().toISOString(),
            id: 'page_1',
            title: 'Captured Traffic',
            pageTimings: { onContentLoad: -1, onLoad: -1 }
          }
        ],
        entries: this.entries.map((entry) => ({ ...entry, pageref: 'page_1' } as HarEntry))
      }
    }
  }

  private summarizeRequest(entry: HarEntry): RequestSummary {
    return {
      id: entry.requestId,
      method: entry.request.method,
      url: entry.request.url,
      status: entry.response?.status,
      statusText: entry.response?.statusText,
      type: entry._resourceType,
      time: entry.time,
      size: entry.response?.content?.size || 0
    }
  }

  addListener(callback: CaptureEventCallback): void {
    this.listeners.add(callback)
  }

  removeListener(callback: CaptureEventCallback): void {
    this.listeners.delete(callback)
  }

  private notifyListeners(event: CaptureEvent): void {
    this.listeners.forEach((callback) => {
      try {
        callback(event)
      } catch (error) {
        console.error('Listener error:', error)
      }
    })
  }

  private isRestrictedUrl(url: string): boolean {
    if (!url) return true
    const restrictedProtocols = ['chrome:', 'chrome-extension:', 'edge:', 'about:', 'data:', 'file:', 'view-source:']
    try {
      const urlObj = new URL(url)
      return restrictedProtocols.includes(urlObj.protocol)
    } catch {
      return true
    }
  }

  isCapturing(): boolean {
    return this.capturing
  }

  getStats(): { total: number; xhr: number; fetch: number; websocket: number; other: number } {
    const allEntries = [...this.entries, ...this.requests.values()]
    const stats = { total: allEntries.length, xhr: 0, fetch: 0, websocket: 0, other: 0 }
    allEntries.forEach((entry) => {
      const type = entry._resourceType?.toLowerCase()
      if (type === 'xhr') stats.xhr++
      else if (type === 'fetch') stats.fetch++
      else if (type === 'websocket') stats.websocket++
      else stats.other++
    })
    return stats
  }
}

export const captureManager = new HarCaptureManager()
export default captureManager
