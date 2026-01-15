/**
 * Native messaging host client
 */

const HOST_NAME = 'com.reverse_api.engineer'

type MessageHandler = (message: Record<string, unknown>) => void
type MessageCallback = (response: Record<string, unknown>) => void

class NativeHostClient {
  private port: chrome.runtime.Port | null = null
  private connected = false
  private messageHandlers = new Map<string, MessageHandler[]>()
  private pendingCallbacks = new Map<number, MessageCallback>()
  private callbackId = 0

  async connect(): Promise<boolean> {
    return new Promise((resolve) => {
      let resolved = false
      let timeoutId: ReturnType<typeof setTimeout> | null = null

      const resolveOnce = (value: boolean) => {
        if (!resolved) {
          resolved = true
          if (timeoutId) clearTimeout(timeoutId)
          resolve(value)
        }
      }

      try {
        this.port = chrome.runtime.connectNative(HOST_NAME)

        this.port.onMessage.addListener((message: Record<string, unknown>) => {
          this.handleMessage(message)
        })

        this.port.onDisconnect.addListener(() => {
          this.connected = false
          this.port = null
          const error = chrome.runtime.lastError
          console.log('Native host disconnected:', error?.message || 'unknown reason')

          const handlers = this.messageHandlers.get('disconnect') || []
          handlers.forEach((handler) => handler({ error: error?.message }))
          
          // If we disconnect before getting status response, resolve false
          resolveOnce(false)
        })

        this.sendMessage({ type: 'status' }, (response) => {
          if (response && response.connected) {
            this.connected = true
            resolveOnce(true)
          } else {
            resolveOnce(false)
          }
        })

        timeoutId = setTimeout(() => {
          resolveOnce(false)
        }, 3000)
      } catch (error) {
        console.error('Failed to connect to native host:', error)
        resolveOnce(false)
      }
    })
  }

  disconnect(): void {
    if (this.port) {
      this.port.disconnect()
      this.port = null
      this.connected = false
    }
  }

  sendMessage(message: Record<string, unknown>, callback?: MessageCallback): void {
    if (!this.port) {
      if (callback) {
        callback({ type: 'error', message: 'Not connected to native host' })
      }
      return
    }

    if (callback) {
      const id = this.callbackId++
      message._callbackId = id
      this.pendingCallbacks.set(id, callback)
    }

    try {
      this.port.postMessage(message)
    } catch (error) {
      console.error('Failed to send message:', error)
      if (callback) {
        callback({ type: 'error', message: (error as Error).message })
      }
    }
  }

  private handleMessage(message: Record<string, unknown>): void {
    if (message._callbackId !== undefined) {
      const callback = this.pendingCallbacks.get(message._callbackId as number)
      if (callback) {
        this.pendingCallbacks.delete(message._callbackId as number)
        callback(message)
      }
      return
    }

    const handlers = this.messageHandlers.get(message.type as string) || []
    handlers.forEach((handler) => handler(message))

    const allHandlers = this.messageHandlers.get('all') || []
    allHandlers.forEach((handler) => handler(message))
  }

  onMessage(type: string, handler: MessageHandler): void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, [])
    }
    this.messageHandlers.get(type)!.push(handler)
  }

  offMessage(type: string, handler: MessageHandler): void {
    const handlers = this.messageHandlers.get(type)
    if (handlers) {
      const index = handlers.indexOf(handler)
      if (index > -1) {
        handlers.splice(index, 1)
      }
    }
  }

  async getStatus(): Promise<Record<string, unknown>> {
    return new Promise((resolve) => {
      this.sendMessage({ type: 'status' }, resolve)
      setTimeout(() => resolve({ connected: false, error: 'Timeout' }), 5000)
    })
  }

  async chat(message: string, runId: string, model?: string): Promise<Record<string, unknown>> {
    return new Promise((resolve) => {
      this.sendMessage({ type: 'chat', message, run_id: runId, model }, resolve)
    })
  }

  isConnected(): boolean {
    return this.connected && this.port !== null
  }
}

export const nativeHost = new NativeHostClient()
export default nativeHost
