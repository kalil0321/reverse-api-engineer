/**
 * Content script for recording user interactions for Playwright codegen
 */

let isRecording = false

// Generate a robust CSS selector for an element
function getSelector(element: Element): string {
  // Try data-testid first
  if (element.hasAttribute('data-testid')) {
    return `[data-testid="${element.getAttribute('data-testid')}"]`
  }

  // Try id
  if (element.id) {
    return `#${CSS.escape(element.id)}`
  }

  // Try unique class combination
  if (element.classList.length > 0) {
    const classes = Array.from(element.classList)
      .filter(c => !c.match(/^(active|hover|focus|selected|open|closed|hidden|visible)/i))
      .slice(0, 3)
    if (classes.length > 0) {
      const selector = classes.map(c => `.${CSS.escape(c)}`).join('')
      const matches = document.querySelectorAll(selector)
      if (matches.length === 1) {
        return selector
      }
    }
  }

  // Try name attribute for form elements
  if (element.hasAttribute('name')) {
    const name = element.getAttribute('name')
    const tag = element.tagName.toLowerCase()
    const selector = `${tag}[name="${name}"]`
    const matches = document.querySelectorAll(selector)
    if (matches.length === 1) {
      return selector
    }
  }

  // Try placeholder for inputs
  if (element.hasAttribute('placeholder')) {
    const placeholder = element.getAttribute('placeholder')
    return `[placeholder="${placeholder}"]`
  }

  // Try aria-label
  if (element.hasAttribute('aria-label')) {
    return `[aria-label="${element.getAttribute('aria-label')}"]`
  }

  // Try text content for buttons and links
  if (element.tagName === 'BUTTON' || element.tagName === 'A') {
    const text = element.textContent?.trim().slice(0, 30)
    if (text) {
      return `text="${text}"`
    }
  }

  // Fall back to tag + nth-child
  const parent = element.parentElement
  if (parent) {
    const siblings = Array.from(parent.children)
    const index = siblings.indexOf(element) + 1
    const tag = element.tagName.toLowerCase()
    const parentSelector = getSelector(parent)
    if (parentSelector !== 'body') {
      return `${parentSelector} > ${tag}:nth-child(${index})`
    }
  }

  // Last resort: just the tag
  return element.tagName.toLowerCase()
}

// Escape string for Python
function escapeString(str: string): string {
  return str
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '\\"')
    .replace(/\n/g, '\\n')
    .replace(/\r/g, '\\r')
    .replace(/\t/g, '\\t')
}

// Send action to background script
function sendAction(action: string, data: Record<string, unknown>) {
  chrome.runtime.sendMessage({
    type: 'codegenAction',
    action,
    ...data
  }).catch(() => {
    // Extension might not be listening
  })
}

// Track the last input element to capture its final value
let lastInputElement: HTMLInputElement | HTMLTextAreaElement | null = null
let inputTimeout: ReturnType<typeof setTimeout> | null = null

function handleClick(event: MouseEvent) {
  if (!isRecording) return

  const target = event.target as Element
  if (!target) return

  // Skip clicks on the extension's own elements
  if (target.closest('[data-codegen-ignore]')) return

  // Commit any pending input
  commitPendingInput()

  const selector = getSelector(target)

  // Check if it's a select element
  if (target.tagName === 'SELECT') {
    // Will be handled by change event
    return
  }

  sendAction('click', { selector })
}

function handleInput(event: Event) {
  if (!isRecording) return

  const target = event.target as HTMLInputElement | HTMLTextAreaElement
  if (!target) return

  // Track the input element
  lastInputElement = target

  // Debounce the input to get the final value
  if (inputTimeout) {
    clearTimeout(inputTimeout)
  }

  inputTimeout = setTimeout(() => {
    commitPendingInput()
  }, 500)
}

function commitPendingInput() {
  if (!lastInputElement) return

  const selector = getSelector(lastInputElement)
  const value = escapeString(lastInputElement.value)

  if (value) {
    sendAction('fill', { selector, value })
  }

  lastInputElement = null
  if (inputTimeout) {
    clearTimeout(inputTimeout)
    inputTimeout = null
  }
}

function handleChange(event: Event) {
  if (!isRecording) return

  const target = event.target as HTMLSelectElement
  if (!target || target.tagName !== 'SELECT') return

  const selector = getSelector(target)
  const value = escapeString(target.value)

  sendAction('select', { selector, value })
}

function handleKeyDown(event: KeyboardEvent) {
  if (!isRecording) return

  // Commit input on Enter
  if (event.key === 'Enter') {
    commitPendingInput()
  }
}

// Handle navigation
let lastUrl = window.location.href
function checkNavigation() {
  if (window.location.href !== lastUrl) {
    lastUrl = window.location.href
    if (isRecording) {
      sendAction('navigate', { url: lastUrl })
    }
  }
}

// Start recording
function startRecording() {
  if (isRecording) return

  isRecording = true
  lastUrl = window.location.href

  document.addEventListener('click', handleClick, true)
  document.addEventListener('input', handleInput, true)
  document.addEventListener('change', handleChange, true)
  document.addEventListener('keydown', handleKeyDown, true)

  // Check for navigation periodically
  setInterval(checkNavigation, 100)

  console.log('[Codegen] Recording started')
}

// Stop recording
function stopRecording() {
  if (!isRecording) return

  commitPendingInput()
  isRecording = false

  document.removeEventListener('click', handleClick, true)
  document.removeEventListener('input', handleInput, true)
  document.removeEventListener('change', handleChange, true)
  document.removeEventListener('keydown', handleKeyDown, true)

  console.log('[Codegen] Recording stopped')
}

// Listen for messages from background script
chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message.type === 'startCodegenRecording') {
    startRecording()
    sendResponse({ success: true })
  } else if (message.type === 'stopCodegenRecording') {
    stopRecording()
    sendResponse({ success: true })
  }
  return true
})

// Check if we should be recording on load
chrome.runtime.sendMessage({ type: 'getCodegenState' }).then(response => {
  if (response?.codegenActive) {
    startRecording()
  }
}).catch(() => {
  // Extension not ready yet
})
