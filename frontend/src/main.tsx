import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router/dom'

import './index.css'
import { Providers } from './Providers'
import { startSignIn } from './auth/signIn'
import { createQueryClient } from './lib/queryClient'
import { createAppRouter } from './router'

const root = document.getElementById('root')!

// Microsoft sign-in first (when switched on); in development mode this returns straight away.
void startSignIn().then(
  (ready) => {
    if (!ready) return // on the way to Microsoft's sign-in page
    const router = createAppRouter()
    const queryClient = createQueryClient()
    createRoot(root).render(
      <StrictMode>
        <Providers client={queryClient}>
          <RouterProvider router={router} />
        </Providers>
      </StrictMode>,
    )
  },
  (error: unknown) => {
    root.textContent = `Sign-in failed: ${error instanceof Error ? error.message : String(error)}. Reload the page to try again.`
  },
)
