import type { ReactNode } from 'react';
import { InfoIcon, AlertTriangleIcon, OctagonAlertIcon, LightbulbIcon } from 'lucide-react';

type CalloutType = 'info' | 'warn' | 'error' | 'tip';

interface CalloutProps {
  type?: CalloutType;
  title?: ReactNode;
  children: ReactNode;
}

const STYLES: Record<CalloutType, { icon: typeof InfoIcon; iconColor: string }> = {
  info:  { icon: InfoIcon,          iconColor: 'text-sky-600' },
  warn:  { icon: AlertTriangleIcon, iconColor: 'text-orange-600' },
  error: { icon: OctagonAlertIcon,  iconColor: 'text-fd-primary' },
  tip:   { icon: LightbulbIcon,     iconColor: 'text-emerald-600' },
};

export function Callout({ type = 'info', title, children }: CalloutProps) {
  const style = STYLES[type];
  const Icon = style.icon;
  return (
    <aside
      className="mt-5 rounded-2xl p-6 flex gap-4"
      style={{
        backgroundColor: 'color-mix(in oklch, var(--color-ink) 5%, transparent)',
      }}
    >
      <Icon className={`size-5 mt-0.5 shrink-0 ${style.iconColor}`} aria-hidden="true" />
      <div className="flex-1 min-w-0">
        {title ? (
          <div className="font-semibold text-ink mb-2">{title}</div>
        ) : null}
        <div className="text-sm leading-relaxed text-ink/85 [&>*+*]:mt-3 [&_p]:m-0 [&_ul]:list-disc [&_ul]:pl-5 [&_ol]:list-decimal [&_ol]:pl-5 [&_code]:font-mono [&_code]:text-[0.85em] [&_code]:bg-ink/[0.08] [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded">
          {children}
        </div>
      </div>
    </aside>
  );
}
