import { useState, useRef, useEffect } from 'react'
import { Button } from '@base-ui/react/button'
import type { Session } from '../shared/types'

interface SessionSelectorProps {
  sessions: Session[]
  activeSessionId: string | null
  isCapturing: boolean
  onCreateSession: (name?: string) => void
  onSwitchSession: (sessionId: string) => void
  onDeleteSession: (sessionId: string) => void
  onRenameSession: (sessionId: string, name: string) => void
}

export function SessionSelector({
  sessions,
  activeSessionId,
  isCapturing,
  onCreateSession,
  onSwitchSession,
  onDeleteSession,
  onRenameSession
}: SessionSelectorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [newSessionName, setNewSessionName] = useState('')
  const [showNewInput, setShowNewInput] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const activeSession = sessions.find(s => s.id === activeSessionId)

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
        setEditingId(null)
        setShowNewInput(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // Focus input when editing
  useEffect(() => {
    if ((editingId || showNewInput) && inputRef.current) {
      inputRef.current.focus()
    }
  }, [editingId, showNewInput])

  const handleCreateSession = () => {
    if (showNewInput && newSessionName.trim()) {
      onCreateSession(newSessionName.trim())
      setNewSessionName('')
      setShowNewInput(false)
    } else {
      setShowNewInput(true)
    }
  }

  const handleNewSessionKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && newSessionName.trim()) {
      onCreateSession(newSessionName.trim())
      setNewSessionName('')
      setShowNewInput(false)
    } else if (e.key === 'Escape') {
      setShowNewInput(false)
      setNewSessionName('')
    }
  }

  const handleRenameKeyDown = (e: React.KeyboardEvent, sessionId: string) => {
    if (e.key === 'Enter' && editName.trim()) {
      onRenameSession(sessionId, editName.trim())
      setEditingId(null)
    } else if (e.key === 'Escape') {
      setEditingId(null)
    }
  }

  const startEditing = (session: Session) => {
    setEditingId(session.id)
    setEditName(session.name)
  }

  const formatDate = (dateString: string) => {
    const date = new Date(dateString)
    return date.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <Button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-2 px-3 py-1.5 text-[11px] font-medium text-white/80 hover:text-white bg-white/5 hover:bg-white/10 border border-white/10 rounded transition-all"
      >
        <FolderIcon />
        <span className="truncate max-w-[120px]">
          {activeSession?.name || 'No Session'}
        </span>
        <ChevronIcon isOpen={isOpen} />
      </Button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-[#141414] border border-white/10 rounded shadow-xl z-50 overflow-hidden">
          {/* Header */}
          <div className="px-3 py-2 border-b border-white/10 bg-white/5">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-white/50 uppercase tracking-wider">Sessions</span>
              <Button
                onClick={handleCreateSession}
                className="text-[10px] text-primary hover:text-primary/80 font-medium transition-colors"
              >
                + New
              </Button>
            </div>
          </div>

          {/* New session input */}
          {showNewInput && (
            <div className="px-3 py-2 border-b border-white/10 bg-primary/5">
              <input
                ref={inputRef}
                type="text"
                value={newSessionName}
                onChange={(e) => setNewSessionName(e.target.value)}
                onKeyDown={handleNewSessionKeyDown}
                placeholder="Session name..."
                className="w-full bg-transparent text-xs text-white placeholder:text-white/30 border-none outline-none"
              />
            </div>
          )}

          {/* Session list */}
          <div className="max-h-64 overflow-y-auto">
            {sessions.length === 0 ? (
              <div className="px-3 py-4 text-center text-[11px] text-white/30">
                No sessions yet
              </div>
            ) : (
              sessions.map(session => (
                <div
                  key={session.id}
                  className={`group flex items-center gap-2 px-3 py-2 hover:bg-white/5 cursor-pointer transition-colors ${
                    session.id === activeSessionId ? 'bg-primary/10 border-l-2 border-primary' : ''
                  }`}
                  onClick={() => {
                    if (!editingId && session.id !== activeSessionId) {
                      onSwitchSession(session.id)
                      setIsOpen(false)
                    }
                  }}
                >
                  {editingId === session.id ? (
                    <input
                      ref={inputRef}
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => handleRenameKeyDown(e, session.id)}
                      onClick={(e) => e.stopPropagation()}
                      className="flex-1 bg-transparent text-xs text-white border border-primary/50 rounded px-1 py-0.5 outline-none"
                    />
                  ) : (
                    <>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-white truncate">{session.name}</span>
                          {session.isActive && (
                            <span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse" />
                          )}
                        </div>
                        <div className="flex items-center gap-2 text-[10px] text-white/40">
                          <span>{formatDate(session.startTime)}</span>
                          <span>•</span>
                          <span>{session.requestCount} requests</span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <Button
                          onClick={(e) => {
                            e.stopPropagation()
                            startEditing(session)
                          }}
                          className="p-1 text-white/40 hover:text-white/80 transition-colors"
                          title="Rename"
                        >
                          <EditIcon />
                        </Button>
                        {session.id !== activeSessionId && !isCapturing && (
                          <Button
                            onClick={(e) => {
                              e.stopPropagation()
                              onDeleteSession(session.id)
                            }}
                            className="p-1 text-white/40 hover:text-red-400 transition-colors"
                            title="Delete"
                          >
                            <TrashIcon />
                          </Button>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Footer with warning if capturing */}
          {isCapturing && (
            <div className="px-3 py-2 border-t border-white/10 bg-yellow-500/10">
              <span className="text-[10px] text-yellow-500/80">
                Stop capture to switch sessions
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function FolderIcon() {
  return (
    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
    </svg>
  )
}

function ChevronIcon({ isOpen }: { isOpen: boolean }) {
  return (
    <svg className={`w-3 h-3 transition-transform ${isOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
    </svg>
  )
}

function EditIcon() {
  return (
    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
    </svg>
  )
}
