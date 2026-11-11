import { createTheme } from '@mui/material/styles'

export default createTheme({
  palette: {
    primary: { main: '#d01b2e', dark: '#a51024' },
    background: { default: '#f5f6f8', paper: '#ffffff' },
    text: { primary: '#17202e', secondary: '#657084' },
    success: { main: '#15803d' }, error: { main: '#c62828' }, divider: '#e4e7ec',
  },
  typography: {
    fontFamily: 'Inter, "Segoe UI", Arial, sans-serif',
    h1: { fontSize: '2.5rem', fontWeight: 750, letterSpacing: '-0.035em' },
    h2: { fontSize: '1.45rem', fontWeight: 700, letterSpacing: '-0.025em' },
    h3: { fontSize: '1.05rem', fontWeight: 700 },
    button: { textTransform: 'none', fontWeight: 650 },
  },
  shape: { borderRadius: 12 },
  components: {
    MuiStack: { defaultProps: { useFlexGap: true } },
    MuiButton: { defaultProps: { disableElevation: true }, styleOverrides: { root: { minHeight: 40 } } },
    MuiPaper: { defaultProps: { elevation: 0 }, styleOverrides: { outlined: { borderColor: '#e4e7ec' } } },
    MuiTextField: { defaultProps: { size: 'small', fullWidth: true } },
    MuiDialog: { defaultProps: { fullWidth: true, maxWidth: 'sm' } },
    MuiDialogTitle: { styleOverrides: { root: { fontWeight: 700 } } },
  },
})
