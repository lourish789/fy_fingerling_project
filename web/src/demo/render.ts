/**
 * Demo only: draws synthetic camera frames in the style of the real overlay
 * (channel, counting line, boxes with track IDs, count panel). No model runs.
 */
import type { ClassKey } from '../lib/types'

export interface DemoFish {
  id: number
  x: number
  y: number
  len: number
  cls: Exclude<ClassKey, 'unknown'>
  wobble: number
  speed: number
}

// The video overlay's colours (src/models/onnx_detector.py CLASS_COLORS, as RGB).
const BOX: Record<DemoFish['cls'], string> = {
  fingerling: 'rgb(0,255,0)',
  post_fingerling: 'rgb(0,191,255)',
  juvenile: 'rgb(255,140,0)',
}
const LABEL: Record<DemoFish['cls'], string> = { fingerling: 'Fingerling', post_fingerling: 'Post-Fingerling', juvenile: 'Juvenile' }

export const W = 640
export const H = 400
export const LINE_Y = H / 2
const CH_X0 = 150
const CH_X1 = 490

let canvas: HTMLCanvasElement | null = null
function ctx2d(w = W, h = H): CanvasRenderingContext2D {
  if (!canvas) canvas = document.createElement('canvas')
  canvas.width = w
  canvas.height = h
  return canvas.getContext('2d')!
}

function background(c: CanvasRenderingContext2D, t: number) {
  c.fillStyle = '#6b6f6a'
  c.fillRect(0, 0, W, H)
  // concrete edges
  c.fillStyle = '#8a8d86'
  c.fillRect(0, 0, CH_X0 - 18, H)
  c.fillRect(CH_X1 + 18, 0, W - CH_X1 - 18, H)
  // channel water
  const g = c.createLinearGradient(CH_X0, 0, CH_X1, 0)
  g.addColorStop(0, '#3a4a46')
  g.addColorStop(0.5, '#4d5f58')
  g.addColorStop(1, '#3a4a46')
  c.fillStyle = g
  c.fillRect(CH_X0, 0, CH_X1 - CH_X0, H)
  // ripples drifting downstream
  c.strokeStyle = 'rgba(220,235,230,0.08)'
  c.lineWidth = 2
  for (let i = 0; i < 9; i++) {
    const y = ((i * 53 + t * 1.6) % (H + 40)) - 20
    c.beginPath()
    c.moveTo(CH_X0 + 20, y)
    c.bezierCurveTo(CH_X0 + 120, y + 8, CH_X1 - 120, y - 8, CH_X1 - 20, y)
    c.stroke()
  }
  // channel walls
  c.fillStyle = '#2c3330'
  c.fillRect(CH_X0 - 18, 0, 18, H)
  c.fillRect(CH_X1, 0, 18, H)
}

function countingLine(c: CanvasRenderingContext2D) {
  c.strokeStyle = 'rgb(0,255,255)'
  c.lineWidth = 2
  c.setLineDash([10, 8])
  c.beginPath()
  c.moveTo(CH_X0 - 18, LINE_Y)
  c.lineTo(CH_X1 + 18, LINE_Y)
  c.stroke()
  c.setLineDash([])
  // downstream arrow
  c.beginPath()
  c.moveTo(W / 2, LINE_Y + 4)
  c.lineTo(W / 2, LINE_Y + 18)
  c.moveTo(W / 2 - 6, LINE_Y + 12)
  c.lineTo(W / 2, LINE_Y + 18)
  c.lineTo(W / 2 + 6, LINE_Y + 12)
  c.stroke()
}

function drawFish(c: CanvasRenderingContext2D, f: DemoFish, t: number) {
  c.save()
  c.translate(f.x, f.y)
  c.rotate(Math.PI / 2 + Math.sin(t / 5 + f.wobble) * 0.12) // heading downstream
  const L = f.len
  c.fillStyle = '#2a2622'
  c.beginPath()
  c.ellipse(0, 0, L / 2, L / 7, 0, 0, Math.PI * 2)
  c.fill()
  c.beginPath()
  c.moveTo(-L / 2 + 2, 0)
  c.lineTo(-L / 2 - L / 5, -L / 7)
  c.lineTo(-L / 2 - L / 5, L / 7)
  c.closePath()
  c.fill()
  // barbels
  c.strokeStyle = '#2a2622'
  c.lineWidth = 1
  c.beginPath()
  c.moveTo(L / 2 - 2, -2)
  c.lineTo(L / 2 + 8, -7)
  c.moveTo(L / 2 - 2, 2)
  c.lineTo(L / 2 + 8, 7)
  c.stroke()
  c.restore()
}

