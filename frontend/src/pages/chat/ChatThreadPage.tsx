import { useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { useChat } from '@ai-sdk/react'
import { DefaultChatTransport, type UIMessage } from 'ai'

import { env } from '@/lib/env'
import { api, ApiError } from '@/lib/api'
import { supabase } from '@/lib/supabase'
import { Skeleton } from '@/components/ui/skeleton'
import MessageList from '@/components/chat/MessageList'
import MessageInput from '@/components/chat/MessageInput'

export default function ChatThreadPage() {
  const { threadId } = useParams<{ threadId: string }>()
  if (!threadId) return null
  // Keying on threadId forces a full remount per thread, so state below
  // naturally resets on navigation instead of needing an effect-driven reset.
  return <ChatThread threadId={threadId} key={threadId} />
}

function ChatThread({ threadId }: { threadId: string }) {
  const [initialMessages, setInitialMessages] = useState<UIMessage[] | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<UIMessage[]>(`/chat/threads/${threadId}/messages`)
      .then(setInitialMessages)
      .catch((err: unknown) => {
        setLoadError(err instanceof ApiError ? err.message : 'Failed to load conversation')
      })
  }, [threadId])

  if (loadError) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <p className="text-destructive text-sm">{loadError}</p>
      </div>
    )
  }

  if (initialMessages === null) {
    return (
      <div className="mx-auto w-full max-w-2xl space-y-4 p-4">
        <Skeleton className="h-16 w-2/3" />
        <Skeleton className="ml-auto h-10 w-1/2" />
        <Skeleton className="h-16 w-2/3" />
      </div>
    )
  }

  return <ChatThreadView threadId={threadId} initialMessages={initialMessages} />
}

// `useChat`'s `messages` option only seeds initial state once, on mount — it
// does not react to later prop changes. This component must therefore not
// mount until the real message history has been fetched (see ChatThread
// above), otherwise `useChat` permanently seeds itself with an empty list.
function ChatThreadView({ threadId, initialMessages }: { threadId: string; initialMessages: UIMessage[] }) {
  const transport = useMemo(
    () =>
      new DefaultChatTransport({
        api: `${env.apiBaseUrl}/chat/stream`,
        headers: async () => {
          const { data } = await supabase.auth.getSession()
          const token = data.session?.access_token
          const headers: Record<string, string> = {}
          if (token) headers.Authorization = `Bearer ${token}`
          return headers
        },
      }),
    [],
  )

  const { messages, sendMessage, status, error } = useChat({
    id: threadId,
    messages: initialMessages,
    transport,
  })

  return (
    <div className="flex h-full flex-col">
      <MessageList messages={messages} status={status} />
      {error && <p className="text-destructive px-4 pb-2 text-sm">{error.message}</p>}
      <MessageInput
        disabled={status === 'streaming' || status === 'submitted'}
        onSend={(text) => sendMessage({ text })}
      />
    </div>
  )
}
