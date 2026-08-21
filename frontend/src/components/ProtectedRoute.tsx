import { Navigate, Outlet } from 'react-router-dom'

import { useSession } from '@/lib/session-context'

export default function ProtectedRoute() {
  const { session, loading } = useSession()

  if (loading) return null
  if (!session) return <Navigate to="/login" replace />

  return <Outlet />
}
