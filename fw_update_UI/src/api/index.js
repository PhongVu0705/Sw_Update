import { createDesktopAdapter, createEventBus } from './desktop'
import { createMockAdapter } from './mock'

const mode = import.meta.env.VITE_API_MODE || (import.meta.env.DEV ? 'mock' : 'bridge')
if (!['mock', 'bridge'].includes(mode)) throw new Error(`Invalid VITE_API_MODE: ${mode}`)
const events = createEventBus(window)
export const api = mode === 'mock'
  ? createMockAdapter(window, events)
  : createDesktopAdapter(window, events)
