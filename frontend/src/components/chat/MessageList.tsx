import { useEffect, useRef } from 'react'
import type { ChatStatus, UIMessage } from 'ai'

import { ScrollArea } from '@/components/ui/scroll-area'
import MessageBubble from '@/components/chat/MessageBubble'
import StreamingIndicator from '@/components/chat/StreamingIndicator'

interface MessageListProps {
  messages: UIMessage[]
  status: ChatStatus
}

export default function MessageList({ messages, status }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, status])

  return (
    <ScrollArea className="flex-1 px-4">
      <div className="mx-auto max-w-2xl space-y-4 py-4">
        {messages.length === 0 && (
          <p className="text-muted-foreground text-center text-sm">Ask a question about the filings corpus.</p>
        )}
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {(status === 'submitted' || status === 'streaming') && <StreamingIndicator />}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  )
}
