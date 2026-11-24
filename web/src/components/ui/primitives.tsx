import { forwardRef, useId, useState, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes } from 'react'
import { AlertCircle, Eye, EyeOff, LoaderCircle } from 'lucide-react'
import { initials as toInitials } from '../../lib/format'

const cx = (...parts: (string | false | null | undefined)[]) => parts.filter(Boolean).join(' ')
export { cx }

/* ── Button ─────────────────────────────────────────────────────────────── */
type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'outline' | 'danger' | 'danger-text'
interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: 'sm' | 'md' | 'lg'
  block?: boolean
  loading?: boolean
  icon?: ReactNode
  iconOnly?: boolean
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', block, loading, icon, iconOnly, className, children, disabled, type = 'button', ...rest }, ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      className={cx('btn', variant !== 'secondary' && `btn-${variant}`, size !== 'md' && `btn-${size}`, block && 'btn-block', iconOnly && 'btn-icon', className)}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner /> : icon}
      {children}
    </button>
  )
})

export function Spinner({ label }: { label?: string }) {
  return <LoaderCircle className="spinner" aria-hidden={!label} aria-label={label} role={label ? 'status' : undefined} />
}

/* ── Fields ─────────────────────────────────────────────────────────────── */
interface FieldShellProps { label: ReactNode; hint?: ReactNode; error?: string | null; id: string; aside?: ReactNode; children: ReactNode }
function FieldShell({ label, hint, error, id, aside, children }: FieldShellProps) {
  return (
    <div className="field">
      <div className="field-label"><label htmlFor={id}>{label}</label>{aside}</div>
      {children}
      {error ? (
        <div className="field-error" id={`${id}-error`} role="alert"><AlertCircle aria-hidden />{error}</div>
      ) : hint ? <div className="field-hint" id={`${id}-hint`}>{hint}</div> : null}
    </div>
  )
}

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, 'id'> {
  label: ReactNode
  hint?: ReactNode
  error?: string | null
  icon?: ReactNode
  aside?: ReactNode
}

