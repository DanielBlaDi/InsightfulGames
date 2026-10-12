import React, { useState, type FormEvent } from 'react';

interface LoginProps {
  onLoginSuccess: (token: string, user: { userId: string; username: string }) => void;
  onBack: () => void;
}

interface AuthResponse {
  accessToken: string;
  expiresIn: number;
  user: {
    userId: string;
    username: string;
  };
}

const FIELD_NAMES: Record<string, string> = {
  password: 'Contraseña',
  username: 'Usuario',
  email: 'Correo electrónico',
  fullName: 'Nombre de usuario',
  confirmPassword: 'Confirmar contraseña',
};

const MSG_TRANSLATIONS: Record<string, string> = {
  'String should have at least 8 characters': 'La contraseña debe tener al menos 8 caracteres',
  'String should have at least 1 character': 'La cadena debe tener al menos 1 carácter',
  'String should have at most 100 characters': 'La cadena debe tener como máximo 100 caracteres',
  'Field required': 'Campo requerido',
  'value is not a valid email address': 'No es una dirección de correo válida',
  'Input should be a valid email': 'No es una dirección de correo válida',
  'value is not a valid integer': 'Debe ser un número entero',
  'value is not a valid string': 'Cadena no válida',
};

function translateMessage(msg: string): string {
  return MSG_TRANSLATIONS[msg] || msg;
}

function formatValidationItem(item: unknown): string {
  if (!item || typeof item !== 'object') return '';
  const it = item as Record<string, unknown>;
  const loc = Array.isArray(it.loc) ? it.loc.map(String) : [];
  const field = loc.length ? loc[loc.length - 1] : '';
  const msg = typeof it.msg === 'string' ? it.msg : '';
  const fieldLabel = field && FIELD_NAMES[field] ? FIELD_NAMES[field] : field;
  const translated = msg ? translateMessage(msg) : '';
  if (fieldLabel && translated) return `${fieldLabel}: ${translated}`;
  return translated || fieldLabel || '';
}

/**
 * Extrae un mensaje legible del cuerpo de un error HTTP.
 * Soporta la forma del contrato `{ error: { code, message } }` y la forma
 * de validación de FastAPI/Pydantic `{ detail: [ { type, loc, msg }, ... ] }`.
 */
function parseErrorMessage(data: unknown, fallback: string): string {
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;

    // Contrato: { error: { code, message } }
    if (obj.error && typeof obj.error === 'object') {
      const err = obj.error as Record<string, unknown>;
      if (typeof err.message === 'string' && err.message) {
        return err.message;
      }
    }

    // FastAPI/Pydantic: { detail: [ ... ] }
    if (Array.isArray(obj.detail)) {
      const messages = obj.detail
        .map((item) => formatValidationItem(item))
        .filter(Boolean) as string[];
      if (messages.length > 0) {
        return messages.join(' ');
      }
    }
  }
  return fallback;
}

interface LoginForm {
  username: string;
  password: string;
}

interface SignupForm {
  fullName: string;
  email: string;
  password: string;
  confirmPassword: string;
}

