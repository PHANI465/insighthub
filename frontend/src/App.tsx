import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthProvider } from './contexts/AuthContext'
import AppLayout from './components/layout/AppLayout'
import LoginPage from './pages/LoginPage'
import ExecutiveDashboard from './pages/ExecutiveDashboard'
import CustomerAnalytics from './pages/CustomerAnalytics'
import SupportOperations from './pages/SupportOperations'
import KnowledgeSearch from './pages/KnowledgeSearch'
import AIInsights from './pages/AIInsights'

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<LoginPage />} />

          {/* Viewer+ pages */}
          <Route element={<AppLayout minRole="Viewer" />}>
            <Route path="/dashboard" element={<ExecutiveDashboard />} />
            <Route path="/insights" element={<AIInsights />} />
          </Route>

          {/* Analyst+ pages */}
          <Route element={<AppLayout minRole="Analyst" />}>
            <Route path="/customers" element={<CustomerAnalytics />} />
            <Route path="/support" element={<SupportOperations />} />
            <Route path="/search" element={<KnowledgeSearch />} />
          </Route>

          {/* Default redirect */}
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