export const TextField = forwardRef<HTMLInputElement, TextFieldProps>(function TextField({ label, hint, error, icon, aside, className, ...rest }, ref) {
  const id = useId()
  return (
    <FieldShell label={label} hint={hint} error={error} id={id} aside={aside}>
      <div className="input-wrap">
        {icon}
        <input
          ref={ref}
          id={id}
          className={cx('input', !!icon && 'has-icon', className)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
          {...rest}
        />
      </div>
    </FieldShell>
  )
})

export const PasswordField = forwardRef<HTMLInputElement, Omit<TextFieldProps, 'type'>>(function PasswordField({ label, hint, error, icon, aside, className, ...rest }, ref) {
  const id = useId()
  const [shown, setShown] = useState(false)
  return (
    <FieldShell label={label} hint={hint} error={error} id={id} aside={aside}>
      <div className="input-wrap">
        {icon}
        <input
          ref={ref}
          id={id}
          type={shown ? 'text' : 'password'}
          className={cx('input', !!icon && 'has-icon', 'has-action', className)}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${id}-error` : hint ? `${id}-hint` : undefined}
          spellCheck={false}
          autoCapitalize="off"
          {...rest}
        />
        <button type="button" className="icon-btn input-action" onClick={() => setShown((s) => !s)} aria-label={shown ? 'Hide password' : 'Show password'} aria-pressed={shown}>
          {shown ? <EyeOff /> : <Eye />}
        </button>
      </div>
    </FieldShell>
  )
})

interface SelectFieldProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'id'> { label: ReactNode; hint?: ReactNode; error?: string | null; children: ReactNode }
export function SelectField({ label, hint, error, children, className, ...rest }: SelectFieldProps) {
  const id = useId()
  return (
    <FieldShell label={label} hint={hint} error={error} id={id}>
      <select id={id} className={cx('input', className)} aria-invalid={error ? true : undefined} {...rest}>{children}</select>
    </FieldShell>
  )
}

export function Switch({ checked, onChange, label, description, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode; description?: ReactNode; disabled?: boolean }) {
  const id = useId()
  return (
    <div className="row-between" style={{ minHeight: 52 }}>
      <label htmlFor={id} className="grow" style={{ cursor: 'pointer' }}>
        <div style={{ fontWeight: 520 }}>{label}</div>
        {description && <div className="small muted">{description}</div>}
      </label>
      <span className="switch">
        <input id={id} type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
        <span className="switch-track" />
        <span className="switch-thumb" />
      </span>
    </div>
  )
}

/* ── Segmented control ──────────────────────────────────────────────────── */
export interface SegmentOption<T extends string> { value: T; label: ReactNode; icon?: ReactNode; disabled?: boolean }
export function Segmented<T extends string>({ value, onChange, options, label, compact }: { value: T; onChange: (v: T) => void; options: SegmentOption<T>[]; label: string; compact?: boolean }) {
  return (
    <div className={cx('segmented', compact && 'compact')} role="group" aria-label={label}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={o.value === value} disabled={o.disabled} onClick={() => onChange(o.value)}>
          {o.icon}{o.label}
        </button>
      ))}
    </div>
  )
}

/* ── Card ───────────────────────────────────────────────────────────────── */
export function Card({ title, icon, action, sub, children, className, flush, id, as: As = 'section' }: {
  title?: ReactNode; icon?: ReactNode; action?: ReactNode; sub?: ReactNode; children?: ReactNode; className?: string; flush?: boolean; id?: string; as?: 'section' | 'div' | 'article'
}) {
  return (
    <As className={cx('card', flush && 'card-flush', className)} id={id}>
      {(title || action) && (
        <header className="card-header" style={flush ? { padding: '16px 16px 0' } : undefined}>
          <div className="grow">
            {title && <h2 className="card-title">{icon}{title}</h2>}
            {sub && <div className="card-sub">{sub}</div>}
          </div>
          {action}
        </header>
      )}
      {children}
    </As>
  )
}

/* ── Badge ──────────────────────────────────────────────────────────────── */
export function Badge({ tone = 'neutral', icon, children }: { tone?: 'neutral' | 'success' | 'warning' | 'danger' | 'accent' | 'live'; icon?: ReactNode; children: ReactNode }) {
  return <span className={cx('badge', tone !== 'neutral' && `badge-${tone}`)}>{icon}{children}</span>
}

/* ── Avatar ─────────────────────────────────────────────────────────────── */
export function Avatar({ name, email, src, size = 'md' }: { name?: string | null; email?: string; src?: string | null; size?: 'sm' | 'md' | 'lg' | 'xl' }) {
  const [failed, setFailed] = useState(false)
  const style = size === 'sm' ? { ['--size' as string]: '28px' } : undefined
  return (
    <span className={cx('avatar', size === 'lg' && 'avatar-lg', size === 'xl' && 'avatar-xl')} style={style} aria-hidden>
      {src && !failed ? <img src={src} alt="" referrerPolicy="no-referrer" onError={() => setFailed(true)} /> : toInitials(name, email)}
    </span>
  )
}

/* ── Skeleton ───────────────────────────────────────────────────────────── */
export function Skeleton({ width, height = 12, radius, className }: { width?: number | string; height?: number | string; radius?: number; className?: string }) {
  return <span className={cx('skeleton', className)} style={{ width, height, borderRadius: radius }} aria-hidden />
}

export function SkeletonList({ rows = 4 }: { rows?: number }) {
  return (
    <div className="list" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div className="list-item" key={i}>
          <Skeleton width={40} height={40} radius={12} />
          <div className="grow stack-sm"><Skeleton width="55%" height={13} /><Skeleton width="35%" height={11} /></div>
          <Skeleton width={44} height={20} />
        </div>
      ))}
    </div>
  )
}

/* ── Empty / error states ───────────────────────────────────────────────── */
export function EmptyState({ icon, title, children, action }: { icon: ReactNode; title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="state">
      <div className="state-icon" aria-hidden>{icon}</div>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
      {action && <div className="row">{action}</div>}
    </div>
  )
}

export function ErrorState({ title = 'Could not load this', message, onRetry, icon }: { title?: string; message?: string; onRetry?: () => void; icon: ReactNode }) {
  return (
    <div className="state state-error" role="alert">
      <div className="state-icon" aria-hidden>{icon}</div>
      <h3>{title}</h3>
      {message && <p>{message}</p>}
      {onRetry && <div className="row"><Button onClick={onRetry}>Try again</Button></div>}
    </div>
  )
}

/* ── Progress ───────────────────────────────────────────────────────────── */
export function ProgressBar({ value, label, indeterminate }: { value?: number; label: string; indeterminate?: boolean }) {
  const pct = Math.round(Math.max(0, Math.min(1, value ?? 0)) * 100)
  return (
    <div className={cx('progress', indeterminate && 'progress-indeterminate')} role="progressbar" aria-label={label}
      aria-valuemin={0} aria-valuemax={100} aria-valuenow={indeterminate ? undefined : pct}>
      <span style={{ width: `${pct}%` }} />
    </div>
  )
}

/* ── Callout ────────────────────────────────────────────────────────────── */
export function Callout({ tone = 'info', icon, children }: { tone?: 'info' | 'warning' | 'danger' | 'success'; icon: ReactNode; children: ReactNode }) {
  return <div className={cx('callout', `callout-${tone}`)} role={tone === 'danger' ? 'alert' : undefined}>{icon}<div>{children}</div></div>
}
