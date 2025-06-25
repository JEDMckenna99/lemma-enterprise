import React, { Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import { ErrorBoundary } from './components/ErrorBoundary'
import { LoadingSpinner } from './components/ui/LoadingSpinner'
import { AuthGate } from './components/auth/AuthGate'

// Lazy load components for code splitting
const Dashboard = React.lazy(() => import('./pages/Dashboard'))
const ApiKeys = React.lazy(() => import('./pages/ApiKeys'))
const Analytics = React.lazy(() => import('./pages/Analytics'))
const Credentials = React.lazy(() => import('./pages/Credentials'))
const Settings = React.lazy(() => import('./pages/Settings'))
const Billing = React.lazy(() => import('./pages/Billing'))

// Marketing pages (server-rendered fallback)
const MarketingFallback = () => {
  React.useEffect(() => {
    // Redirect to Flask-rendered marketing pages
    window.location.href = '/'
  }, [])
  return <LoadingSpinner />
}

function App() {
  return (
    <ErrorBoundary>
      <Suspense fallback={<LoadingSpinner />}>
        <Routes>
          {/* Marketing routes - fallback to Flask */}
          <Route path="/" element={<MarketingFallback />} />
          <Route path="/pricing" element={<MarketingFallback />} />
          <Route path="/docs" element={<MarketingFallback />} />
          
          {/* Protected app routes */}
          <Route path="/app/*" element={
            <AuthGate>
              <Routes>
                <Route index element={<Navigate to="/app/dashboard" replace />} />
                <Route path="dashboard" element={<Dashboard />} />
                <Route path="api-keys" element={<ApiKeys />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="credentials" element={<Credentials />} />
                <Route path="billing" element={<Billing />} />
                <Route path="settings" element={<Settings />} />
              </Routes>
            </AuthGate>
          } />
          
          {/* Catch all - redirect to marketing */}
          <Route path="*" element={<MarketingFallback />} />
        </Routes>
      </Suspense>
    </ErrorBoundary>
  )
}

export default App 