/**
 * Microsoft sign-in (user decision 2026-11-19). The backend says whether it is switched on
 * (GET /auth/config). When it is, people are sent to Microsoft to sign in, and their access token for
 * Avi.Intelligence goes once to POST /auth/session, which keeps it in an HttpOnly cookie. Every API call
 * and every plain download link then carries the sign-in; the token is renewed before it runs out.
 * In development mode (no Entra IDs in .env) none of this runs.
 */
import { InteractionRequiredAuthError, PublicClientApplication } from '@azure/msal-browser'

interface AuthConfig {
  mode: 'entra' | 'development'
  client_id: string | null
  authority: string | null
  scope: string | null
}

const RENEW_MS = 30 * 60 * 1000 // Microsoft access tokens last at least an hour.

let msal: PublicClientApplication | null = null
let scopes: string[] = []
let renewTimer: ReturnType<typeof setTimeout> | undefined

export function signInEnabled(): boolean {
  return msal !== null
}

/** Runs before the app renders. Resolves false when the page is on its way to Microsoft's sign-in. */
export async function startSignIn(): Promise<boolean> {
  let cfg: AuthConfig
  try {
    const res = await fetch('/api/v1/auth/config', { headers: { Accept: 'application/json' } })
    if (!res.ok) return true // let the app show its usual "cannot reach the server" messages
    cfg = (await res.json()) as AuthConfig
  } catch {
    return true
  }
  if (cfg.mode !== 'entra' || !cfg.client_id || !cfg.authority || !cfg.scope) return true

  msal = new PublicClientApplication({
    auth: {
      clientId: cfg.client_id,
      authority: cfg.authority,
      redirectUri: window.location.origin,
      postLogoutRedirectUri: window.location.origin,
    },
    cache: { cacheLocation: 'sessionStorage' },
  })
  scopes = [cfg.scope]
  await msal.initialize()
  const result = await msal.handleRedirectPromise()
  const account = result?.account ?? msal.getActiveAccount() ?? msal.getAllAccounts()[0]
  if (!account) {
    await msal.loginRedirect({ scopes })
    return false
  }
  msal.setActiveAccount(account)
  return renewSession()
}

/** Gets a fresh token (silently when possible) and hands it to the backend's session cookie. */
export async function renewSession(): Promise<boolean> {
  if (!msal) return false
  const account = msal.getActiveAccount() ?? undefined
  try {
    const { accessToken } = await msal.acquireTokenSilent({ scopes, account })
    const res = await fetch('/api/v1/auth/session', {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
    })
    clearTimeout(renewTimer)
    renewTimer = setTimeout(() => void renewSession(), RENEW_MS)
    return res.ok
  } catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
      await msal.acquireTokenRedirect({ scopes, account })
      return false
    }
    throw error
  }
}

export async function signOut(): Promise<void> {
  clearTimeout(renewTimer)
  await fetch('/api/v1/auth/session', { method: 'DELETE' })
  await msal?.logoutRedirect()
}
