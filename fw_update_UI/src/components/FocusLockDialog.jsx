import { useState } from 'react'
import { Alert, Button, Dialog, DialogActions, DialogContent, DialogTitle, Stack, TextField, Typography } from '@mui/material'

export default function FocusLockDialog({ locked, password, onAccept, onClose }) {
  const [value, setValue] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState('')
  const submit = (event) => {
    event.preventDefault()
    if (!value) { setError('Please enter a password.'); return }
    if (locked && value !== password) { setError('Incorrect password.'); return }
    if (!locked && value !== confirmation) { setError('Passwords do not match.'); return }
    onAccept(value)
  }
  return (
    <Dialog open onClose={onClose} aria-labelledby="focus-lock-title">
      <DialogTitle id="focus-lock-title">{locked ? 'Enter Password to Unlock' : 'Set Lock Password'}</DialogTitle>
      <form onSubmit={submit}>
        <DialogContent dividers>
          <Stack spacing={2.5}>
            <Typography variant="body2" color="text.secondary">{locked ? 'Enter the lock password to restore the full layout.' : 'Focus Mode hides setup controls and the terminal. Start and Stop remain available. The password applies to this session.'}</Typography>
            <TextField autoFocus required type="password" label="Password" value={value} onChange={(event) => setValue(event.target.value)} autoComplete={locked ? 'current-password' : 'new-password'} />
            {!locked && <TextField required type="password" label="Confirm password" value={confirmation} onChange={(event) => setConfirmation(event.target.value)} autoComplete="new-password" />}
            {error && <Alert severity="error">{error}</Alert>}
          </Stack>
        </DialogContent>
        <DialogActions><Button onClick={onClose}>Cancel</Button><Button type="submit" variant="contained">{locked ? 'Unlock Page' : 'Lock Page'}</Button></DialogActions>
      </form>
    </Dialog>
  )
}
