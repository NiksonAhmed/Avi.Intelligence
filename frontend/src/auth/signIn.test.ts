import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Microsoft's library is replaced: tests never contact Microsoft.
const msal = {
  initialize: vi.fn(async () => undefined),
  handleRedirectPromise: vi.fn(async () => null as null | { account: { username: string } }),
  getActiveAccount: vi.fn(() => null as null | { username: string }),
  getAllAccounts: vi.fn(() => [] as { username: string }[]),
  setActiveAccount: vi.fn(),
  loginRedirect: vi.fn(async () => undefined),
  acquireTokenSilent: vi.fn(async () => ({ accessToken: 'token-123' })),
  acquireTokenRedirect: vi.fn(async () => undefined),
  logoutRedirect: vi.fn(async () => undefined),
}
const created: unknown[] = []
vi.mock('@azure/msal-browser', () => ({
  InteractionRequiredAuthError: class extends Error {},
  PublicClientApplication: class {
    constructor(config: unknown) {
      created.push(config)
      return msal
    }
  },
}))

const ENTRA = {
  mode: 'entra',
  client_id: 'client-1',
  authority: 'https://login.microsoftonline.com/tenant-1',
  scope: 'api://client-1/access_as_user',
}

function serve(config: object) {
  const calls: { url: string; init?: RequestInit }[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      calls.push({ url, init })
      if (url === '/api/v1/auth/config') return new Response(JSON.stringify(config), { status: 200 })
      return new Response(null, { status: 204 })
    }),
  )
  return calls
}

async function load() {
  vi.resetModules()
  return import('./signIn')
}

describe('Microsoft sign-in', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    created.length = 0
  })
  afterEach(() => vi.unstubAllGlobals())

  it('does nothing in development mode', async () => {
    serve({ mode: 'development', client_id: null, authority: null, scope: null })
    const { startSignIn, signInEnabled } = await load()
    expect(await startSignIn()).toBe(true)
    expect(created).toHaveLength(0)
    expect(signInEnabled()).toBe(false)
  })

  it('sends someone who is not signed in to Microsoft', async () => {
    serve(ENTRA)
    const { startSignIn } = await load()
    expect(await startSignIn()).toBe(false)
    expect(created[0]).toMatchObject({ auth: { clientId: 'client-1', authority: ENTRA.authority } })
    expect(msal.loginRedirect).toHaveBeenCalledWith({ scopes: [ENTRA.scope] })
  })

  it('hands a signed-in person’s token to the backend session, then can sign out', async () => {
    const calls = serve(ENTRA)
    msal.getAllAccounts.mockReturnValueOnce([{ username: 'person@avion.example' }])
    const { startSignIn, signInEnabled, signOut } = await load()
    expect(await startSignIn()).toBe(true)
    expect(signInEnabled()).toBe(true)
    const session = calls.find((c) => c.url === '/api/v1/auth/session')
    expect(session?.init).toMatchObject({ method: 'POST', headers: { Authorization: 'Bearer token-123' } })
    await signOut()
    expect(calls.at(-1)?.init).toMatchObject({ method: 'DELETE' })
    expect(msal.logoutRedirect).toHaveBeenCalled()
  })
})
