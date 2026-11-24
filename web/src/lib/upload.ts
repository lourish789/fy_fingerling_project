import { ApiError, CLIENT_HEADER } from './api'
import { API_BASE } from './config'
import { getAccessToken } from './token'
import { demoBackend } from '../demo/registry'

export interface UploadHandle<T> {
  promise: Promise<T>
  abort: () => void
}

/**
 * POST a form with upload progress (fetch cannot report upload progress).
 * The caller makes sure the access token is fresh first: a large video is
 * never uploaded twice just to recover from an expired token.
 */
export function uploadWithProgress<T = unknown>(path: string, form: FormData, onProgress?: (fraction: number) => void): UploadHandle<T> {
  const demo = demoBackend()
  if (demo) return demoUpload<T>(demo.demoFetch, path, form, onProgress)
  const xhr = new XMLHttpRequest()
  const promise = new Promise<T>((resolve, reject) => {
    xhr.open('POST', API_BASE + path)
    const token = getAccessToken()
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)
    Object.entries(CLIENT_HEADER).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    xhr.responseType = 'json'
    xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total) }
    xhr.onload = () => {
      const body = (xhr.response && typeof xhr.response === 'object' ? xhr.response : {}) as Record<string, unknown>
      if (xhr.status >= 200 && xhr.status < 300) { onProgress?.(1); resolve(body as T); return }
      const retry = Number(xhr.getResponseHeader('Retry-After')) || undefined
      reject(new ApiError(typeof body.error === 'string' ? body.error : `Upload failed (${xhr.status}).`, xhr.status,
        typeof body.code === 'string' ? body.code : `http_${xhr.status}`, { retryAfter: retry, data: body }))
    }
    xhr.onerror = () => reject(new ApiError('The upload was interrupted. Check your connection and try again.', 0, 'network'))
    xhr.onabort = () => reject(new ApiError('Upload cancelled.', 0, 'aborted'))
    xhr.send(form)
  })
  return { promise, abort: () => xhr.abort() }
}

/** Demo builds: pretend to upload (with progress), then hand the form to the demo server. */
function demoUpload<T>(demoFetch: (u: string, i: RequestInit) => Promise<Response>, path: string, form: FormData, onProgress?: (f: number) => void): UploadHandle<T> {
  let aborted = false
  const promise = (async () => {
    for (let i = 1; i <= 10; i++) {
      await new Promise((r) => setTimeout(r, 110))
      if (aborted) throw new ApiError('Upload cancelled.', 0, 'aborted')
      onProgress?.(i / 10)
    }
    const res = await demoFetch(path, { method: 'POST', body: form })
    const body = await res.json()
    if (!res.ok) throw new ApiError(body.error ?? 'Upload failed.', res.status, body.code ?? 'error')
    return body as T
  })()
  return { promise, abort: () => { aborted = true } }
}
