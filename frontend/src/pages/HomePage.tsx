import { useEffect, useState } from 'react'
import type { Session } from '@supabase/supabase-js'

import { api, ApiError } from '@/lib/api'
import { supabase } from '@/lib/supabase'
import { Button } from '@/components/ui/button'

interface MeResponse {
  id: string
  email: string
}

export default function HomePage({ session }: { session: Session }) {
  const [me, setMe] = useState<MeResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api
      .get<MeResponse>('/me')
      .then(setMe)
      .catch((err: unknown) => {
        setError(err instanceof ApiError ? err.message : 'Backend request failed')
      })
  }, [])

  return (
    <div className="mx-auto max-w-2xl space-y-8 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Document Copilot</h1>
        <Button variant="outline" onClick={() => supabase.auth.signOut()}>
          Sign out
        </Button>
      </div>

      <p className="text-muted-foreground text-center">Signed in as {session.user.email}</p>

      <div className="space-y-2 rounded-lg border p-6 text-center">
        <h2 className="text-lg font-semibold">Backend auth check</h2>
        <p className="text-muted-foreground text-sm">
          This calls <code className="bg-muted rounded px-1">GET /me</code> with your Supabase token.
        </p>
        {me && (
          <p className="text-sm">
            Backend verified <strong>{me.email}</strong> ({me.id})
          </p>
        )}
        {error && <p className="text-destructive text-sm">{error}</p>}
      </div>
    </div>
  )
}
