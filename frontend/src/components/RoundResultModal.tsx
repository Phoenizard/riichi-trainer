import React from 'react';
import Tile from './Tile';
import MeldDisplay from './MeldDisplay';
import type { RoundResultData } from '../types/game';

const SEAT_NAMES = ['自家', '下家', '対面', '上家'];
const RESULT_LABELS: Record<string, string> = {
  tsumo: '自摸和了',
  ron: '荣和',
  draw_normal: '流局（荒牌平局）',
  draw_kyuushu: '流局（九种九牌）',
  draw_4riichi: '流局（四家立直）',
  draw_4kan: '流局（四杠散了）',
  draw_4wind: '流局（四风连打）',
};

const YAKU_NAMES: Record<string, string> = {
  'Riichi': '立直',
  'Double Riichi': '两立直',
  'Ippatsu': '一发',
  'Menzen Tsumo': '门前清自摸和',
  'Tanyao': '断幺九',
  'Pinfu': '平和',
  'Iipeiko': '一杯口',
  'Ryanpeikou': '二杯口',
  'Yakuhai (east)': '役牌·东',
  'Yakuhai (south)': '役牌·南',
  'Yakuhai (west)': '役牌·西',
  'Yakuhai (north)': '役牌·北',
  'Yakuhai (wind of round)': '场风牌',
  'Yakuhai (wind of place)': '自风牌',
  'Yakuhai (haku)': '役牌·白',
  'Yakuhai (hatsu)': '役牌·发',
  'Yakuhai (chun)': '役牌·中',
  'Haitei Raoyue': '海底摸月',
  'Houtei Raoyui': '河底捞鱼',
  'Rinshan Kaihou': '岭上开花',
  'Chankan': '抢杠',
  'Chiitoitsu': '七对子',
  'Toitoi': '对对和',
  'San Ankou': '三暗刻',
  'Shou Sangen': '小三元',
  'Honitsu': '混一色',
  'Chinitsu': '清一色',
  'Chantai': '混全带幺九',
  'Junchan': '纯全带幺九',
  'Sanshoku Doujun': '三色同顺',
  'Sanshoku Doukou': '三色同刻',
  'Ittsu': '一气通贯',
  'San Kantsu': '三杠子',
  'Honroutou': '混老头',
  'Nagashi Mangan': '流局满贯',
  'Dora': '宝牌',
  'Aka Dora': '赤宝牌',
  // 役满
  'Kokushi Musou': '国士无双',
  'Suuankou': '四暗刻',
  'Daisangen': '大三元',
  'Shousuushii': '小四喜',
  'Daisuushii': '大四喜',
  'Tsuuiisou': '字一色',
  'Chinroutou': '清老头',
  'Ryuuiisou': '绿一色',
  'Chuuren Poutou': '九莲宝灯',
  'Suu Kantsu': '四杠子',
  'Tenhou': '天和',
  'Chiihou': '地和',
  'Renhou': '人和',
};

interface RoundResultModalProps {
  result: RoundResultData;
  onContinue: () => void;
}

const RoundResultModal: React.FC<RoundResultModalProps> = ({ result, onContinue }) => {
  const { winner, han, fu, yaku, score_deltas, scores, winning_hand, winning_melds, tenpai_hands } = result;
  const resultLabel = RESULT_LABELS[result.result] || result.result;
  const isDraw = result.result.startsWith('draw');

  return (
    <div className="modal-overlay">
      <div className="modal-content">
        <div className="modal-title">{resultLabel}</div>

        {winner >= 0 && (
          <div>
            <strong>{SEAT_NAMES[winner]}</strong> 和了
          </div>
        )}

        {/* Winning hand */}
        {winning_hand && winning_hand.length > 0 && (
          <div style={{ margin: '12px 0', display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'flex-end' }}>
            {winning_hand.map((tile, i) => (
              <Tile key={i} tile={tile} small />
            ))}
          </div>
        )}
        {winning_melds && winning_melds.length > 0 && (
          <MeldDisplay melds={winning_melds} small ownerSeat={winner} />
        )}

        {han > 0 && (
          <div style={{ fontSize: 18, fontWeight: 700, margin: '8px 0' }}>
            {han}翻 {fu}符
          </div>
        )}

        {yaku && yaku.length > 0 && (
          <div className="modal-yaku">
            役: {yaku.map(y => YAKU_NAMES[y] || y).join('、')}
          </div>
        )}

        {/* Tenpai hands on draw */}
        {isDraw && tenpai_hands && Object.keys(tenpai_hands).length > 0 && (
          <div className="tenpai-section">
            <div className="tenpai-title">听牌</div>
            {[0, 1, 2, 3].filter(i => tenpai_hands[String(i)]).map(i => {
              const data = tenpai_hands[String(i)];
              return (
                <div key={i} className="tenpai-player">
                  <div className="tenpai-player-name">{SEAT_NAMES[i]}</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'flex-end' }}>
                    {data.hand.map((tile, j) => (
                      <Tile key={j} tile={tile} small />
                    ))}
                  </div>
                  {data.melds && data.melds.length > 0 && (
                    <MeldDisplay melds={data.melds} small ownerSeat={i} />
                  )}
                </div>
              );
            })}
          </div>
        )}

        <div className="modal-scores">
          {score_deltas.map((delta, i) => {
            const sign = delta >= 0 ? '+' : '';
            const cls = delta > 0 ? 'score-positive' : delta < 0 ? 'score-negative' : '';
            return (
              <div key={i} className="modal-score-row">
                <span>{SEAT_NAMES[i]}</span>
                <span className={cls}>{sign}{delta}</span>
                <span>→ {scores[i]}点</span>
              </div>
            );
          })}
        </div>

        {result.round_stats && result.round_stats.total > 0 && (
          <div className="modal-stats">
            AI 一致率: {result.round_stats.matches}/{result.round_stats.total}
            ({Math.round(result.round_stats.agreement_rate * 100)}%)
          </div>
        )}

        <button className="modal-btn" onClick={onContinue}>
          続行
        </button>
      </div>
    </div>
  );
};

export default RoundResultModal;
