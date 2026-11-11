export const backendEvents = [
  'onLogFromPy', 'onConnectionState', 'onProgressFromPy',
  'onMassStage', 'onMassResult', 'onMassFinished',
]

export function createEventBus(host) {
  const listeners = new Map()
  for (const event of backendEvents) {
    listeners.set(event, new Set())
    host[event] = (...args) => {
      for (const listener of listeners.get(event)) listener(...args)
    }
  }
  return {
    on(event, listener) {
      if (!listeners.has(event)) throw new Error(`Unknown backend event: ${event}`)
      listeners.get(event).add(listener)
      return () => listeners.get(event).delete(listener)
    },
    emit(event, ...args) { host[event](...args) },
  }
}

export function createDesktopAdapter(host, events, timeoutMs = 8000) {
  let readyPromise
  function ready() {
    if (host.pywebview?.api) return Promise.resolve(host.pywebview.api)
    if (readyPromise) return readyPromise
    readyPromise = new Promise((resolve, reject) => {
      const cleanup = () => {
        host.removeEventListener('pywebviewready', check)
        clearTimeout(timeout)
      }
      const check = () => {
        if (!host.pywebview?.api) return
        cleanup()
        resolve(host.pywebview.api)
      }
      const timeout = setTimeout(() => {
        cleanup()
        readyPromise = undefined
        reject(new Error('Python backend unavailable. Open the desktop app, or use VITE_API_MODE=mock for a browser preview.'))
      }, timeoutMs)
      host.addEventListener('pywebviewready', check)
      check()
    })
    return readyPromise
  }

  async function call(method, ...args) {
    const bridge = await ready()
    if (typeof bridge[method] !== 'function') throw new Error(`Python API method unavailable: ${method}`)
    const result = await bridge[method](...args)
    if (typeof result?.ok !== 'boolean') throw new Error('Invalid response from Python backend. Rebuild the UI and restart the desktop app.')
    if (!result.ok) throw new Error(result.error || `${method} failed`)
    if (method === 'select_file' && result.data === null) return { status: 'CANCELLED' }
    return result.data
  }
  return { mode: 'bridge', ready, call, on: events.on }
}
