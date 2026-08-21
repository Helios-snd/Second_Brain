import { isTextUIPart, type UIMessage } from 'ai'

import { cn } from '@/lib/utils'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'

export default function MessageBubble({ message }: { message: UIMessage }) {
  const isUser = message.role === 'user'
  const text = message.parts
    .filter(isTextUIPart)
    .map((part) => part.text)
    .join('')

  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse')}>
      <Avatar className="size-8 shrink-0">
        <AvatarFallback>{isUser ? 'U' : 'AI'}</AvatarFallback>
      </Avatar>
      <div
        className={cn(
          'max-w-[80%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted',
        )}
      >
        {text}
      </div>
    </div>
  )
}
