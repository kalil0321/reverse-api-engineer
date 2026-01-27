import type { AppMode } from '../shared/types'

interface ModeSelectorProps {
  mode: AppMode
  onModeChange: (mode: AppMode) => void
  disabled?: boolean
}

export function ModeSelector({ mode, onModeChange, disabled }: ModeSelectorProps) {
  return (
    <div className="flex items-center bg-white/5 rounded border border-white/10 p-0.5">
      <button
        onClick={() => onModeChange('capture')}
        disabled={disabled}
        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded transition-all ${
          mode === 'capture'
            ? 'bg-primary/20 text-primary'
            : 'text-white/50 hover:text-white/80 hover:bg-white/5'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        Capture
      </button>
      <button
        onClick={() => onModeChange('codegen')}
        disabled={disabled}
        className={`px-3 py-1 text-[10px] font-bold uppercase tracking-wider rounded transition-all ${
          mode === 'codegen'
            ? 'bg-primary/20 text-primary'
            : 'text-white/50 hover:text-white/80 hover:bg-white/5'
        } ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
      >
        Codegen
      </button>
    </div>
  )
}