export default function Login({ onLoginSuccess, onBack }: LoginProps) {
  const [tab, setTab] = useState<'login' | 'signup'>('login');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [loginForm, setLoginForm] = useState<LoginForm>({ username: '', password: '' });
  const [signupForm, setSignupForm] = useState<SignupForm>({
    fullName: '',
    email: '',
    password: '',
    confirmPassword: '',
  });

  const API_BASE = '/api';

  const handleLoginInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    setLoginForm({ ...loginForm, [e.target.name]: e.target.value });
  };

  const handleSignupInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    const { name, value } = e.target;
    setSignupForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleLogin = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: loginForm.username,
          password: loginForm.password,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(parseErrorMessage(data, 'Credenciales inválidas'));
      }

      const authData = data as AuthResponse;
      onLoginSuccess(authData.accessToken, authData.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al iniciar sesión');
    } finally {
      setLoading(false);
    }
  };

  const handleSignup = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    if (signupForm.password !== signupForm.confirmPassword) {
      setError('Las contraseñas no coinciden');
      setLoading(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/auth/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: signupForm.fullName,
          password: signupForm.password,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(parseErrorMessage(data, 'Error al registrarse'));
      }

      // Login automático tras registrarse
      const loginRes = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: signupForm.fullName,
          password: signupForm.password,
        }),
      });

      const loginData = await loginRes.json();

      if (!loginRes.ok) {
        throw new Error(parseErrorMessage(loginData, 'Registro OK pero fallo al iniciar sesión'));
      }

      onLoginSuccess(loginData.accessToken, loginData.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error al crear cuenta');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F9F6F0] text-[#231D19] font-sans antialiased overflow-x-hidden relative">
      {/* Ambient gradients */}
      <div className="fixed inset-0 pointer-events-none overflow-hidden z-0">
        <div className="absolute -top-32 left-1/3 w-[650px] h-[400px] bg-[#EADCC8]/60 blur-[130px] rounded-full"></div>
        <div className="absolute top-1/2 -right-24 w-[500px] h-[450px] bg-[#F1D7C6]/40 blur-[140px] rounded-full"></div>
        <div className="absolute -bottom-24 left-10 w-[550px] h-[350px] bg-[#E6DEC8]/50 blur-[120px] rounded-full"></div>
        <div className="absolute inset-0 opacity-[0.025] bg-[radial-gradient(#8c7169_1px,transparent_1px)] bg-[size:24px_24px]"></div>
      </div>

      <header className="relative z-10 w-full max-w-7xl mx-auto px-6 py-6 flex items-center justify-between">
        <button
          onClick={onBack}
          className="p-2 rounded-lg hover:bg-white/50 transition-colors"
          aria-label="Volver"
        >
          <span className="material-symbols-outlined text-[24px]">arrow_back</span>
        </button>
        <a href="#" aria-label="Insightful Games Home" className="inline-block hover:scale-[1.01] transition-transform">
          <img
            alt="Insightful Games"
            className="h-9 sm:h-10 w-auto object-contain rounded-md"
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuDLpjEJMqcoHj5kyHCd_den9mRKN0NrinrcNxjKJbXDL9aI6XGvJyoJpT3uUv8gj-sQMchrdLD9pStCkMaJ0_TT4nESDQTT-BO9H4TzkKi9IAJoiB9FCG_jVT-j3TcHIilU-bCWHptgWcLHNj998YZR-1wU8TcpGKCVEkFu067sJ-2DWUQADPAarcBCB3JH6dFOneiqpMkYYhkVFrpRiOrk-8vPFIvJuo3JI7lWtht3T7_BM_NqLs2NbRRTjv6pUcLWJtA"
          />
        </a>
        <div className="w-10" />
      </header>

      <main className="relative z-10 w-full max-w-md mx-auto px-4 py-6 my-auto">
        <div className="bg-[#FFFDF9] border border-[#ECE2D5] rounded-3xl shadow-[0_12px_40px_-10px_rgba(80,55,30,0.07),0_2px_10px_rgba(0,0,0,0.02)] p-6 sm:p-8">
          <div className="text-center mb-6">
            <h1 className="text-2xl sm:text-[26px] font-bold font-serif text-[#231D19] tracking-tight">
              {tab === 'login' ? 'Iniciar Sesión' : 'Crear Cuenta'}
            </h1>
            <p className="text-xs sm:text-[13px] text-[#756A63] mt-2 leading-relaxed">
              {tab === 'login'
                ? 'Accede para jugar y mejorar tu pensamiento estratégico.'
                : 'Regístrate gratis. Sin datos bancarios, sin publicidad.'}
            </p>
          </div>

          <div className="grid grid-cols-2 p-1 bg-[#F5EFE6] border border-[#EAE0D2] rounded-2xl mb-6">
            <button
              onClick={() => { setTab('login'); setError(null); }}
              className={`py-2 text-xs font-semibold rounded-xl transition-all ${
                tab === 'login' ? 'bg-[#D85A2B] text-white shadow-sm' : 'text-[#756A63] hover:text-[#231D19]'
              }`}
            >
              Iniciar Sesión
            </button>
            <button
              onClick={() => { setTab('signup'); setError(null); }}
              className={`py-2 text-xs font-semibold rounded-xl transition-all ${
                tab === 'signup' ? 'bg-[#D85A2B] text-white shadow-sm' : 'text-[#756A63] hover:text-[#231D19]'
              }`}
            >
              Crear Cuenta
            </button>
          </div>

          {error && (
            <div
              className="mb-4 p-3 rounded-xl bg-[#FFF0F0] border border-[#F5C6C6] text-[#BA1A1A] text-sm text-center animate-shake"
              role="alert"
            >
              {error}
            </div>
          )}

          {tab === 'login' ? (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[#443831] mb-1.5">Usuario o Email</label>
                <input
                  name="username"
                  required
                  type="text"
                  placeholder="Pepito"
                  value={loginForm.username}
                  onChange={handleLoginInputChange}
                  className="w-full pl-10 pr-3.5 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#443831] mb-1.5">Contraseña</label>
                <div className="relative">
                  <input
                    name="password"
                    id="password-input-login"
                    required
                    type={showPass ? 'text' : 'password'}
                    placeholder="••••••••••••"
                    value={loginForm.password}
                    onChange={handleLoginInputChange}
                    className="w-full pl-10 pr-10 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPass(!showPass)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#988A80] hover:text-[#55463E] text-xs"
                  >
                    {showPass ? 'Ocultar' : 'Ver'}
                  </button>
                </div>
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 bg-[#D85A2B] hover:bg-[#BF4C22] disabled:bg-[#D85A2B]/60 text-white text-sm font-semibold rounded-xl shadow-md shadow-[#D85A2B]/25 flex items-center justify-center gap-2 transition-all duration-200 active:scale-[0.99] mt-2"
              >
                <span>{loading ? 'Verificando...' : 'Entrar a Insightful Games'}</span>
              </button>
            </form>
          ) : (
            <form onSubmit={handleSignup} className="space-y-3.5">
              <div>
                <label className="block text-xs font-semibold text-[#443831] mb-1">Nombre de Usuario</label>
                <input
                  name="fullName"
                  required
                  type="text"
                  placeholder="Pepito Pérez"
                  value={signupForm.fullName}
                  onChange={handleSignupInputChange}
                  className="w-full px-3 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#443831] mb-1">Email</label>
                <input
                  name="email"
                  required
                  type="email"
                  placeholder="pepito@insightfulgames.com"
                  value={signupForm.email}
                  onChange={handleSignupInputChange}
                  className="w-full px-3 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <input
                  name="password"
                  required
                  type="password"
                  placeholder="Contraseña"
                  value={signupForm.password}
                  onChange={handleSignupInputChange}
                  className="w-full px-3 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm"
                />
                <input
                  name="confirmPassword"
                  required
                  type="password"
                  placeholder="Confirmar"
                  value={signupForm.confirmPassword}
                  onChange={handleSignupInputChange}
                  className="w-full px-3 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm"
                />
              </div>
              <button
                type="submit"
                disabled={loading}
                className="w-full py-2.5 px-4 bg-[#D85A2B] hover:bg-[#BF4C22] disabled:bg-[#D85A2B]/60 text-white text-sm font-semibold rounded-xl shadow-md shadow-[#D85A2B]/25 flex items-center justify-center gap-2 transition-all duration-200 active:scale-[0.99] mt-2"
              >
                <span>{loading ? 'Creando cuenta...' : 'Registrarse'}</span>
              </button>
            </form>
          )}
        </div>
      </main>
    </div>
  );
}