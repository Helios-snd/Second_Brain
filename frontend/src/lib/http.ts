export class ApiError extends Error {
  readonly status: number
  readonly isNetworkError: boolean
  readonly body: unknown

  constructor(message: string, status: number, isNetworkError: boolean, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.isNetworkError = isNetworkError
    this.body = body
  }
}

export interface HttpRequestOptions {
  method?: string
  headers?: Record<string, string>
  body?: unknown
  timeoutMs?: number
}

const DEFAULT_TIMEOUT_MS = 15_000

function parseBody(text: string): unknown {
  if (!text) return undefined
  try {
    return JSON.parse(text)
  } catch {
    return text
  }
}

export async function httpRequest<T>(url: string, options: HttpRequestOptions = {}): Promise<T> {
  const { method = 'GET', headers = {}, body, timeoutMs = DEFAULT_TIMEOUT_MS } = options

  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

  let response: Response
  try {
    response = await fetch(url, {
      method,
      headers: { 'Content-Type': 'application/json', ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
  } catch (error) {
    const message = controller.signal.aborted
      ? `Request timed out after ${timeoutMs}ms`
      : error instanceof Error
        ? error.message
        : 'Network request failed'
    throw new ApiError(message, 0, true)
  } finally {
    clearTimeout(timeout)
  }

  const data = parseBody(await response.text())

  if (!response.ok) {
    throw new ApiError(`Request failed with status ${response.status}`, response.status, false, data)
  }

  return data as T
}
