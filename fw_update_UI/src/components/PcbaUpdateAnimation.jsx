import { Box } from '@mui/material'
import { keyframes } from '@mui/material/styles'

const dataFlow = keyframes`
  from { stroke-dashoffset: 24; }
  to { stroke-dashoffset: 0; }
`
const corePulse = keyframes`
  0%, 100% { opacity: .4; }
  50% { opacity: 1; }
`
const traces = [
  'M8 28 H24 V44 H40', 'M8 60 H40', 'M8 92 H24 V76 H40',
  'M112 28 H96 V44 H80', 'M112 60 H80', 'M112 92 H96 V76 H80',
  'M44 8 V40', 'M76 8 V40', 'M44 112 V80', 'M76 112 V80',
]

export default function PcbaUpdateAnimation({ size }) {
  return (
    <Box role="progressbar" aria-label="PCBA update in progress" aria-valuetext="Updating firmware" sx={{
      width: size, height: size, flexShrink: 0, overflow: 'hidden', contain: 'paint',
      color: '#1565c0', borderRadius: 2,
      background: 'radial-gradient(circle, #1565c018 0%, #1565c006 60%, transparent 75%)',
      '& .data-flow': { animation: `${dataFlow} 1.2s linear infinite` },
      '& .chip-core': { animation: `${corePulse} 1.8s ease-in-out infinite` },
      '@media (prefers-reduced-motion: reduce)': { '& .data-flow, & .chip-core': { animation: 'none' } },
    }}>
      <svg aria-hidden="true" viewBox="0 0 120 120" width="100%" height="100%" style={{ display: 'block', overflow: 'hidden' }}>
        <g fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          {traces.map((path) => <path key={path} d={path} opacity=".18" />)}
          {traces.map((path, index) => <path key={path} className="data-flow" d={path} strokeDasharray="4 20" style={{ animationDelay: `${index * -0.12}s` }} />)}
        </g>
        <rect x="40" y="40" width="40" height="40" rx="9" fill="#e6effa" stroke="currentColor" strokeWidth="2.5" />
        <rect className="chip-core" x="50" y="50" width="20" height="20" rx="4" fill="currentColor" />
        <g fill="currentColor" opacity=".45">
          <circle cx="8" cy="28" r="2.5" /><circle cx="8" cy="92" r="2.5" />
          <circle cx="112" cy="28" r="2.5" /><circle cx="112" cy="92" r="2.5" />
          <circle cx="44" cy="8" r="2.5" /><circle cx="76" cy="112" r="2.5" />
        </g>
      </svg>
    </Box>
  )
}
