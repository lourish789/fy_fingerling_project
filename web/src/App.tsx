import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './auth/AuthProvider'
import { BootScreen, PublicOnly, RequireAuth, RequireOnboarded, RequireRole } from './auth/guards'
import { AppShell } from './components/layout/Shell'
import { ToastProvider } from './components/ui/feedback'
import { AuthLayout } from './pages/auth/AuthLayout'
import { LoginPage } from './pages/auth/LoginPage'
import { SignupPage } from './pages/auth/SignupPage'
import { ForgotPasswordPage, ResetPasswordPage } from './pages/auth/PasswordPages'
import { HomePage } from './pages/HomePage'
import { CountPage } from './pages/CountPage'
import { NotFoundPage } from './pages/NotFoundPage'

// Less-visited screens load on demand (the service worker still precaches them for offline use).
const OnboardingPage = lazy(() => import('./pages/OnboardingPage').then((m) => ({ default: m.OnboardingPage })))
const HistoryPage = lazy(() => import('./pages/HistoryPage').then((m) => ({ default: m.HistoryPage })))
const RunDetailPage = lazy(() => import('./pages/RunDetailPage').then((m) => ({ default: m.RunDetailPage })))
const InsightsPage = lazy(() => import('./pages/InsightsPage').then((m) => ({ default: m.InsightsPage })))
const ProfilePage = lazy(() => import('./pages/ProfilePage').then((m) => ({ default: m.ProfilePage })))
const SettingsPage = lazy(() => import('./pages/SettingsPage').then((m) => ({ default: m.SettingsPage })))
const AdminPage = lazy(() => import('./pages/AdminPage').then((m) => ({ default: m.AdminPage })))

export function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <Routes>
            {/* Public: signed-in visitors are sent on to the app */}
            <Route element={<PublicOnly />}>
              <Route element={<AuthLayout />}>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/signup" element={<SignupPage />} />
                <Route path="/forgot-password" element={<ForgotPasswordPage />} />
              </Route>
            </Route>
            {/* Reset links work whether or not someone is signed in on this device */}
            <Route element={<AuthLayout />}>
              <Route path="/reset-password" element={<ResetPasswordPage />} />
            </Route>

            {/* Protected */}
            <Route element={<RequireAuth />}>
              <Route path="/welcome" element={<Suspense fallback={<BootScreen />}><OnboardingPage /></Suspense>} />
              <Route element={<RequireOnboarded />}>
                <Route element={<AppShell />}>
                  <Route index element={<HomePage />} />
                  <Route path="count" element={<CountPage />} />
                  <Route path="history" element={<HistoryPage />} />
                  <Route path="history/:runId" element={<RunDetailPage />} />
                  <Route path="insights" element={<InsightsPage />} />
                  <Route path="profile" element={<ProfilePage />} />
                  <Route path="settings" element={<SettingsPage />} />
                  <Route element={<RequireRole role="admin" />}>
                    <Route path="admin" element={<AdminPage />} />
                  </Route>
                  <Route path="*" element={<NotFoundPage />} />
                </Route>
              </Route>
            </Route>
          </Routes>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  )
}
