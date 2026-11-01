import GamePage from './GamePage';
import { useGameSocket } from './useGameSocket';

interface GameScreenProps {
  gameId: string; // devuelto por POST /api/games
  onUnauthorized?: () => void;
  /** Si se pasa, la pantalla ofrece salir de la partida (por ejemplo, para configurar otra). */
  onExit?: () => void;
}

function ConnectedGame({ gameId, onUnauthorized, onExit }: GameScreenProps) {
  const session = useGameSocket({ gameId });
  return <GamePage session={session} onUnauthorized={onUnauthorized} onExit={onExit} />;
}

/** Punto de entrada para integrar la partida: conecta con el Gateway y pinta la pantalla. */
export default function GameScreen(props: GameScreenProps) {
  // key: una partida distinta no hereda orientación ni confirmaciones de la anterior.
  return <ConnectedGame key={props.gameId} {...props} />;
}
