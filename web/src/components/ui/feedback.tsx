import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { AlertTriangle, CircleCheck, Info, X, CircleAlert } from 'lucide-react'
import { Button } from './primitives'

/* ── Toasts ─────────────────────────────────────────────────────────────── */
type Tone = 'info' | 'success' | 'warning' | 'error'
export interface ToastInput {
  title?: string
  message: string
  tone?: Tone
  /** ms; 0 keeps it until dismissed */
  duration?: number
  action?: { label: string; onClick: () => void }
  /** Replaces an existing toast with the same id instead of stacking. */
  id?: string
}
interface ToastItem extends Required<Pick<ToastInput, 'message' | 'tone'>> { id: string; title?: string; action?: ToastInput['action']; duration: number }

interface ToastApi { show: (t: ToastInput) => string; dismiss: (id: string) => void }
const ToastContext = createContext<ToastApi | null>(null)

const ICONS: Record<Tone, ReactNode> = {
  info: <Info aria-hidden />,
  success: <CircleCheck aria-hidden />,
  warning: <AlertTriangle aria-hidden />,
  error: <CircleAlert aria-hidden />,
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([])
  const timers = useRef(new Map<string, number>())

  const dismiss = useCallback((id: string) => {
    setItems((list) => list.filter((t) => t.id !== id))
    const t = timers.current.get(id)
    if (t) { clearTimeout(t); timers.current.delete(id) }
  }, [])

  const show = useCallback((input: ToastInput) => {
    const id = input.id ?? Math.random().toString(36).slice(2)
    const item: ToastItem = {
      id, title: input.title, message: input.message, tone: input.tone ?? 'info', action: input.action,
      duration: input.duration ?? (input.tone === 'error' ? 7000 : 4500),
    }
    setItems((list) => [...list.filter((t) => t.id !== id), item].slice(-3))
    const old = timers.current.get(id)
    if (old) clearTimeout(old)
    if (item.duration > 0) timers.current.set(id, window.setTimeout(() => dismiss(id), item.duration))
    return id
  }, [dismiss])

  useEffect(() => () => { timers.current.forEach((t) => clearTimeout(t)) }, [])
  const api = useMemo(() => ({ show, dismiss }), [show, dismiss])

  return (
    <ToastContext.Provider value={api}>
      {children}
      {createPortal(
        <div className="toast-region" role="region" aria-label="Notifications">
          <div aria-live="polite" aria-atomic="false" style={{ display: 'contents' }}>
            {items.map((t) => (
              <div key={t.id} className={`toast toast-${t.tone}`} role={t.tone === 'error' ? 'alert' : 'status'}>
                {ICONS[t.tone]}
                <div className="toast-body">
                  {t.title && <div className="toast-title">{t.title}</div>}
                  <div>{t.message}</div>
                </div>
                {t.action && (
                  <button className="toast-action" onClick={() => { t.action!.onClick(); dismiss(t.id) }}>{t.action.label}</button>
                )}
                <button className="toast-close" onClick={() => dismiss(t.id)} aria-label="Dismiss"><X /></button>
              </div>
            ))}
          </div>
        </div>,
        document.body,
      )}
    </ToastContext.Provider>
  )
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}

/* ── Modal dialog ───────────────────────────────────────────────────────── */
export function Dialog({ open, onClose, title, children, labelledBy = 'dialog-title' }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; labelledBy?: string }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const prev = document.activeElement as HTMLElement | null
    const node = ref.current
    node?.querySelector<HTMLElement>('input, button, [href], select, textarea')?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
      if (e.key === 'Tab' && node) {
        const f = Array.from(node.querySelectorAll<HTMLElement>('input, button, [href], select, textarea')).filter((el) => !el.hasAttribute('disabled'))
        if (!f.length) return
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus() }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus() }
      }
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => { document.removeEventListener('keydown', onKey); document.body.style.overflow = ''; prev?.focus() }
  }, [open, onClose])

  if (!open) return null
  return createPortal(
    <>
      <div className="scrim" onClick={onClose} />
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby={labelledBy} ref={ref}>
        <h2 id={labelledBy}>{title}</h2>
        {children}
      </div>
    </>,
    document.body,
  )
}

export function ConfirmDialog({ open, onClose, onConfirm, title, message, confirmLabel, danger, busy }: {
  open: boolean; onClose: () => void; onConfirm: () => void; title: string; message: ReactNode; confirmLabel: string; danger?: boolean; busy?: boolean
}) {
  return (
    <Dialog open={open} onClose={onClose} title={title}>
      <div className="secondary" style={{ marginBottom: 24 }}>{message}</div>
      <div className="row" style={{ justifyContent: 'flex-end' }}>
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button variant={danger ? 'danger' : 'primary'} onClick={onConfirm} loading={busy}>{confirmLabel}</Button>
      </div>
    </Dialog>
  )
}
