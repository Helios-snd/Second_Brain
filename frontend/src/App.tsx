import { Navigate, Route, Routes } from 'react-router-dom'

import ProtectedRoute from '@/components/ProtectedRoute'
import { SessionProvider, useSession } from '@/lib/session-context'
import ChatLayout from '@/pages/chat/ChatLayout'
import ChatListPage from '@/pages/chat/ChatListPage'
import ChatThreadPage from '@/pages/chat/ChatThreadPage'
import SignInPage from '@/pages/SignInPage'

function AppRoutes() {
  const { session, loading } = useSession()

  if (loading) return null

  return (
    <Routes>
      <Route path="/login" element={session ? <Navigate to="/" replace /> : <SignInPage />} />
      <Route element={<ProtectedRoute />}>
        <Route element={<ChatLayout />}>
          <Route path="/" element={<ChatListPage />} />
          <Route path="/chats/:threadId" element={<ChatThreadPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

function App() {
  return (
    <SessionProvider>
      <AppRoutes />
    </SessionProvider>
  )
}

export default App
