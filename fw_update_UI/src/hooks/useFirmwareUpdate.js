import { useEffect, useReducer, useRef, useState } from 'react'
import { api } from '../api'
import { initialMassState, massReducer, validateMassInputs } from '../state/massUpdate'

export default function useFirmwareUpdate(session, { autoPcba = false } = {}) {
  const [state, dispatch] = useReducer(massReducer, initialMassState)
  const [file, setFile] = useState(null)
  const [toolType, setToolType] = useState(null)
  const [expectedFw, setExpectedFw] = useState('')
  const running = useRef(false)
  const { addLog } = session

  useEffect(() => {
    const subscriptions = [
      api.on('onProgressFromPy', (percent, current, total) => dispatch({ type: 'progress', percent, current, total })),
      api.on('onMassStage', (stage) => dispatch({ type: 'stage', stage })),
      api.on('onMassResult', (result) => {
        dispatch({ type: 'result', result })
        if (!result.pass && result.reason) addLog(`FAIL: ${result.reason}`)
      }),
      api.on('onMassFinished', (finish) => {
        running.current = false
        dispatch({ type: 'finished', finish })
        if (finish.reason) addLog(`ERROR: ${finish.reason}`)
      }),
    ]
    return () => subscriptions.forEach((off) => off())
  }, [addLog])

  const config = { connected: session.connection.connected, port: session.port, file, toolType, expectedFw, mode: api.mode }
  const invalid = validateMassInputs(config)
  const invalidate = () => dispatch({ type: 'invalidate' })
  const start = () => {
    if (running.current || session.busy || !session.ready) return
    return session.perform(async () => {
      if (invalid) throw new Error(invalid)
      running.current = true
      dispatch({ type: 'start' })
      try {
        const response = await api.call('run_mass_update', session.port, file.id, toolType, expectedFw.trim(), autoPcba)
        if (response.cancelled) {
          running.current = false
          dispatch({ type: 'finished', finish: { stopped: true, reason: '' } })
          return
        }
        if (response.status !== 'STARTED') throw new Error(response.message || 'The update did not start.')
      } catch (err) {
        running.current = false
        dispatch({ type: 'startFailed', message: err.message })
        throw err
      }
    })
  }
  const stop = () => {
    if (!running.current) return
    return session.perform(async () => { await api.call('stop_update') })
  }
  const change = (setter) => (value) => {
    if (running.current || session.busy) return
    setter(value)
    invalidate()
  }

  return {
    state, file, toolType, expectedFw, invalid, start, stop, invalidate,
    disabled: state.running || session.busy || !session.ready,
    isRunning: () => running.current,
    setFile: change(setFile), setToolType: change(setToolType), setExpectedFw: change(setExpectedFw),
    connectionSession: {
      ...session,
      setPort: change(session.setPort),
      toggleConnection: () => {
        if (running.current || session.busy) return
        invalidate()
        return session.toggleConnection()
      },
    },
  }
}
