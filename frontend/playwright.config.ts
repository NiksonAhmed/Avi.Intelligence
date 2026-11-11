import { defineConfig, devices } from '@playwright/test'

/**
 * End-to-end tests run the real backend (demo SharePoint connector, throwaway SQLite database)
 * and the Vite dev server. Requires `uv` on PATH and `npx playwright install chromium`.
 */
export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  // The Vite dev server serves thousands of unbundled modules; more parallel browsers than this
  // overloads a typical laptop and causes page-load timeouts.
  workers: 2,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'] } },
    { name: 'tablet', use: { ...devices['Desktop Chrome'], viewport: { width: 820, height: 1180 } } },
  ],
  webServer: [
    {
      // Fresh database every run, so tests that assign tasks find the plan entries unassigned.
      command:
        'uv run python -c "import pathlib; pathlib.Path(\'e2e.db\').unlink(missing_ok=True)"' +
        ' && uv run alembic upgrade head && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000',
      cwd: '../backend',
      url: 'http://127.0.0.1:8000/api/health',
      // Never reuse a running backend: a developer's server may be connected to live SharePoint or
      // SimpleTrials. If port 8000 is busy, stop that server first.
      reuseExistingServer: false,
      env: {
        APP_ENV: 'test',
        SHAREPOINT_MODE: 'mock',
        SIMPLETRIALS_MODE: 'mock', // never call the real SimpleTrials API from tests
        VIEDOC_MODE: 'mock', // ... nor a real Viedoc study: the demo study is used
        DATA_MANAGEMENT_ENABLED: 'true',
        DATABASE_URL: 'sqlite:///./e2e.db',
        DEV_USER_ROLE: 'admin',
        ANTHROPIC_API_KEY: '', // e2e never calls the paid AI API; the assistant runs search-only
      },
      timeout: 120_000,
    },
    {
      command: 'npm run dev',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: !process.env.CI,
      timeout: 120_000,
    },
  ],
})
