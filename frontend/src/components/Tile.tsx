import React from 'react';

const SUIT_LABELS: Record<string, string> = { m: '万', p: '筒', s: '索' };
const HONOR_LABELS: Record<string, string> = {
  E: '東', S: '南', W: '西', N: '北',
  P: '白', F: '發', C: '中',
};

function parseTile(tile: string): { number: string; suit: string; suitClass: string; isHonor: boolean; isRed: boolean } {
  // Honor tiles: single letter
  if (tile.length === 1 && HONOR_LABELS[tile]) {
    const dragonClass = 'PFC'.includes(tile) ? `tile-dragon-${tile}` : 'tile-wind';
    return { number: HONOR_LABELS[tile], suit: '', suitClass: dragonClass, isHonor: true, isRed: false };
  }
  // Suited tiles: "1m", "0p" etc.
  const num = tile[0];
  const s = tile[tile.length - 1];
  const isRed = num === '0';
  const displayNum = isRed ? '5' : num;
  const suitClass = `tile-${s === 'm' ? 'man' : s === 'p' ? 'pin' : 'sou'}`;
  return { number: displayNum, suit: SUIT_LABELS[s] || '', suitClass, isHonor: false, isRed };
}

interface TileProps {
  tile: string;
  onClick?: () => void;
  clickable?: boolean;
  recommended?: boolean;
  faceDown?: boolean;
  small?: boolean;
  sideways?: boolean;
}

const Tile: React.FC<TileProps> = ({ tile, onClick, clickable, recommended, faceDown, small, sideways }) => {
  if (faceDown) {
    return (
      <div className={`tile tile-back ${small ? 'tile-small' : ''} ${sideways ? 'tile-sideways' : ''}`} />
    );
  }

  const { number, suit, suitClass, isHonor, isRed } = parseTile(tile);

  const classes = [
    'tile',
    suitClass,
    isRed && 'tile-red',
    clickable && 'tile-clickable',
    recommended && 'tile-recommended',
    small && 'tile-small',
    sideways && 'tile-sideways',
  ].filter(Boolean).join(' ');

  return (
    <div className={classes} onClick={clickable ? onClick : undefined}>
      {isHonor ? (
        <span className="tile-honor">{number}</span>
      ) : (
        <>
          <span className="tile-number">{number}</span>
          <span className="tile-suit">{suit}</span>
        </>
      )}
    </div>
  );
};

export default Tile;
