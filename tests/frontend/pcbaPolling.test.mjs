import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import { createEventBus } from '../../fw_update_UI/src/api/desktop.js'
import { createMockAdapter } from '../../fw_update_UI/src/api/mock.js'
import { PcbaCycle } from '../../fw_update_UI/src/state/pcbaCycle.js'
import { initialMassState, massReducer, pcbaStatus, stageLabels, validateMassInputs } from '../../fw_update_UI/src/state/massUpdate.js'

test('update requires an explicit M12 or M18 choice', () => {
  const config = { connected: true, port: 'COM3', file: { id: 'file', size: 10, ext: 'bin' }, expectedFw: '1.4.2', mode: 'bridge' }
  for (const toolType of [null, undefined, '', 'M20']) assert.match(validateMassInputs({ ...config, toolType }), /Select M12 or M18/)
  for (const toolType of ['M12', 'M18']) assert.equal(validateMassInputs({ ...config, toolType }), '')
})

test('simulation matches Python presence/removal rules across all 49 feedback pairs', () => {
  const cases = JSON.parse(readFileSync(new URL('../fixtures/pcba_presence.json', import.meta.url), 'utf8'))
  for (const [feedback, group] of Object.entries(cases)) {
    for (const pair of group) {
      for (const stage of ['waiting_for_unplug', 'waiting_for_next_target', 'programming']) {
        const machine = new PcbaCycle()
        machine.phase = stage
        let expected = stage
        if (feedback === 'present' && stage === 'waiting_for_next_target') expected = 'programming'
        else if (feedback === 'absent' && stage === 'waiting_for_unplug') expected = 'waiting_for_next_target'
        assert.equal(machine.observe(...pair), expected, `${stage}: ${pair}`)
      }
    }
  }
})

test('mock keeps polling every presence gate through repeated wrong feedback until Stop', async (context) => {
  context.mock.timers.enable({ apis: ['setTimeout'] })
  const events = createEventBus({})
  const adapter = createMockAdapter({}, events)
  let phase
  const results = []
  const finished = []
  events.on('onMassStage', (value) => { phase = value })
  events.on('onMassResult', (value) => results.push(value))
  events.on('onMassFinished', (value) => finished.push(value))
  const tick = (count = 1) => { for (let i = 0; i < count; i++) context.mock.timers.tick(350) }
  await adapter.call('connect_port', 'SIM-COM3')
  await adapter.call('run_mass_update', 'SIM-COM3', null, 'M12', '1.4.2', true)
  assert.equal(phase, 'programming', 'first board starts without polling')
  tick(10)
  assert.equal(results.length, 1)
  for (const expected of ['waiting_for_unplug', 'waiting_for_next_target', 'waiting_for_unplug', 'waiting_for_next_target']) {
    assert.equal(phase, expected)
    const invalid = [[null, 0x81], [0x80, null], [0x85, 0x85], ...(expected === 'waiting_for_unplug' ? [[0x80, 0x81], [0x81, 0x80]] : [[0x80, 0x82], [0x82, 0x81]])]
    for (const pair of invalid) {
      await adapter.call('set_pcba_feedback', ...pair)
      tick(100)
      assert.equal(phase, expected)
      assert.equal(finished.length, 0)
    }
    await adapter.call('set_pcba_feedback', ...(expected === 'waiting_for_unplug' ? [0x82, 0x81] : [0x80, 0x81]))
    tick()
    if (expected === 'waiting_for_next_target' && results.length === 1) {
      assert.equal(phase, 'programming')
      tick(10)
      assert.equal(results.length, 2)
    }
  }
  assert.equal(phase, 'programming')
  await adapter.call('stop_update')
  tick(1000)
  assert.equal(results.length, 2)
  assert.equal(finished.length, 1)
  assert.equal(finished[0].stopped, true)
})

test('update returns straight to removal and accepts an already removed board', () => {
  const cycle = new PcbaCycle()
  assert.equal(cycle.phase, 'programming')
  cycle.updated()
  assert.equal(cycle.observe(0x80, 0x81), 'waiting_for_unplug')
  assert.equal(cycle.observe(0x82, 0x81), 'waiting_for_next_target')
  assert.equal(cycle.observe(0x80, 0x81), 'programming')
  cycle.updated()
  assert.equal(cycle.phase, 'waiting_for_unplug')
  assert.equal(cycle.observe(null, 0x83), 'waiting_for_next_target')
})

test('PCBA card follows the two waiting steps and resets the result on the next update', () => {
  let state = massReducer(initialMassState, { type: 'start' })
  assert.deepEqual(pcbaStatus(state), { value: 'Updating firmware. Keep the PCBA connected.', tone: 'info' })
  for (let board = 1; board <= 2; board++) {
    state = massReducer(state, { type: 'stage', stage: 'programming' })
    assert.equal(pcbaStatus(state).value, 'Updating firmware. Keep the PCBA connected.')
    assert.equal(state.result, null)
    state = massReducer(state, { type: 'result', result: { pass: true, detected: '1.4.2' } })
    state = massReducer(state, { type: 'stage', stage: 'waiting_for_unplug' })
    assert.equal(pcbaStatus(state).value, 'Update complete. Remove the PCBA.')
    assert.equal(stageLabels[state.stage], 'Please remove')
    assert.equal(state.passed, board)
    state = massReducer(state, { type: 'stage', stage: 'waiting_for_next_target' })
    assert.deepEqual(pcbaStatus(state), { value: 'Insert the next PCBA to continue.', tone: 'warning' })
  }
})

test('a stopped or failed batch cannot display the previous OK status', () => {
  const state = { ...initialMassState, result: { pass: true, detected: '1.4.2' } }
  assert.deepEqual(pcbaStatus({ ...state, finish: { stopped: true } }), { value: 'STOPPED', tone: 'neutral' })
  assert.deepEqual(pcbaStatus({ ...state, finish: { reason: 'Serial lost' } }), { value: 'Error, check logs', tone: 'error' })
  assert.deepEqual(pcbaStatus({ ...state, running: true, stage: 'waiting_for_unplug', result: { pass: false } }), { value: 'Update failed. Remove the PCBA.', tone: 'error' })
})
