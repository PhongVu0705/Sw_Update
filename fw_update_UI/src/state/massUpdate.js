export const initialMassState = {
  running: false, stage: 'idle', progress: 0, current: 0, total: 0,
  passed: 0, failed: 0, result: null, finish: null,
}

export function massReducer(state, action) {
  switch (action.type) {
    case 'invalidate':
      if (state.running) return state
      return { ...state, result: null, finish: null, progress: 0, current: 0, total: 0, stage: 'idle' }
    case 'start':
      if (state.running) return state
      return { ...state, running: true, stage: 'starting', progress: 0, current: 0, total: 0, result: null, finish: null }
    case 'progress':
      if (!state.running) return state
      return { ...state, progress: Math.max(0, Math.min(100, Number(action.percent) || 0)), current: action.current, total: action.total }
    case 'stage':
      if (!state.running) return state
      if (action.stage === 'programming' && state.stage !== 'programming') {
        return { ...state, stage: action.stage, result: null, progress: 0, current: 0, total: 0 }
      }
      return { ...state, stage: action.stage }
    case 'result':
      if (!state.running || state.result) return state
      return { ...state, result: action.result, progress: action.result.pass ? 100 : state.progress,
        passed: state.passed + (action.result.pass === true ? 1 : 0),
        failed: state.failed + (action.result.pass === true ? 0 : 1) }
    case 'finished':
      return { ...state, running: false, stage: 'done', finish: action.finish }
    case 'startFailed':
      return { ...state, running: false, stage: 'idle', finish: { reason: action.message } }
    default: return state
  }
}

export function isValidVersion(value) {
  return typeof value === 'string' && value.length <= 32 && /^\d+(\.\d+){0,3}$/.test(value.trim())
}

export function validateMassInputs({ connected, port, file, toolType, expectedFw, mode }) {
  if (!connected || !port) return 'Select a COM port and press Connect first.'
  if (!['M12', 'M18'].includes(toolType)) return 'Select M12 or M18 before starting.'
  if (!file || (mode === 'bridge' && !file.id)) return 'Select firmware using the Browse button first.'
  if (!['bin', 'csv'].includes(file.ext)) return 'Unsupported file type — choose a .bin or .csv file.'
  if (!file.size) return 'The firmware file is empty. Choose a non-empty file.'
  if (!isValidVersion(expectedFw)) return 'Enter the expected firmware version as decimal numbers separated by dots, e.g. 1.4.2.'
  return ''
}

export const stageLabels = {
  idle: 'Waiting for start', starting: 'Starting mass update',
  targeting: 'Waiting for target',
  waiting_for_next_target: 'Insert PCBA', waiting_for_unplug: 'Please remove',
  programming: 'Programming MCU', verifying: 'Verifying firmware', done: 'Finished',
}

export function pcbaStatus(state) {
  if (!state.running) {
    if (state.finish?.reason) return { value: 'Error, check logs', tone: 'error' }
    if (state.finish?.stopped) return { value: 'STOPPED', tone: 'neutral' }
  }
  if (state.running) {
    if (['starting', 'programming', 'verifying', 'targeting'].includes(state.stage)) {
      return { value: 'Updating firmware. Keep the PCBA connected.', tone: 'info' }
    }
    if (state.stage === 'waiting_for_next_target') {
      return { value: 'Insert the next PCBA to continue.', tone: 'warning' }
    }
  }
  if (state.result) {
    return { value: state.result.pass ? 'Update complete. Remove the PCBA.' : 'Update failed. Remove the PCBA.', tone: state.result.pass ? 'success' : 'error' }
  }
  return { value: 'Insert the next PCBA to continue.', tone: 'neutral' }
}
