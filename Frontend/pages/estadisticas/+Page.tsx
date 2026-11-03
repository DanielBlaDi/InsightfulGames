import { useData } from 'vike-react/useData';
import StatsView from '../../src/stats/StatsView';
import type { Data } from './+data';

export default function Page() {
  return <StatsView data={useData<Data>()} />;
}
