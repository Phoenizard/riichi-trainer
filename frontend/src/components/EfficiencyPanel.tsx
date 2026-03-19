import React, { useState } from 'react';
import Tile from './Tile';
import type { EfficiencyRow } from '../types/game';

interface EfficiencyPanelProps {
  efficiency: EfficiencyRow[] | null;
  shanten: number | null;
}

const EfficiencyPanel: React.FC<EfficiencyPanelProps> = ({ efficiency, shanten }) => {
  const [expanded, setExpanded] = useState(() => {
    const saved = localStorage.getItem('showEfficiency');
    return saved !== null ? saved === 'true' : true;
  });

  const toggle = () => {
    setExpanded(v => {
      const next = !v;
      localStorage.setItem('showEfficiency', String(next));
      return next;
    });
  };

  return (
    <div className="efficiency-panel">
      <div className="efficiency-header" onClick={toggle}>
        <span>牌效率分析</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {shanten !== null && shanten !== undefined && (
            <span className="efficiency-shanten-badge">
              {shanten === -1 ? '聴牌' : `${shanten} 向听`}
            </span>
          )}
          <span>{expanded ? '▾' : '▸'}</span>
        </span>
      </div>
      {expanded && efficiency && efficiency.length > 0 && (
        <div className="efficiency-body">
          <table className="efficiency-table">
            <thead>
              <tr>
                <th style={{ textAlign: 'left' }}>切</th>
                <th style={{ textAlign: 'left' }}>进张</th>
                <th style={{ textAlign: 'right' }}>总进张</th>
                <th style={{ textAlign: 'right' }}>剩余</th>
              </tr>
            </thead>
            <tbody>
              {efficiency.map((row, i) => (
                <tr key={row.discard} className={i === 0 ? 'efficiency-best' : ''}>
                  <td className="efficiency-discard-cell">
                    <Tile tile={row.discard} small />
                  </td>
                  <td className="efficiency-accepts-cell">
                    <div className="efficiency-accepts">
                      {row.accepts.map((t, j) => (
                        <Tile key={j} tile={t} mini />
                      ))}
                    </div>
                  </td>
                  <td className="efficiency-total">{row.total}</td>
                  <td className={`efficiency-remaining ${row.remaining <= 4 ? 'efficiency-low' : ''}`}>
                    {row.remaining}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="efficiency-legend">
            <span>总进张 = 理论最大枚数</span>
            <span>剩余 = 扣除场上可见牌</span>
          </div>
        </div>
      )}
      {expanded && (!efficiency || efficiency.length === 0) && (
        <div className="efficiency-body">
          <div className="efficiency-empty">无可减少向听数的打法</div>
        </div>
      )}
    </div>
  );
};

export default EfficiencyPanel;
