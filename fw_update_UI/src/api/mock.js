import { PcbaCycle } from '../state/pcbaCycle.js'

const responses = {
  target_m18: ['Target M18', 'Target set: M18'],
  target_m12: ['Target M12', 'Target set: M12'],
  metco_password: ['Send Default METCO Password', 'AUTH OK — session opened'],
  calibration: ['Read Data Calibration', 'Data: 08 02 1F 00'],
  fw_version: ['Check FW Version', 'FW Version: 1.4.2'],
  fw_pn: ['Check FW P/N', 'FW P/N (Decimal): 49320100'],
  mpbid: ['Check MPBID', 'Data: 4D 50 42 49 44 07 A3'],
  wipe_counters: ['Wipe Counters And Histograms', 'Command executed (no data)'],
}

export function browserFileInfo(file) {
  return { id: null, name: file.name, size: file.size, ext: file.name.split('.').pop().toLowerCase() }
}

export function createMockAdapter(host, events) {
  let connection = { connected: false, port: null }
  let timer = null
  let pcbaFeedback = [0x82, 0x83]
  const log = (message) => events.emit('onLogFromPy', `[SIM] ${message}`)
  const success = { status: 'SUCCESS' }
  const methods = {
    get_ports: () => ({ ...success, ports: [
      { port: 'SIM-COM3', description: 'Simulated Serial Port' },
      { port: 'SIM-COM4', description: 'Simulated USB Device' },
    ] }),
    get_connection_state: () => ({ ...connection }),
    connect_port(port) {
      connection = { connected: true, port }
      events.emit('onConnectionState', { ...connection })
      log(`Connected to ${port}`)
      return success
    },
    disconnect_port() {
      connection = { connected: false, port: null }
      events.emit('onConnectionState', { ...connection })
      log('Disconnected')
      return success
    },
    select_file() {
      return new Promise((resolve) => {
        const input = host.document.createElement('input')
        input.type = 'file'
        input.accept = '.bin,.csv'
        input.hidden = true
        const finish = (result) => { input.remove(); resolve(result) }
        input.addEventListener('change', () => finish(input.files[0]
          ? { ...success, ...browserFileInfo(input.files[0]) } : { status: 'CANCELLED' }), { once: true })
        input.addEventListener('cancel', () => finish({ status: 'CANCELLED' }), { once: true })
        host.document.body.appendChild(input)
        input.click()
      })
    },
    run_hex_command(command) {
      log(`>> ${command}`)
      log('<< OK (simulated response)')
      return success
    },
    run_quick_command(key) {
      const response = responses[key]
      if (!response) throw new Error('Unknown quick command')
      if (key === 'calibration') log('Sending default METCO password before reading calibration data...')
      log(`${response[0]}: ${response[1]}`)
      return { status: key === 'wipe_counters' ? 'NO_DATA' : 'SUCCESS', title: response[0], result: response[1] }
    },
    set_pcba_feedback(target, version) {
      if (![target, version].every((value) => value === null || (Number.isInteger(value) && value >= 0 && value <= 255))) throw new Error('Invalid simulated PCBA feedback')
      pcbaFeedback = [target, version]
      log(`PCBA feedback: Target=${target?.toString(16).toUpperCase() ?? 'TIMEOUT'}, FW=${version?.toString(16).toUpperCase() ?? 'TIMEOUT'}`)
      return success
    },
    run_mass_update(port, fileId, toolType, expectedFw, autoPcba = false) {
      if (timer) throw new Error('An update is already running')
      if (!['M12', 'M18'].includes(toolType)) throw new Error('Select M12 or M18 before starting.')
      if (typeof autoPcba !== 'boolean') throw new Error('Auto PCBA mode must be true or false')
      const cycle = autoPcba ? new PcbaCycle() : null
      let progress = 0
      log(`Starting simulated ${toolType} update on ${port}`)
      events.emit('onMassStage', cycle ? cycle.phase : 'programming')
      const advance = () => {
        if (cycle && cycle.phase !== 'programming') {
          const before = cycle.phase
          cycle.observe(...pcbaFeedback)
          if (before !== cycle.phase) {
            events.emit('onMassStage', cycle.phase)
            if (cycle.phase === 'programming') progress = 0
          }
          timer = setTimeout(advance, 350)
          return
        }
        progress += 10
        events.emit('onProgressFromPy', progress, progress, 100)
        if (progress === 80) events.emit('onMassStage', 'verifying')
        if (progress >= 100) {
          const result = { pass: true, detected: expectedFw, expected: expectedFw, reason: '' }
          log('PASS — simulated firmware verification')
          events.emit('onMassResult', result)
          if (cycle) {
            cycle.updated()
            events.emit('onMassStage', cycle.phase)
            timer = setTimeout(advance, 350)
          } else {
            timer = null
            events.emit('onMassStage', 'done')
            events.emit('onMassFinished', { stopped: false, reason: '' })
          }
        } else {
          timer = setTimeout(advance, 350)
        }
      }
      timer = setTimeout(advance, 350)
      return { status: 'STARTED' }
    },
    stop_update() {
      clearTimeout(timer)
      timer = null
      log('Update stopped by operator')
      events.emit('onMassFinished', { stopped: true, reason: '' })
      return success
    },
  }
  return {
    mode: 'mock', ready: async () => {}, on: events.on,
    async call(method, ...args) {
      if (!methods[method]) throw new Error(`Mock API method unavailable: ${method}`)
      if (['run_hex_command', 'run_quick_command', 'run_mass_update'].includes(method) && !connection.connected) {
        throw new Error('Connect to a simulated COM port first')
      }
      return methods[method](...args)
    },
  }
}
