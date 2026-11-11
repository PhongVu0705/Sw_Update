import { Box } from '@mui/material'
import { keyframes } from '@mui/material/styles'

const jump = keyframes`
  0%, 46%, 90%, 100% { transform: translateY(0); }
  62%, 74% { transform: translateY(-60%); }
`
const obstacle = keyframes`
  from { left: 110%; }
  to { left: -20%; }
`
const run = keyframes`
  0%, 49.99% { opacity: 1; }
  50%, 100% { opacity: 0; }
`
const ground = keyframes`
  to { background-position-x: -48px; }
`

export default function DinosaurRunner({ focus }) {
  return (
    <Box role="img" aria-label="Dinosaur jumping over obstacles" sx={{
      minWidth: 0, width: '100%', overflow: 'hidden', alignSelf: 'center',
      color: '#536174', borderRadius: 1.5, bgcolor: '#ffffff80',
    }}>
      <Box sx={{
        position: 'relative', height: focus ? 'clamp(100px, 26cqh, 190px)' : 104,
        overflow: 'hidden', contain: 'paint',
        '& .dino-jump': { animation: `${jump} 2.6s ease-in-out infinite` },
        '& .dino-cactus': { animation: `${obstacle} 2.6s linear infinite` },
        '& .dino-leg': { animation: `${run} .24s steps(1) infinite` },
        '& .dino-leg-alt': { animationDelay: '-.12s' },
        '& .dino-ground': { animation: `${ground} .6s linear infinite` },
        '@media (prefers-reduced-motion: reduce)': {
          '& .dino-jump, & .dino-cactus, & .dino-leg, & .dino-ground': { animation: 'none' },
          '& .dino-cactus': { left: '72%' },
          '& .dino-leg-alt': { opacity: 0 },
        },
      }}>
        <svg aria-hidden="true" viewBox="0 0 80 24" width="26%" height="18%" style={{ position: 'absolute', top: '12%', right: '12%', opacity: .25 }}>
          <path d="M4 20 H74 M17 20 V13 H29 V5 H45 V13 H59 V20" fill="none" stroke="currentColor" strokeWidth="2" />
        </svg>
        <svg className="dino-jump" aria-hidden="true" viewBox="0 0 44 48" preserveAspectRatio="xMinYMax meet" style={{ position: 'absolute', left: '14%', bottom: 18, width: '18%', maxWidth: 64, height: '48%', overflow: 'visible' }}>
          <g fill="currentColor" shapeRendering="crispEdges">
            <path d="M22 2 H42 V6 H44 V22 H30 V26 H36 V30 H32 V28 H28 V34 H24 V38 H12 V34 H8 V30 H4 V26 H0 V14 H4 V22 H8 V26 H12 V22 H16 V18 H22 Z" />
            <path d="M30 6 H34 V10 H30 Z" fill="#fff" />
            <path d="M34 18 H44 V20 H34 Z" fill="#fff" />
            <path className="dino-leg" d="M12 36 H18 V44 H22 V48 H14 V42 H12 Z M22 36 H28 V40 H32 V44 H24 V40 H22 Z" />
            <path className="dino-leg dino-leg-alt" d="M12 36 H18 V40 H22 V44 H14 V40 H12 Z M22 36 H28 V44 H32 V48 H24 V42 H22 Z" />
          </g>
        </svg>
        <svg className="dino-cactus" aria-hidden="true" viewBox="0 0 24 36" preserveAspectRatio="xMinYMax meet" style={{ position: 'absolute', left: '110%', bottom: 18, width: '9%', maxWidth: 30, height: '22%' }}>
          <path d="M10 36 V22 H4 V18 H0 V7 H5 V16 H10 V0 H15 V21 H19 V10 H24 V23 H20 V27 H15 V36 Z" fill="currentColor" shapeRendering="crispEdges" />
        </svg>
        <Box sx={{ position: 'absolute', bottom: 17, left: 0, right: 0, borderTop: '1px solid', borderColor: 'currentColor', opacity: .45 }} />
        <Box className="dino-ground" sx={{ position: 'absolute', bottom: 8, left: 0, right: 0, height: 5, opacity: .3, backgroundImage: 'repeating-linear-gradient(90deg, currentColor 0 5px, transparent 5px 24px)', backgroundSize: '48px 1px', backgroundRepeat: 'repeat-x' }} />
      </Box>
    </Box>
  )
}
