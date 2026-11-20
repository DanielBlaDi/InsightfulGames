import { usePageContext } from 'vike-react/usePageContext';
import MatchPage from '../../../src/multiplayer/MatchPage';

// "/partida/{matchId}": sala de espera y tablero multijugador (ssr: false).
export default function Page() {
  const { routeParams } = usePageContext();
  return <MatchPage key={routeParams.matchId} matchId={routeParams.matchId ?? ''} />;
}
