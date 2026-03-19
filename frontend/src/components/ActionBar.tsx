import React, { useState } from 'react';
import Tile from './Tile';
import type { ActionOption } from '../types/game';

interface ActionBarProps {
  availableActions: ActionOption[] | null;
  onAction: (actionType: string, tile?: string, meldTiles?: string[]) => void;
}

const ACTION_LABELS: Record<string, string> = {
  tsumo: 'ツモ',
  ron: 'ロン',
  riichi: '立直',
  chi: '吃',
  pon: '碰',
  kan: '杠',
  skip: '跳过',
  kyuushu: '九种九牌',
};

const ActionBar: React.FC<ActionBarProps> = ({ availableActions, onAction }) => {
  const [showChiOptions, setShowChiOptions] = useState(false);

  if (!availableActions || availableActions.length === 0) return null;

  // Filter out discard actions (handled by tile clicking)
  const specialActions = availableActions.filter(a => a.type !== 'discard');
  if (specialActions.length === 0) return null;

  // Group chi actions (may have multiple options)
  const chiActions = specialActions.filter(a => a.type === 'chi');
  const otherActions = specialActions.filter(a => a.type !== 'chi');

  const btnClass = (type: string) => {
    const base = 'action-btn';
    if (type === 'tsumo' || type === 'ron') return `${base} action-btn-tsumo`;
    if (type === 'riichi') return `${base} action-btn-riichi`;
    if (type === 'pon' || type === 'chi' || type === 'kan') return `${base} action-btn-call`;
    if (type === 'skip') return `${base} action-btn-skip`;
    return base;
  };

  return (
    <div className="action-bar">
      {/* Win actions first */}
      {otherActions.filter(a => a.type === 'tsumo' || a.type === 'ron').map((a, i) => (
        <button key={`win-${i}`} className={btnClass(a.type)} onClick={() => onAction(a.type, a.tile)}>
          {ACTION_LABELS[a.type] || a.type}
        </button>
      ))}

      {/* Riichi */}
      {otherActions.filter(a => a.type === 'riichi').map((a, i) => (
        <button key={`riichi-${i}`} className={btnClass(a.type)} onClick={() => onAction(a.type, a.tile)}>
          {ACTION_LABELS[a.type]} → {a.tile && <Tile tile={a.tile} small />}
        </button>
      ))}

      {/* Chi */}
      {chiActions.length === 1 && (
        <button className={btnClass('chi')} onClick={() => onAction('chi', chiActions[0].tile, chiActions[0].meld_tiles)}>
          {ACTION_LABELS.chi} {chiActions[0].meld_tiles?.map((t, j) => <Tile key={j} tile={t} small />)}
        </button>
      )}
      {chiActions.length > 1 && (
        <div style={{ position: 'relative' }}>
          <button className={btnClass('chi')} onClick={() => setShowChiOptions(!showChiOptions)}>
            {ACTION_LABELS.chi} ▾
          </button>
          {showChiOptions && (
            <div style={{
              position: 'absolute', bottom: '100%', left: 0, background: '#fff',
              border: '1px solid #ccc', borderRadius: 4, padding: 4, zIndex: 10,
              display: 'flex', flexDirection: 'column', gap: 4,
            }}>
              {chiActions.map((a, i) => (
                <button
                  key={i}
                  className="action-btn action-btn-chi-option"
                  onClick={() => { onAction('chi', a.tile, a.meld_tiles); setShowChiOptions(false); }}
                >
                  {a.meld_tiles?.map((t, j) => <Tile key={j} tile={t} small />)}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Pon / Kan */}
      {otherActions.filter(a => a.type === 'pon' || a.type === 'kan').map((a, i) => (
        <button key={`call-${i}`} className={btnClass(a.type)} onClick={() => onAction(a.type, a.tile)}>
          {ACTION_LABELS[a.type] || a.type} {a.tile && <Tile tile={a.tile} small />}
        </button>
      ))}

      {/* Kyuushu */}
      {otherActions.filter(a => a.type === 'kyuushu').map((a, i) => (
        <button key={`kyu-${i}`} className={btnClass(a.type)} onClick={() => onAction(a.type)}>
          {ACTION_LABELS[a.type]}
        </button>
      ))}

      {/* Skip (always last) */}
      {otherActions.filter(a => a.type === 'skip').map((a, i) => (
        <button key={`skip-${i}`} className={btnClass(a.type)} onClick={() => onAction(a.type)}>
          {ACTION_LABELS[a.type]}
        </button>
      ))}
    </div>
  );
};

export default ActionBar;