function drawBox(c: CanvasRenderingContext2D, f: DemoFish) {
  const w = f.len * 0.42 + 10
  const h = f.len * 1.25 + 8
  const x = f.x - w / 2
  const y = f.y - h / 2
  c.strokeStyle = BOX[f.cls]
  c.lineWidth = 1
  c.strokeRect(x, y, w, h)
  const text = `#${f.id} ${LABEL[f.cls]}`
  c.font = '11px sans-serif'
  const tw = c.measureText(text).width + 6
  c.fillStyle = BOX[f.cls]
  c.fillRect(x, y - 14, tw, 14)
  c.fillStyle = '#000'
  c.fillText(text, x + 3, y - 3)
}

function countPanel(c: CanvasRenderingContext2D, counts: Record<string, number>) {
  const lines = [`Total: ${counts.total ?? 0}`]
  ;(['fingerling', 'post_fingerling', 'juvenile'] as const).forEach((k) => { if (counts[k]) lines.push(`${LABEL[k]}: ${counts[k]}`) })
  c.fillStyle = 'rgba(0,0,0,0.55)'
  c.fillRect(8, 8, 150, 8 + lines.length * 18)
  c.font = '14px sans-serif'
  lines.forEach((l, i) => {
    c.fillStyle = i === 0 ? '#fff' : BOX[(['fingerling', 'post_fingerling', 'juvenile'] as const).find((k) => l.startsWith(LABEL[k]))!]
    c.fillText(l, 16, 26 + i * 18)
  })
}

/** A live frame as base64 JPEG (what the server sends on the 'frame' event). */
export function renderFrame(fish: DemoFish[], counts: Record<string, number>, t: number): string {
  const c = ctx2d()
  background(c, t)
  countingLine(c)
  fish.forEach((f) => drawFish(c, f, t))
  fish.forEach((f) => drawBox(c, f))
  countPanel(c, counts)
  return canvas!.toDataURL('image/jpeg', 0.72).split(',')[1]
}

/** A still with `n` fish (photos, batch images). */
export function renderStill(fish: DemoFish[], counts: Record<string, number>, seed: number): string {
  const c = ctx2d()
  background(c, seed * 7)
  fish.forEach((f) => drawFish(c, f, seed))
  fish.forEach((f) => drawBox(c, f))
  countPanel(c, counts)
  return canvas!.toDataURL('image/jpeg', 0.75)
}

/** A spot-check crop of one counted fish. */
export function renderCrop(cls: DemoFish['cls'], seed: number): string {
  const c = ctx2d(120, 120)
  c.fillStyle = '#4a5b55'
  c.fillRect(0, 0, 120, 120)
  c.strokeStyle = 'rgba(220,235,230,0.1)'
  c.beginPath()
  c.moveTo(0, 30 + (seed % 40))
  c.bezierCurveTo(40, 40, 80, 20, 120, 35 + (seed % 30))
  c.stroke()
  const len = cls === 'fingerling' ? 50 : cls === 'post_fingerling' ? 64 : 80
  drawFish(c, { id: seed, x: 60, y: 60, len, cls, wobble: seed, speed: 0 }, seed)
  return canvas!.toDataURL('image/jpeg', 0.8)
}

let nextId = 1
export function spawnFish(rand: () => number): DemoFish {
  const r = rand()
  const cls: DemoFish['cls'] = r < 0.8 ? 'fingerling' : r < 0.95 ? 'post_fingerling' : 'juvenile'
  const len = cls === 'fingerling' ? 34 + rand() * 8 : cls === 'post_fingerling' ? 44 + rand() * 8 : 56 + rand() * 10
  return { id: nextId++, x: CH_X0 + 40 + rand() * (CH_X1 - CH_X0 - 80), y: -30, len, cls, wobble: rand() * 6, speed: 3.2 + rand() * 1.6 }
}

export function resetFishIds() { nextId = 1 }

export function stillFish(n: number, rand: () => number): DemoFish[] {
  return Array.from({ length: n }, (_, i) => {
    const f = spawnFish(rand)
    f.id = i + 1
    f.y = 40 + rand() * (H - 80)
    return f
  })
}
