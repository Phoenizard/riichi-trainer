import { useState } from 'react';
import { useGameSocket } from './hooks/useGameSocket';
import GameInfoBar from './components/GameInfoBar';
import TableArea from './components/TableArea';
import HandArea from './components/HandArea';
import ActionBar from './components/ActionBar';
import CoachPanel from './components/CoachPanel';
import EfficiencyPanel from './components/EfficiencyPanel';
import RoundResultModal from './components/RoundResultModal';
import GameEndOverlay from './components/GameEndOverlay';
import ChatSidebar from './components/ChatSidebar';
import './styles/tiles.css';

function App() {
  const { state, startNewGame, sendAction, continueRound, sendChatMessage, setChatInput } = useGameSocket();
  const [showCoach, setShowCoach] = useState(() => {
    const saved = localStorage.getItem('showCoach');
    return saved !== null ? saved === 'true' : true;
  });

  const toggleCoach = () => {
    setShowCoach(v => {
      const next = !v;
      localStorage.setItem('showCoach', String(next));
      return next;
    });
  };

  // Lobby screen
  if (state.phase === 'lobby') {
    return (
      <div className="lobby">
        <div className="lobby-title">立直麻雀 AI トレーナー</div>
        <div className="lobby-subtitle">Riichi Mahjong AI Trainer</div>
        <button className="lobby-btn" onClick={startNewGame}>
          ゲーム開始
        </button>
      </div>
    );
  }

  const selfMelds = state.gameInfo?.players[0]?.melds || [];

  return (
    <div className="app-layout">
      <div className="app-main">
        {/* Game info bar */}
        {state.gameInfo && <GameInfoBar gameInfo={state.gameInfo} />}

        {/* Table area */}
        {state.gameInfo && (
          <TableArea gameInfo={state.gameInfo} aiThinking={state.aiThinking} />
        )}

        {/* Hand area */}
        <HandArea
          hand={state.hand}
          drawTile={state.drawTile}
          melds={selfMelds}
          availableActions={state.availableActions}
          coach={showCoach ? state.coach : null}
          onDiscard={(tile) => sendAction('discard', tile)}
          onTileRightClick={(tile) => {
            setChatInput(state.chatInput + `[${tile}]`);
          }}
        />

        {/* Action bar */}
        <div style={{ padding: '0 16px' }}>
          <ActionBar
            availableActions={state.availableActions}
            onAction={sendAction}
          />
        </div>

        {/* Coach panel */}
        <CoachPanel
          coach={state.coach}
          visible={showCoach}
          onToggle={toggleCoach}
        />

        {/* Tile efficiency panel */}
        <EfficiencyPanel
          efficiency={state.efficiency}
          shanten={state.efficiencyShanten ?? state.coach?.shanten ?? null}
        />

        {/* Round result modal */}
        {state.phase === 'round_result' && state.roundResult && (
          <RoundResultModal result={state.roundResult} onContinue={continueRound} />
        )}

        {/* Game end overlay */}
        {state.phase === 'game_over' && state.finalScores && (
          <GameEndOverlay scores={state.finalScores} onNewGame={startNewGame} />
        )}
      </div>

      {/* Chat sidebar */}
      <ChatSidebar
        messages={state.chatMessages}
        input={state.chatInput}
        loading={state.chatLoading}
        onSend={sendChatMessage}
        onInputChange={setChatInput}
        gamePhase={state.phase}
      />
    </div>
  );
}

export default App;
