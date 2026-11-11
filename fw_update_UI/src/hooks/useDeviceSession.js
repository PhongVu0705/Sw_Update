import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

export default function useDeviceSession() {
  const [ports, setPorts] = useState([])
  const [port, setPort] = useState('')
  const [connection, setConnection] = useState({ connected: false, port: null })
  const [logs, setLogs] = useState([])
  const [ready, setReady] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const operation = useRef(false)
  const logId = useRef(0)
  const addLog = useCallback((message) => {
    const line = { id: ++logId.current, time: new Date().toLocaleTimeString('en-GB'), message: String(message) }
    setLogs((previous) => [...previous.slice(-1999), line])
  }, [])

  const perform = useCallback(async (action) => {
    if (operation.current) return
    operation.current = true
    setBusy(true)
    setError('')
    try { return await action() }
    catch (err) { setError(err.message); addLog(`ERROR: ${err.message}`) }
    finally { operation.current = false; setBusy(false) }
  }, [addLog])

  useEffect(() => {
    let active = true
    const offLog = api.on('onLogFromPy', addLog)
    const offConnection = api.on('onConnectionState', (state) => {
      setConnection(state)
      if (state.connected) setPort(state.port)
    })
    async function boot() {
      try {
        await api.ready()
        const [result, state] = await Promise.all([api.call('get_ports'), api.call('get_connection_state')])
        if (!active) return
        setPorts(result.ports || [])
        setConnection(state)
        if (state.connected) setPort(state.port)
        setReady(true)
        addLog(api.mode === 'mock' ? 'SIMULATION mode — sample data, no hardware access.' : `Found ${result.ports.length} COM port(s).`)
      } catch (err) { if (active) { setError(err.message); addLog(`ERROR: ${err.message}`) } }
    }
    boot()
    return () => { active = false; offLog(); offConnection() }
  }, [addLog])

  const refresh = () => perform(async () => {
    const result = await api.call('get_ports')
    setPorts(result.ports || [])
    if (!result.ports.some((item) => item.port === port) && !connection.connected) setPort('')
    addLog(`Found ${result.ports.length} COM port(s).`)
  })
  const toggleConnection = () => perform(async () => {
    if (!connection.connected && !port) throw new Error('Select a COM port first.')
    if (connection.connected) await api.call('disconnect_port')
    else await api.call('connect_port', port)
    setConnection(await api.call('get_connection_state'))
  })
  const leave = (onBack) => perform(async () => {
    if (connection.connected) await api.call('disconnect_port')
    onBack()
  })
  return { ports, port, setPort, connection, logs, addLog, clearLogs: () => setLogs([]), ready, busy, error, setError, perform, refresh, toggleConnection, leave }
}
