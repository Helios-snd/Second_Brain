export default function ChatListPage() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-xl font-semibold">Document Copilot</h1>
      <p className="text-muted-foreground max-w-md text-sm">
        Select a conversation from the sidebar, or start a new one to ask about the filings corpus.
      </p>
    </div>
  )
}
