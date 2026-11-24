import { createContext, useContext, useEffect, type ReactNode } from 'react'

export interface PageMeta {
  title: string
  subtitle?: string
  /** Show a back button to this path (mobile top bar). */
  back?: string
  /** Contextual quick actions for the top bar. */
  actions?: ReactNode
}

export const PageMetaContext = createContext<(meta: PageMeta) => void>(() => {})

/** Each page declares its own title, back target and quick actions for the shell's top bar. */
export function usePageMeta(meta: PageMeta, deps: unknown[] = []): void {
  const set = useContext(PageMetaContext)
  useEffect(() => {
    set(meta)
    document.title = meta.title === 'Home' ? 'AquaCount' : `${meta.title} · AquaCount`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta.title, meta.subtitle, meta.back, ...deps])
}
