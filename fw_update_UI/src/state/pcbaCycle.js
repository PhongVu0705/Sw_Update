// Browser simulation of the backend state machine; shared fixtures verify parity.
export class PcbaCycle {
  phase = 'programming'

  observe(target, version) {
    const present = [0x80, 0x81].includes(target) && [0x80, 0x81].includes(version)
    const absent = [0x82, 0x83].includes(target) || [0x82, 0x83].includes(version)
    if (this.phase === 'waiting_for_next_target' && present) this.phase = 'programming'
    else if (this.phase === 'waiting_for_unplug' && absent) this.phase = 'waiting_for_next_target'
    return this.phase
  }

  updated() {
    if (this.phase !== 'programming') throw new Error('PCBA update completed outside the programming phase')
    this.phase = 'waiting_for_unplug'
  }
}
