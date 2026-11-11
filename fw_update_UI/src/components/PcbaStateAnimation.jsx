import { Box } from '@mui/material'
import { keyframes } from '@mui/material/styles'

const breathe = keyframes`
  0%, 100% { opacity: .25; transform: scale(.94); }
  50% { opacity: .65; transform: scale(1.04); }
`
const draw = keyframes`
  to { stroke-dashoffset: 0; }
`
const settle = keyframes`
  0% { transform: scale(.75); opacity: 0; }
  65% { transform: scale(1.08); opacity: 1; }
  100% { transform: scale(1); opacity: 1; }
`
const nudge = keyframes`
  0%, 100% { transform: translateX(0); }
  25% { transform: translateX(-3px); }
  75% { transform: translateX(3px); }
`
const insert = keyframes`
  0%, 100% { transform: translateY(-3px); opacity: .4; }
  50% { transform: translateY(3px); opacity: 1; }
`
const dot = keyframes`
  0%, 70%, 100% { opacity: .2; }
  35% { opacity: 1; }
`

export default function PcbaStateAnimation({ kind, size, color }) {
  const waiting = kind === 'waiting'
  const success = kind === 'success'
  const label = waiting ? 'Waiting for PCBA' : success ? 'PCBA update successful' : 'PCBA update failed'

  return (
    <Box role="img" aria-label={label} sx={{
      width: size, height: size, flexShrink: 0, overflow: 'hidden', contain: 'paint', color,
      '& .state-halo': { transformOrigin: '60px 60px', animation: `${breathe} 2.8s ease-in-out infinite` },
      '& .state-badge': { transformOrigin: '60px 60px', animation: `${settle} .6s ease-out both` },
      '& .state-mark': { strokeDasharray: 1, strokeDashoffset: 1, animation: `${draw} .5s ease-out .2s forwards` },
      '& .state-error': { animation: `${nudge} .24s ease-in-out .75s 2` },
      '& .state-insert': { animation: `${insert} 2s ease-in-out infinite` },
      '& .state-dot': { animation: `${dot} 1.8s ease-in-out infinite` },
      '@media (prefers-reduced-motion: reduce)': {
        '& .state-halo, & .state-badge, & .state-mark, & .state-error, & .state-insert, & .state-dot': { animation: 'none', transform: 'none' },
        '& .state-mark': { strokeDashoffset: 0 },
      },
    }}>
      <svg aria-hidden="true" viewBox="0 0 120 120" width="100%" height="100%" style={{ display: 'block', overflow: 'hidden' }}>
        <circle cx="60" cy="60" r="43" fill="currentColor" opacity=".06" />
        <circle className="state-halo" cx="60" cy="60" r="48" fill="none" stroke="currentColor" strokeWidth="2" />
        {waiting ? <>
          <rect x="38" y="38" width="44" height="43" rx="8" fill="none" stroke="currentColor" strokeWidth="2.5" />
          <rect x="50" y="50" width="20" height="19" rx="3" fill="currentColor" opacity=".3" />
          <path className="state-insert" d="M60 16 V31 M54 25 L60 31 L66 25" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          {[48, 60, 72].map((cx, index) => <circle key={cx} className="state-dot" cx={cx} cy="92" r="3" fill="currentColor" style={{ animationDelay: `${index * .2}s` }} />)}
        </> : <g className="state-badge">
          <circle cx="60" cy="60" r="37" fill="none" stroke="currentColor" strokeWidth="2.5" opacity=".3" />
          <g className={success ? undefined : 'state-error'} fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" strokeLinejoin="round">
            {success ? <path className="state-mark" pathLength="1" d="M40 60 L54 74 L81 46" /> : <>
              <path className="state-mark" pathLength="1" d="M46 46 L74 74" />
              <path className="state-mark" pathLength="1" d="M74 46 L46 74" style={{ animationDelay: '.35s' }} />
            </>}
          </g>
        </g>}
      </svg>
    </Box>
  )
}
