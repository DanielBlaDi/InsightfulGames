import { useData } from 'vike-react/useData';
import AccountNav from '../../src/components/AccountNav';
import StatsView from '../../src/stats/StatsView';
import type { Data } from './+data';

export default function Page() {
  return (
    <>
      <AccountNav current="estadisticas" />
      <StatsView data={useData<Data>()} />
    </>
  );
}
