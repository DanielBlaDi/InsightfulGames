import { usePageContext } from 'vike-react/usePageContext';

export default function Page() {
  const { is404 } = usePageContext();
  return (
    <main className="min-h-screen flex flex-col items-center justify-center gap-space-sm px-gutter-mobile text-center">
      <h1 className="font-headline-lg text-headline-lg">{is404 ? 'Página no encontrada' : 'Algo salió mal'}</h1>
      <a href="/" className="font-label-lg text-label-lg text-primary underline">
        Volver al inicio
      </a>
    </main>
  );
}
