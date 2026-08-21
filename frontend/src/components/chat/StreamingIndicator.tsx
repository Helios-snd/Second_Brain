import { Avatar, AvatarFallback } from '@/components/ui/avatar'

export default function StreamingIndicator() {
  return (
    <div className="flex gap-3">
      <Avatar className="size-8 shrink-0">
        <AvatarFallback>AI</AvatarFallback>
      </Avatar>
      <div className="bg-muted flex items-center gap-1 rounded-lg px-3 py-2">
        <span className="bg-foreground/50 size-1.5 animate-bounce rounded-full [animation-delay:-0.3s]" />
        <span className="bg-foreground/50 size-1.5 animate-bounce rounded-full [animation-delay:-0.15s]" />
        <span className="bg-foreground/50 size-1.5 animate-bounce rounded-full" />
      </div>
    </div>
  )
}
