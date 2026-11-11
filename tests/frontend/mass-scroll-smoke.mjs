// Requires Vite mock on port 5173 and headless Edge/Chrome with CDP on port 9222.
import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'

const target = await (await fetch('http://127.0.0.1:9222/json/new?about:blank', { method: 'PUT' })).json()
const socket = new WebSocket(target.webSocketDebuggerUrl)
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject })
let sequence = 0
const pending = new Map()
const errors = []
socket.onmessage = ({ data }) => {
  const message = JSON.parse(data)
  if (message.id) {
    const request = pending.get(message.id)
    pending.delete(message.id)
    if (message.error) request.reject(new Error(JSON.stringify(message.error)))
    else request.resolve(message.result)
  } else if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails)
}
function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = ++sequence
    pending.set(id, { resolve, reject })
    socket.send(JSON.stringify({ id, method, params }))
  })
}
async function evaluate(expression) {
  const result = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true })
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails))
  return result.result.value
}
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
const hasText = (text) => `document.body.innerText.includes(${JSON.stringify(text)})`
async function waitFor(expression) {
  for (let i = 0; i < 150; i++) {
    if (await evaluate(`Boolean(${expression})`)) return
    await delay(100)
  }
  throw new Error(`Timed out: ${expression}\n${await evaluate('document.body.innerText')}`)
}
async function click(text) {
  await waitFor(`Array.from(document.querySelectorAll('button')).some(b => b.textContent.trim() === ${JSON.stringify(text)} && !b.disabled)`)
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === ${JSON.stringify(text)}).click()`)
  await delay(100)
}
async function feedback(targetHeader, fwHeader) {
  await evaluate(`(async () => { const {api} = await import('/src/api/index.js'); await api.call('set_pcba_feedback', ${JSON.stringify(targetHeader)}, ${JSON.stringify(fwHeader)}); })()`)
}
async function inputValues(selector, values) {
  await evaluate(`(() => { const inputs = document.querySelectorAll(${JSON.stringify(selector)}); ${JSON.stringify(values)}.forEach((value, index) => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(inputs[index], value); inputs[index].dispatchEvent(new Event('input', { bubbles: true })); }); })()`)
  await delay(100)
}
async function resize(width, height) {
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600 })
  await delay(200)
}
async function checkViewport(focus = false) {
  const layout = await evaluate(`(() => { const rect = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { top: r.top, bottom: r.bottom, height: r.height }; }; return { width: innerWidth, height: innerHeight, pageWidth: document.documentElement.scrollWidth, pageHeight: document.documentElement.scrollHeight, footer: rect('footer'), panel: rect(${JSON.stringify(focus ? '[aria-label="PCBA STATUS"]' : '[aria-label="Mass update terminal"]')}), buttons: Array.from(document.querySelectorAll('[aria-label="Focus workspace"] button')).map(el => { const r = el.getBoundingClientRect(); return { top: r.top, bottom: r.bottom }; }) }; })()`)
  assert.ok(layout.pageHeight <= layout.height + 1, `page fits viewport vertically: ${JSON.stringify(layout)}`)
  assert.ok(layout.pageWidth <= layout.width, 'page fits viewport horizontally')
  assert.ok(Math.abs(layout.footer.bottom - layout.height) < 2, 'footer stays at bottom of viewport')
  assert.ok(layout.panel.bottom <= layout.footer.top, 'panel stays above footer')
  if (focus) {
    assert.ok(layout.panel.height > 40, 'Focus status gets the remaining height')
    assert.ok(layout.buttons.every(rect => rect.top >= 0 && rect.bottom <= layout.footer.top), 'Focus Start/Stop stay visible')
    assert.equal(await evaluate(`(() => { const card = document.querySelector('[aria-label="PCBA STATUS"]'); const bounds = card.getBoundingClientRect(); return Array.from(card.querySelectorAll('p')).every(el => { const r = el.getBoundingClientRect(); return r.top >= bounds.top && r.bottom <= bounds.bottom; }); })()`), true, 'status message and FW values stay fully visible')
  } else assert.ok(layout.footer.top - layout.panel.bottom <= 25, 'log fills the remaining height without a blank gap')
  return layout.panel.height
}
async function focusMode(locked) {
  await evaluate(`document.querySelector('[aria-label="${locked ? 'Lock' : 'Unlock'} Focus Mode"]').click()`)
  await waitFor(`document.querySelectorAll('[role="dialog"] input').length === ${locked ? 2 : 1}`)
  await inputValues('[role="dialog"] input', locked ? ['operator', 'operator'] : ['operator'])
  await click(locked ? 'Lock Page' : 'Unlock Page')
  await waitFor(`!document.querySelector('[role="dialog"]')`)
}
async function checkStatusNoScroll() {
  assert.equal(await evaluate(`(() => { const card = document.querySelector('[aria-label="PCBA STATUS"]'); return [card, ...card.querySelectorAll('*')].filter(el => el instanceof HTMLElement).every(el => !['auto', 'scroll'].includes(getComputedStyle(el).overflowY)); })()`), true, 'status and animation do not create vertical scrollbars')
}
const stageIs = (stage) => `Array.from(document.querySelectorAll('footer p')).some(p => p.textContent === ${JSON.stringify(stage)})`
async function screenshot(name) {
  const artifacts = new URL('../../logs/ui-smoke/', import.meta.url)
  await mkdir(artifacts, { recursive: true })
  const result = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true })
  await writeFile(new URL(`${name}.png`, artifacts), Buffer.from(result.data, 'base64'))
}
async function checkLogSize() {
  const measure = `(() => { const box = document.querySelector('[aria-label="Mass update terminal"]'); const log = document.querySelector('[role="log"]'); return { height: box.getBoundingClientRect().height, page: document.documentElement.scrollHeight, content: log.scrollHeight, viewport: log.clientHeight, scroll: log.scrollTop, overflow: getComputedStyle(log).overflowY }; })()`
  const before = await evaluate(measure)
  await evaluate(`(() => { for (let i = 0; i < 300; i++) window.onLogFromPy('Scroll test ' + i + ' ' + 'X'.repeat(120)); })()`)
  await delay(250)
  await waitFor(`(() => { const log = document.querySelector('[role="log"]'); return log.scrollHeight - log.clientHeight - log.scrollTop < 2; })()`)
  const after = await evaluate(measure)
  assert.ok(Math.abs(after.height - before.height) < 1, 'log frame must keep its height')
  assert.ok(Math.abs(after.page - before.page) < 1, 'logs must not grow the page')
  assert.ok(after.content > after.viewport, 'log content must overflow inside its viewport')
  assert.equal(after.overflow, 'scroll')
  assert.ok(after.content - after.viewport - after.scroll < 2, `new messages auto-scroll inside the log: ${JSON.stringify(after)}`)
  await evaluate(`document.querySelector('[role="log"]').scrollTop = 0`)
  assert.equal(await evaluate(`document.querySelector('[role="log"]').scrollTop`), 0, 'old logs can be reached by scrolling')
}

try {
  await send('Runtime.enable')
  await send('Page.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: 1280, height: 800, deviceScaleFactor: 1, mobile: false })
  await send('Page.navigate', { url: process.env.UI_TEST_URL || 'http://127.0.0.1:5173' })
  await waitFor(hasText('FW Update Tool'))
  await evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Mass Update')).click()`)
  await waitFor(hasText('SIMULATION'))
  assert.equal(await evaluate(`document.querySelectorAll('[aria-label="Tool type"] [aria-pressed="true"]').length`), 0, 'no tool is preselected')
  await waitFor(`document.querySelector('[aria-label="Waiting for PCBA"]')`)
  assert.equal(await evaluate(`Boolean(document.querySelector('[role="status"].MuiAlert-root'))`), false, 'guideline card is removed')
  await checkLogSize()
  const initialLogHeight = await checkViewport()
  await resize(1280, 1000)
  assert.ok(await checkViewport() > initialLogHeight + 150, 'log grows with viewport height')
  await resize(1280, 800)
  await evaluate(`document.querySelector('[role="combobox"]').dispatchEvent(new MouseEvent('mousedown', { bubbles: true, button: 0 }))`)
  await waitFor(`document.querySelectorAll('[role="option"]').length > 1`)
  await evaluate(`Array.from(document.querySelectorAll('[role="option"]')).find(el => el.textContent.includes('SIM-COM3')).click()`)
  await click('Connect')
  await evaluate(`(() => { const dt = new DataTransfer(); dt.items.add(new File(['firmware'], 'sample.bin')); document.querySelector('[aria-label="Firmware file selection"]').dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, dataTransfer: dt })); const el = document.querySelector('input[placeholder="e.g. 1.4.2"]'); Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, '1.4.2'); el.dispatchEvent(new Event('input', { bubbles: true })); })()`)
  await delay(100)
  assert.equal(await evaluate(`Array.from(document.querySelectorAll('button')).find(b => b.textContent.trim() === 'Start').disabled`), true, 'Start requires a tool choice')
  await click('M18')
  await feedback(0x80, 0x81)
  await click('Start')
  await waitFor(stageIs('Programming MCU'))
  await waitFor(`document.querySelector('[aria-label="PCBA update in progress"]')`)
  await checkStatusNoScroll()
  assert.ok(await evaluate(`document.querySelector('[aria-label="PCBA STATUS"]').getBoundingClientRect().height < 240`), 'normal status card stays compact')
  assert.equal(await evaluate(`document.querySelector('[aria-label="PCBA update in progress"]').getAnimations({ subtree: true }).some(animation => animation.playState === 'running')`), true, 'update animation is running')
  assert.equal(await evaluate(`Boolean(document.querySelector('[aria-label="Verified firmware versions"]'))`), false)
  await screenshot('mass-status-updating')
  await waitFor(hasText('Passed 1'))
  await waitFor(stageIs('Please remove'))
  await waitFor(`document.querySelector('[aria-label="PCBA update successful"]')`)
  assert.equal(await evaluate(`document.querySelector('[aria-label="PCBA STATUS"] p').textContent`), 'Update complete. Remove the PCBA.')
  assert.equal(await evaluate(`document.querySelector('[aria-label="Actual firmware"]').textContent`), '1.4.2')
  assert.equal(await evaluate(`document.querySelector('[aria-label="Configured firmware"]').textContent`), '1.4.2')
  assert.equal(await evaluate(`Boolean(document.querySelector('[aria-label="PCBA update in progress"]'))`), false, 'animation stops after update')
  await evaluate(`(() => { const controls = document.querySelector('[aria-label="Mass update controls"]'); controls.scrollTop = controls.scrollHeight; })()`)
  await screenshot('mass-status-ok')
  await focusMode(true)
  const focusedHeight = await checkViewport(true)
  await screenshot('mass-focus-fit')
  await resize(1280, 600)
  const shortHeight = await checkViewport(true)
  assert.ok(shortHeight < focusedHeight - 150, 'Focus card shrinks on shorter windows')
  await screenshot('mass-focus-short')
  await resize(1920, 1080)
  assert.ok(await checkViewport(true) > focusedHeight + 200, 'Focus card expands on taller windows')
  await resize(390, 844)
  await checkViewport(true)
  await screenshot('mass-focus-mobile')
  await focusMode(false)
  await checkViewport()
  await evaluate(`(() => { const controls = document.querySelector('[aria-label="Mass update controls"]'); controls.scrollTop = controls.scrollHeight; })()`)
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true, 'versions fit the mobile status card')
  await screenshot('mass-status-ok-mobile')
  await resize(1280, 800)
  for (const pair of [[0x80, 0x81], [0x85, 0x85], [null, 0x81]]) {
    await feedback(...pair)
    await delay(750)
    assert.equal(await evaluate(stageIs('Please remove')), true)
  }
  await feedback(0x82, 0x81)
  await waitFor(stageIs('Insert PCBA'))
  await waitFor(`document.querySelector('[aria-label="Waiting for PCBA"]')`)
  assert.equal(await evaluate(`Boolean(document.querySelector('[aria-label="Verified firmware versions"]'))`), false, 'previous board versions disappear while waiting')
  await feedback(0x80, null)
  await delay(750)
  assert.equal(await evaluate(stageIs('Insert PCBA')), true)
  await click('Insert PCBA')
  await waitFor(`document.querySelector('[aria-label="PCBA update in progress"]')`)
  await waitFor(hasText('Passed 2'))
  await click('Stop')
  await waitFor(hasText('STOPPED'))
  assert.equal(await evaluate(`Boolean(document.querySelector('[aria-label="PCBA update in progress"]'))`), false)
  await feedback(0x80, 0x81)
  await delay(800)
  assert.equal(await evaluate(hasText('Passed 3')), false)
  await resize(390, 844)
  await checkViewport()
  await checkLogSize()
  assert.equal(await evaluate('document.documentElement.scrollWidth <= window.innerWidth'), true)
  await screenshot('mass-scroll-mobile')
  // Hold only the rendered update state to inspect animation across window sizes.
  // The full two-board workflow above uses the normal mock adapter.
  await evaluate(`(async () => { const { api } = await import('/src/api/index.js'); window.__restoreAnimationApi = api.call; api.call = async (method, ...args) => { if (method === 'run_mass_update') { window.onMassStage('programming'); return { status: 'STARTED' }; } return window.__restoreAnimationApi(method, ...args); }; })()`)
  await resize(1280, 800)
  await focusMode(true)
  await click('Start')
  await waitFor(`document.querySelector('[aria-label="PCBA update in progress"]')`)
  for (const [width, height] of [[1280, 800], [1280, 600], [390, 844]]) {
    await resize(width, height)
    await checkViewport(true)
    const before = await evaluate(`document.querySelector('[aria-label="PCBA STATUS"]').getBoundingClientRect().height`)
    for (let frame = 0; frame < 4; frame++) { await delay(100); await checkStatusNoScroll() }
    assert.equal(await evaluate(`document.querySelector('[aria-label="PCBA STATUS"]').getBoundingClientRect().height`), before, 'animation keeps layout stable')
    await screenshot(`mass-animation-${width}-${height}`)
  }
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] })
  await delay(100)
  assert.equal(await evaluate(`document.querySelector('[aria-label="PCBA update in progress"]').getAnimations({ subtree: true }).some(animation => animation.playState === 'running')`), false, 'reduced motion stops the animation')
  await send('Emulation.setEmulatedMedia', { features: [] })
  // Exercise result/waiting visuals using bridge events within the held UI fixture.
  for (const [kind, label] of [['error', 'PCBA update failed'], ['waiting', 'Waiting for PCBA'], ['success', 'PCBA update successful']]) {
    await evaluate(`(() => { ${kind === 'waiting' ? "window.onMassStage('waiting_for_next_target');" : `window.onMassStage('programming'); window.onMassResult({ pass: ${kind === 'success'}, detected: '1.4.2', expected: '1.4.2', reason: ${JSON.stringify(kind === 'error' ? 'Simulated visual test failure' : '')} }); window.onMassStage('waiting_for_unplug');`} })()`)
    await waitFor(`document.querySelector('[aria-label="${label}"]')`)
    assert.equal(await evaluate(`document.querySelector('[aria-label="${label}"]').getAnimations({ subtree: true }).some(animation => animation.playState === 'running')`), true, `${kind} animation is running`)
    if (kind !== 'waiting') await waitFor(`Array.from(document.querySelectorAll('[aria-label="${label}"] .state-mark')).every(path => Math.abs(parseFloat(getComputedStyle(path).strokeDashoffset)) < .001)`)
    for (const [width, height] of [[1280, 600], [390, 844]]) {
      await resize(width, height)
      await checkViewport(true)
      await checkStatusNoScroll()
      await screenshot(`mass-${kind}-${width}-${height}`)
    }
    assert.equal(await evaluate(`Boolean(document.querySelector('[aria-label="Verified firmware versions"]'))`), kind === 'success')
    await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] })
    await delay(100)
    assert.equal(await evaluate(`document.querySelector('[aria-label="${label}"]').getAnimations({ subtree: true }).some(animation => animation.playState === 'running')`), false, `${kind} respects reduced motion`)
    await send('Emulation.setEmulatedMedia', { features: [] })
  }
  await evaluate(`(async () => { const { api } = await import('/src/api/index.js'); api.call = window.__restoreAnimationApi; delete window.__restoreAnimationApi; })()`)
  await click('Stop')
  assert.equal(await evaluate(`Boolean(document.querySelector('[aria-label="PCBA update in progress"]'))`), false)
  assert.equal(await evaluate(`document.querySelector('[aria-label="PCBA STATUS"]').getAnimations({ subtree: true }).some(animation => animation.playState === 'running')`), false, 'Stop leaves a static status')
  assert.deepEqual(errors, [])
  console.log('Mass UI passed: updating/waiting/success/failure animations, no status scrollbars, reduced motion, static Stop, Focus resizing, two PCBA cycles, desktop/mobile.')
} finally {
  socket.close()
  await fetch(`http://127.0.0.1:9222/json/close/${target.id}`)
}
