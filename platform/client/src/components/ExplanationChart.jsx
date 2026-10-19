import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis, ReferenceLine } from 'recharts';

// Shared explainability widget: horizontal bars of feature contributions (e.g. SHAP values).
// Positive impact pushes the prediction up, negative pulls it down.
export default function ExplanationChart({ items = [] }) {
  if (!items.length) return null;
  const data = [...items].sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact)).slice(0, 8);
  const height = 28 * data.length + 24;

  return (
    <figure className="explanation">
      <figcaption>Why: feature contributions</figcaption>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, bottom: 0, left: 8 }}>
          <XAxis type="number" hide domain={['auto', 'auto']} />
          <YAxis type="category" dataKey="feature" width={170} tick={{ fontSize: 12, fill: 'var(--text-muted)' }} axisLine={false} tickLine={false} />
          <ReferenceLine x={0} stroke="var(--border-strong)" />
          <Tooltip
            cursor={{ fill: 'var(--surface-hover)' }}
            formatter={(v, _n, p) => [`${Number(v).toFixed(3)}${p.payload.value !== undefined ? `  (value: ${JSON.stringify(p.payload.value)})` : ''}`, 'impact']}
            contentStyle={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
          />
          <Bar dataKey="impact" radius={[0, 3, 3, 0]} barSize={14}>
            {data.map((d) => (
              <Cell key={d.feature} fill={d.impact >= 0 ? 'var(--positive)' : 'var(--negative)'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
