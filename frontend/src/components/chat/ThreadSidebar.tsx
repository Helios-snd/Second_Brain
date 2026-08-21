import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { PlusIcon } from 'lucide-react'

import { api, ApiError } from '@/lib/api'
import { supabase } from '@/lib/supabase'
import { useSession } from '@/lib/session-context'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from '@/components/ui/sidebar'

interface ThreadSummary {
  id: string
  title: string | null
  created_at: string
  updated_at: string
}

export default function ThreadSidebar() {
  const { session } = useSession()
  const navigate = useNavigate()
  const { threadId } = useParams()
  const [threads, setThreads] = useState<ThreadSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)

  useEffect(() => {
    api
      .get<ThreadSummary[]>('/chat/threads')
      .then(setThreads)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Could not load conversations')
      })
  }, [])

  async function handleNewThread() {
    setCreating(true)
    setError(null)
    try {
      const thread = await api.post<ThreadSummary>('/chat/threads', {})
      setThreads((prev) => [thread, ...(prev ?? [])])
      navigate(`/chats/${thread.id}`)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not create a new chat')
    } finally {
      setCreating(false)
    }
  }

  return (
    <Sidebar>
      <SidebarHeader>
        <Button onClick={handleNewThread} disabled={creating} className="w-full justify-start gap-2">
          <PlusIcon className="size-4" />
          New chat
        </Button>
      </SidebarHeader>
      <SidebarContent>
        <SidebarMenu>
          {threads === null && !error && (
            <div className="space-y-2 px-2 py-1">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          )}
          {error && <p className="text-destructive px-2 py-1 text-sm">{error}</p>}
          {threads?.length === 0 && (
            <p className="text-muted-foreground px-2 py-1 text-sm">No conversations yet</p>
          )}
          {threads?.map((thread) => (
            <SidebarMenuItem key={thread.id}>
              <SidebarMenuButton asChild isActive={thread.id === threadId}>
                <Link to={`/chats/${thread.id}`}>{thread.title ?? 'Untitled thread'}</Link>
              </SidebarMenuButton>
            </SidebarMenuItem>
          ))}
        </SidebarMenu>
      </SidebarContent>
      <SidebarFooter>
        <Separator />
        <p className="text-muted-foreground truncate px-2 text-sm">{session?.user.email}</p>
        <Button variant="outline" onClick={() => supabase.auth.signOut()}>
          Sign out
        </Button>
      </SidebarFooter>
    </Sidebar>
  )
}
