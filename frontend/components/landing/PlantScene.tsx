import { forwardRef } from 'react';
import { Box, Cylinder, Face, Label, Legs, Quad, Sheet, VIEWBOX, project, pts } from './sceneKit';

/* An isometric manufacturing floor: systems of record, a bioreactor, an investigation desk, a freeze dryer with a
 * model forecast, a review board, a QC bench and a partner delivery dock. Plain SVG so the camera can move freely. */

export const STATIONS = {
  overview: [300, 300, 70],
  connect: [55, 210, 95],
  monitor: [250, 215, 105],
  investigate: [370, 345, 100],
  predict: [540, 255, 150],
  act: [430, 22, 105],
  partners: [150, 480, 45],
} as const;

const ROUTE: [number, number][] = [[118, 520], [118, 420], [104, 372], [104, 110], [150, 110], [150, 300], [292, 300], [292, 430], [458, 430], [458, 306], [624, 306], [624, 448]];

function Trend({ w, h, data, color = '#0e7490', markAt }: { w: number; h: number; data: number[]; color?: string; markAt?: number }) {
  const step = w / (data.length - 1);
  const line = data.map((v, i) => `${(i * step).toFixed(1)},${(h - v * h).toFixed(1)}`).join(' ');
  return (
    <g>
      <polyline points={line} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" />
      {markAt !== undefined && <circle cx={markAt * step} cy={h - data[markAt] * h} r={3} fill="#dc2626" />}
    </g>
  );
}

