import AnsiToReact from 'ansi-to-react'

interface TerminalProps {
  command: string
  stdout?: string
  stderr?: string
  exitCode?: number
  durationMs?: number
  cwd?: string
  className?: string
}

export function Terminal({
  command,
  stdout,
  stderr,
  exitCode = 0,
  durationMs,
  cwd,
  className = '',
}: TerminalProps) {
  const isSuccess = exitCode === 0

  return (
    <div className={`border-l-2 ${isSuccess ? 'border-green-500/30' : 'border-primary/30'} bg-black/30 ${className}`}>
      <div className="px-4 py-2 bg-white/5 border-b border-border/30">
        <div className="flex items-center gap-2 text-[11px] font-mono">
          {cwd && <span className="text-text-secondary/60">{cwd}</span>}
          <span className="text-primary/80">$</span>
          <span className="text-white/90">{command}</span>
        </div>
      </div>
      
      {(stdout || stderr) && (
        <div className="p-4 font-mono text-[12px] leading-relaxed">
          {stdout && (
            <div className="text-white/90 whitespace-pre-wrap break-words">
              <AnsiToReact>{stdout}</AnsiToReact>
            </div>
          )}
          {stderr && (
            <div className="text-primary/90 mt-2 whitespace-pre-wrap break-words">
              <AnsiToReact>{stderr}</AnsiToReact>
            </div>
          )}
        </div>
      )}
      
      <div className={`px-4 py-2 border-t border-border/30 flex items-center gap-3 text-[10px] ${
        isSuccess ? 'text-green-500/80' : 'text-primary/80'
      }`}>
        <span className="font-semibold">
          {isSuccess ? '✓' : '✗'} Exit {exitCode}
        </span>
        {durationMs !== undefined && (
          <span className="text-text-secondary/60">
            {durationMs < 1000 ? `${durationMs}ms` : `${(durationMs / 1000).toFixed(2)}s`}
          </span>
        )}
      </div>
    </div>
  )
}
