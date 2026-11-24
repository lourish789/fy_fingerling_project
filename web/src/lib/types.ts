export type ClassKey = 'fingerling' | 'post_fingerling' | 'juvenile' | 'unknown'
export type Counts = { total: number } & Record<ClassKey, number>

export type Theme = 'system' | 'light' | 'dark'
export type SetupType = 'channel' | 'webcam' | 'ip_camera' | 'uploads'
export type SourceKind = 'camera' | 'upload' | 'batch' | 'url'

export interface Preferences {
  theme?: Theme
  hatchery_name?: string
  role_title?: string
  setup_type?: SetupType
  size_focus?: Exclude<ClassKey, 'unknown'>[]
  daily_target?: number
  default_source?: SourceKind
  camera_index?: number
  stream_url?: string
  compact_numbers?: boolean
  haptics?: boolean
}

export interface User {
  id: string
  email: string
  name: string
  avatar_url: string | null
  role: 'admin' | 'operator'
  has_password: boolean
  google_connected: boolean
  google_email: string | null
  onboarded: boolean
  preferences: Preferences
  created_at: string | null
  last_login_at: string | null
}

export interface AuthPayload {
  access_token: string
  token_type: 'Bearer'
  expires_in: number
  user: User
  is_new?: boolean
}

export interface AuthConfig {
  google_client_id: string | null
  signup_enabled: boolean
  password_reset: 'email' | 'console'
  version: string
}

export type RunKind = 'video' | 'camera' | 'url' | 'image' | 'batch'
export type RunStatus = 'completed' | 'stopped' | 'error' | 'reset' | 'superseded' | string

export interface RunRecord {
  run_id: string
  kind: RunKind
  source: string
  status: RunStatus
  total: number
  counts: Partial<Counts>
  corrected_total: number | null
  correction_factor: number | null
  warning: string
  frames_processed: number
  processing_seconds: number
  started_at: string | null
  ended_at: string | null
  created_at: string | null
  owner: { id: string; name: string } | null
}

export interface RunList {
  runs: RunRecord[]
  total: number
  limit: number
  offset: number
  has_more: boolean
  scope: 'mine' | 'all'
}

export interface BatchResultItem {
  filename: string
  status: 'success' | 'error'
  counts?: Counts
  detections?: number
  label_summary?: string
  annotated_image?: string | null
  image?: string | null
  error?: string
}

export interface RunDetail {
  run: RunRecord
  summary: (Record<string, unknown> & { settings?: Record<string, unknown>; results?: BatchResultItem[]; correction_note?: string; source_fps?: number; processing_fps?: number; source_frames?: number; events_logged?: number; detections?: number }) | null
  files_available: boolean
  files: { name: string; label: string; bytes: number }[]
  crops: { path: string; seq: number | null; class: string }[]
  crops_total: number
  images: string[]
  media_token: string
  media_expires_in: number
}

export interface Insights {
  scope: 'mine' | 'all'
  days: number
  today: { fish: number; runs: number }
  period: {
    fish: number
    runs: number
    avg_fish_per_run: number
    best_day: { date: string; fish: number; runs: number } | null
    avg_processing_fps: number | null
    completed_share: number | null
  }
  lifetime: { runs: number; fish: number }
  series: { date: string; fish: number; runs: number }[]
  classes: Record<ClassKey, number>
  statuses: Record<string, number>
  kinds: Record<string, number>
  busiest_hour: number | null
}

export interface SessionInfo {
  id: string
  user_agent: string
  ip: string
  signed_in_at: string | null
  last_active_at: string | null
  expires_at: string | null
  current: boolean
}

export interface JobInfo { kind: string; label: string; started_at: string; started_by: string | null }

export interface StationStatus {
  is_processing: boolean
  job: JobInfo | null
  counts?: Partial<Counts>
  fps?: number
  frame_number?: number
  active_tracks?: number
  source_type?: string
  is_live?: boolean
}

export interface AdminUser {
  id: string
  email: string
  name: string
  avatar_url: string | null
  role: 'admin' | 'operator'
  is_active: boolean
  google_connected: boolean
  has_password: boolean
  runs: number
  created_at: string | null
  last_login_at: string | null
  is_you: boolean
}

export interface StationConfig {
  version: string
  model_loaded: boolean
  settings: Record<string, unknown>
  calibration: { factor?: number; note?: string }
  is_processing: boolean
  runs_dir: string | null
  database: string
  users: number
  runs_recorded: number
  features: { google_sign_in: boolean; email: boolean; open_signup: boolean }
}
