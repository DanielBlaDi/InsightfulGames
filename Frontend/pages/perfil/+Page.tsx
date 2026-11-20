import ProfilePage from '../../src/profile/ProfilePage';

// "/perfil": aplicación de una sola página (ssr: false, valor común). Los datos se piden en el
// navegador a GET /api/profile/me con la cookie de sesión.
export default function Page() {
  return <ProfilePage />;
}
