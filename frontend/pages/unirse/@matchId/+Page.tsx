import { usePageContext } from 'vike-react/usePageContext';
import JoinMatchPage from '../../../src/multiplayer/JoinMatchPage';

// "/unirse/{matchId}": enlace de invitación (ssr: false).
export default function Page() {
  const { routeParams } = usePageContext();
  return <JoinMatchPage key={routeParams.matchId} matchId={routeParams.matchId ?? ''} />;
}
