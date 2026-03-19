import React from 'react';
import Tile from './Tile';
import type { CoachAnalysis } from '../types/game';

const ACTION_LABELS: Record<string, string> = {
  none: '跳过',
  pon: '碰',
  chi: '吃',
  hora: '和了',
  reach: '立直',
  daiminkan: '杠',
  ankan: '暗杠',
  kakan: '加杠',
};

interface CoachPanelProps {
  coach: CoachAnalysis | null;
  visible: boolean;
  onToggle: () => void;
}

const CoachPanel: React.FC<CoachPanelProps> = ({ coach, visible, onToggle }) => {
  const isDiscard = coach?.recommended_action === 'dahai';
  const maxScore = coach?.candidates && coach.candidates.length > 0 ? coach.candidates[0].score : 1;

  return (
    <div className="coach-panel">
      <div className="coach-header" onClick={onToggle}>
        <span>AI 教练 {visible ? '▾' : '▸'}</span>
        {coach && <span>向听: {coach.shanten === -1 ? '聴牌' : coach.shanten}</span>}
      </div>
      {visible && coach && (
        <div className="coach-body">
          <div className="coach-recommend">
            <span>推荐:</span>
            {isDiscard && coach.recommended ? (
              <Tile tile={coach.recommended} recommended />
            ) : coach.recommended_action === 'reach' && coach.recommended ? (
              <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                <span style={{ fontWeight: 700, fontSize: 16 }}>立直 →</span>
                <Tile tile={coach.recommended} small recommended />
              </span>
            ) : (
              <span style={{ fontWeight: 700, fontSize: 16 }}>
                {ACTION_LABELS[coach.recommended_action] || coach.recommended_action}
              </span>
            )}
          </div>
          {coach.candidates.length > 0 && (
            <div className="coach-candidates">
              {coach.candidates.slice(0, 5).map((c, i) => (
                <div key={i} className="coach-candidate">
                  <Tile tile={c.tile} small />
                  <div style={{ width: 60 }}>
                    <div
                      className="coach-score-bar"
                      style={{ width: `${(c.score / maxScore) * 100}%` }}
                    />
                    <span style={{ fontSize: 10 }}>{c.score.toFixed(2)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default CoachPanel;
