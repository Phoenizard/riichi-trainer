import React from 'react';
import Tile from './Tile';
import MeldDisplay from './MeldDisplay';
import type { ActionOption, MeldView, CoachAnalysis } from '../types/game';

interface HandAreaProps {
  hand: string[];
  drawTile: string | null;
  melds: MeldView[];
  availableActions: ActionOption[] | null;
  coach: CoachAnalysis | null;
  onDiscard: (tile: string) => void;
  onTileRightClick?: (tile: string) => void;
}

const HandArea: React.FC<HandAreaProps> = ({ hand, drawTile, melds, availableActions, coach, onDiscard, onTileRightClick }) => {
  // Which tiles can be discarded?
  const discardableTiles = new Set<string>();
  if (availableActions) {
    for (const a of availableActions) {
      if (a.type === 'discard' && a.tile) {
        discardableTiles.add(a.tile);
      }
    }
  }

  const canDiscard = discardableTiles.size > 0;
  const recommended = coach?.recommended || '';
  const hasCallAction = availableActions?.some(a => a.type === 'chi' || a.type === 'pon' || a.type === 'kan') ?? false;

  const handleContextMenu = (e: React.MouseEvent, tile: string) => {
    e.preventDefault();
    onTileRightClick?.(tile);
  };

  return (
    <div className={`hand-area${hasCallAction ? ' hand-area-call-available' : ''}`}>
      <div className="hand-tiles">
        {hand.map((tile, i) => (
          <div
            key={`h-${i}`}
            onContextMenu={(e) => handleContextMenu(e, tile)}
            style={{ display: 'inline-flex' }}
          >
            <Tile
              tile={tile}
              clickable={canDiscard && discardableTiles.has(tile)}
              recommended={tile === recommended}
              onClick={() => onDiscard(tile)}
            />
          </div>
        ))}
        {drawTile && (
          <div className="draw-tile-gap" onContextMenu={(e) => handleContextMenu(e, drawTile)}>
            <Tile
              key="draw"
              tile={drawTile}
              clickable={canDiscard && discardableTiles.has(drawTile)}
              recommended={drawTile === recommended}
              onClick={() => onDiscard(drawTile)}
            />
          </div>
        )}
      </div>
      <MeldDisplay melds={melds} small={false} ownerSeat={0} />
    </div>
  );
};

export default HandArea;