export const PlantScene = forwardRef<SVGGElement, { className?: string; initial: string }>(function PlantScene({ className, initial }, cameraRef) {
  const route = ROUTE.map(([x, y]) => project(x, y, 0.5).map(n => n.toFixed(1)).join(',')).join(' ');
  return (
    <svg viewBox={`${VIEWBOX.x} ${VIEWBOX.y} ${VIEWBOX.w} ${VIEWBOX.h}`} className={className} role="img" aria-label="Illustration of a manufacturing floor: plant systems, a bioreactor, an investigation desk, a freeze dryer with a model forecast, a review board, a QC bench and a partner delivery dock, linked by a data route.">
      <g ref={cameraRef} transform={initial}>
        {/* floor */}
        <Box x={-10} y={-10} z={-10} w={660} d={660} h={10} tone="light" />
        {[80, 160, 240, 320, 400, 480, 560].map(v => (
          <g key={v} stroke="#d3d1cb" strokeWidth={0.6}>
            <polyline fill="none" points={pts([[v, -10, 0], [v, 650, 0]])} />
            <polyline fill="none" points={pts([[-10, v, 0], [650, v, 0]])} />
          </g>
        ))}
        <g stroke="#7d7b76" strokeWidth={1.2} fill="none">
          <polyline points={pts([[10, 40, 0], [10, 10, 0], [40, 10, 0]])} />
          <polyline points={pts([[600, 630, 0], [630, 630, 0], [630, 600, 0]])} />
        </g>

        {/* data route, drawn in as the tour advances */}
        <polyline points={route} fill="none" stroke="#b9e3ea" strokeWidth={7} strokeLinejoin="round" strokeLinecap="round" opacity={0.55} />
        <polyline points={route} pathLength={1} fill="none" stroke="#0e7490" strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" strokeDasharray="1 1" style={{ strokeDashoffset: 'var(--route, 1)' }} />

        {/* review board on the back wall */}
        <Box x={300} y={12} w={262} d={14} h={196} tone="light" />
        <Quad face="left" at={26} a0={310} a1={552} b0={16} b1={198} fill="#f7f7f5" stroke="#bdbbb5" />
        <Face face="left" x={310} y={26} z={198}>
          <Label x={12} y={18} size={9} fill="#42413e">PROPOSAL · SIGNATURES REQUIRED</Label>
          {[0, 1, 2, 3].map(i => <rect key={i} x={12} y={32 + i * 13} width={[190, 160, 175, 120][i]} height={5} fill="#d6d4cf" />)}
          <rect x={12} y={92} width={104} height={58} fill="#ecf8fa" stroke="#5fb7c4" />
          <Label x={20} y={108} size={7.5} fill="#0e6f86">MSAT</Label>
          <path d="M22,132 q10,-12 20,0 t20,-2 t18,2" fill="none" stroke="#0e7490" strokeWidth={1.6} />
          <rect x={126} y={92} width={104} height={58} fill="#ffffff" stroke="#d9a441" strokeDasharray="4 3" />
          <Label x={134} y={108} size={7.5} fill="#a16207">QA · PENDING</Label>
        </Face>

        {/* systems of record */}
        {['MES', 'PI', 'LIMS', 'QMS'].map((name, i) => {
          const y = 96 + i * 58;
          return (
            <g key={name}>
              <Box x={16} y={y} w={72} d={54} h={162} tone="dark" />
              <Face face="right" x={88} y={y + 54} z={162}>
                <Label x={8} y={18} size={9} fill="#e7e6e2">{name}</Label>
                {[0, 1, 2, 3, 4].map(j => <rect key={j} x={8} y={30 + j * 14} width={38} height={6} fill="#3b3a37" stroke="#262523" strokeWidth={0.5} />)}
                <rect x={8} y={110} width={38} height={3} fill="#5fb7c4" />
                <circle cx={44} cy={14} r={2.2} fill="#5fb7c4" />
              </Face>
            </g>
          );
        })}

        {/* bioreactor on its skid, with a local HMI */}
        <Box x={168} y={150} w={134} d={134} h={14} tone="mid" />
        <Box x={176} y={240} z={14} w={10} d={10} h={70} tone="dark" />
        <Cylinder cx={235} cy={215} z={14} r={50} h={150} id="lp-vessel" />
        <Box x={226} y={206} z={164} w={20} d={20} h={26} tone="dark" />
        <Cylinder cx={236} cy={216} z={190} r={7} h={8} id="lp-motor" dark top="#5b5955" />
        <Box x={190} y={168} z={140} w={60} d={6} h={6} tone="light" />
        {(() => { const [sx, sy] = project(266, 258, 100); return <g><rect x={sx - 2} y={sy - 6} width={44} height={14} rx={2} fill="#2f2e2c" /><text x={sx + 4} y={sy + 4} fontSize={8} fill="#e7e6e2" fontFamily="var(--font-inter), Inter, sans-serif" fontWeight={600}>BR-UP-01</text></g>; })()}
        <Box x={308} y={196} w={66} d={8} h={118} tone="dark" />
        <Face face="left" x={312} y={204} z={112}>
          <rect x={0} y={0} width={58} height={44} fill="#0f2c33" />
          <g transform="translate(5 8)"><Trend w={48} h={28} data={[0.7, 0.72, 0.71, 0.73, 0.72, 0.74, 0.73, 0.72, 0.5, 0.42, 0.45]} color="#5fb7c4" markAt={8} /></g>
        </Face>

        {/* investigation desk */}
        <Legs x={300} y={300} w={150} d={108} h={70} />
        <Box x={296} y={296} z={70} w={158} d={116} h={10} tone="light" />
        <Box x={318} y={312} z={80} w={96} d={6} h={58} tone="dark" />
        <Face face="left" x={322} y={318} z={134}>
          <rect x={0} y={0} width={88} height={50} fill="#f4fbfc" />
          {[0, 1, 2].map(i => <line key={i} x1={4} x2={84} y1={12 + i * 14} y2={12 + i * 14} stroke="#d6e3e6" strokeWidth={0.6} />)}
          <g transform="translate(4 4)"><Trend w={80} h={10} data={[0.6, 0.62, 0.6, 0.63, 0.61, 0.62, 0.95, 0.9, 0.7]} color="#dc2626" /></g>
          <g transform="translate(4 18)"><Trend w={80} h={10} data={[0.7, 0.7, 0.71, 0.7, 0.72, 0.7, 0.3, 0.25, 0.3]} color="#0e7490" /></g>
          <g transform="translate(4 32)"><Trend w={80} h={10} data={[0.5, 0.52, 0.5, 0.51, 0.5, 0.5, 0.51, 0.5, 0.5]} color="#82807b" /></g>
          <line x1={64} x2={64} y1={2} y2={48} stroke="#0b1e22" strokeWidth={0.8} strokeDasharray="2 2" />
        </Face>
        <Box x={346} y={318} z={80} w={40} d={30} h={2} tone="dark" />
        <Sheet x={340} y={356} z={80} w={50} d={36} tag="SOP" tagFill="#82807b" />
        <Sheet x={396} y={340} z={80} w={50} d={36} tag="WO" tagFill="#42413e" />
        <Sheet x={398} y={372} z={82} w={44} d={32} tag="LIMS" />

        {/* freeze dryer with a floating primary-drying forecast */}
        <Box x={470} y={120} w={80} d={30} h={120} tone="mid" />
        <Box x={468} y={150} w={146} d={120} h={162} tone="light" />
        <Face face="left" x={468} y={270} z={162}>
          <circle cx={64} cy={86} r={48} fill="#cfd1d1" stroke="#8f8d88" />
          <circle cx={64} cy={86} r={38} fill="#2b3a3e" stroke="#1b2729" />
          <path d="M40,66 a34,34 0 0 1 30,-16" fill="none" stroke="#7fb9c4" strokeWidth={2} opacity={0.7} />
          <rect x={118} y={22} width={22} height={34} fill="#0f2c33" />
          <rect x={121} y={27} width={16} height={3} fill="#5fb7c4" />
          <rect x={121} y={34} width={10} height={3} fill="#2b5f6b" />
        </Face>
        <polyline points={pts([[540, 306, 176], [540, 288, 168], [540, 270, 150]])} fill="none" stroke="#0e7490" strokeWidth={1.2} strokeDasharray="3 3" />
        <Face face="left" x={470} y={306} z={292}>
          <rect x={0} y={0} width={150} height={112} fill="rgba(255,255,255,0.9)" stroke="#0e7490" strokeWidth={1.2} />
          <Label x={10} y={16} size={7.5} fill="#0e6f86">PRIMARY DRYING MODEL</Label>
          <line x1={10} x2={140} y1={44} y2={44} stroke="#d9a441" strokeWidth={1.2} strokeDasharray="4 3" />
          <Label x={104} y={40} size={6} fill="#a16207" weight={500}>vapor limit</Label>
          <path d="M10,96 C40,30 70,30 100,58 S130,90 140,96" fill="none" stroke="#c2410c" strokeWidth={1.6} />
          <path d="M10,98 C44,58 76,52 104,68 S132,92 140,98" fill="none" stroke="#0e7490" strokeWidth={2} />
          <path d="M10,98 C44,50 76,44 104,62 S132,90 140,98 L140,102 C132,96 104,76 76,62 C44,66 10,100 10,100 Z" fill="#0e7490" opacity={0.12} />
          <line x1={10} x2={140} y1={102} y2={102} stroke="#bdbbb5" strokeWidth={0.8} />
        </Face>

        {/* partner delivery dock */}
        <Box x={56} y={468} w={118} d={92} h={74} tone="crate" />
        <Quad face="top" at={74} a0={56} a1={174} b0={509} b1={519} fill="#0e7490" />
        <Quad face="left" at={560} a0={76} a1={150} b0={22} b1={52} fill="#f3efe7" stroke="#a39c8e" />
        <Face face="left" x={84} y={560} z={42}><Label x={0} y={0} size={10} fill="#42413e">CMO · OCT</Label></Face>
        <Sheet x={84} y={476} z={74} w={52} d={36} tag="ZIP" tagFill="#42413e" />
        <Box x={196} y={500} w={70} d={56} h={40} tone="crate" />
        <Sheet x={206} y={508} z={40} w={46} d={34} tag="CoA" tagFill="#82807b" />

        {/* QC bench with HPLC and samples */}
        <Legs x={452} y={462} w={160} d={84} h={66} />
        <Box x={448} y={458} z={66} w={168} d={92} h={10} tone="light" />
        <Box x={462} y={468} z={76} w={56} d={46} h={46} tone="paper" />
        <Quad face="left" at={514} a0={470} a1={510} b0={96} b1={114} fill="#0f2c33" />
        {[0, 1, 2].map(r => [0, 1, 2, 3].map(c => (
          <g key={`${r}-${c}`}>
            <Cylinder cx={540 + c * 16} cy={478 + r * 18} z={76} r={5} h={16} id={`lp-vial-${r}-${c}`} />
            <Cylinder cx={540 + c * 16} cy={478 + r * 18} z={92} r={5} h={4} id={`lp-cap-${r}-${c}`} dark={false} top={r === 1 && c === 2 ? '#d9a441' : '#0e7490'} />
          </g>
        )))}
      </g>
    </svg>
  );
});
