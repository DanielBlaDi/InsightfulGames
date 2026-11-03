import { lazy, Suspense } from 'react';

// import.meta.env.DEV es constante en el build: en producción la importación desaparece.
const DevHarness = import.meta.env.DEV ? lazy(() => import('../../src/game/mock/DevHarness')) : null;

export default function Page() {
  return DevHarness ? (
    <Suspense>
      <DevHarness />
    </Suspense>
  ) : null;
}
