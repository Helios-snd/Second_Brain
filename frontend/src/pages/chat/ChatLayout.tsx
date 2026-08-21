import { Outlet } from 'react-router-dom'

import ThreadSidebar from '@/components/chat/ThreadSidebar'
import { SidebarInset, SidebarProvider } from '@/components/ui/sidebar'

export default function ChatLayout() {
  return (
    <SidebarProvider>
      <ThreadSidebar />
      <SidebarInset>
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  )
}
