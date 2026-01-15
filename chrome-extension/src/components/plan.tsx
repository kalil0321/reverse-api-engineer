interface PlanTodo {
  id?: string
  label: string
  status: 'pending' | 'in_progress' | 'completed' | 'cancelled'
  description?: string
}

interface PlanProps {
  title?: string
  description?: string
  todos: PlanTodo[]
  className?: string
}

export function Plan({ title, description, todos, className = '' }: PlanProps) {
  const completed = todos.filter(t => t.status === 'completed').length
  const inProgress = todos.filter(t => t.status === 'in_progress').length
  const total = todos.length

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <span className="text-green-500/90">✓</span>
      case 'in_progress':
        return <span className="text-primary animate-pulse">⟳</span>
      case 'cancelled':
        return <span className="text-text-secondary/40">✗</span>
      default:
        return <span className="text-text-secondary/60">○</span>
    }
  }

  return (
    <div className={`border-l-2 border-primary/30 bg-black/20 ${className}`}>
      {(title || description) && (
        <div className="px-4 py-3 border-b border-border/30">
          {title && (
            <h3 className="text-sm font-semibold text-white/90 mb-1">{title}</h3>
          )}
          {description && (
            <p className="text-[12px] text-text-secondary/80">{description}</p>
          )}
        </div>
      )}
      
      {total > 0 && (
        <div className="px-4 py-2 border-b border-border/30 flex items-center gap-3 text-[11px]">
          <span className="text-text-secondary/80 font-medium">
            {completed} of {total} complete
          </span>
          {inProgress > 0 && (
            <span className="text-primary/80">{inProgress} in progress</span>
          )}
        </div>
      )}
      
      <div className="divide-y divide-border/20">
        {todos.map((todo, idx) => {
          const isCompleted = todo.status === 'completed'
          const isInProgress = todo.status === 'in_progress'
          const isCancelled = todo.status === 'cancelled'
          
          return (
            <div
              key={todo.id || idx}
              className={`px-4 py-3 flex items-start gap-3 ${
                isCompleted ? 'text-text-secondary/60' : 
                isInProgress ? 'text-primary/90' : 
                isCancelled ? 'text-text-secondary/40' :
                'text-white/80'
              }`}
            >
              <div className="mt-0.5 flex-shrink-0 text-[14px]">
                {getStatusIcon(todo.status)}
              </div>
              <div className="flex-1 min-w-0">
                <div className={`text-[13px] ${isCompleted ? 'line-through' : ''} ${isCancelled ? 'line-through' : ''}`}>
                  {todo.label}
                </div>
                {todo.description && (
                  <div className="text-[11px] text-text-secondary/70 mt-1">
                    {todo.description}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
