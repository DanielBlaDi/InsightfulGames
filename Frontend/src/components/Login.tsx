import React, { useState } from 'react';

export default function Login() {
  const [tab, setTab] = useState<'login' | 'signup'>('login');
  const [showPass, setShowPass] = useState(false);
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setSuccess(false);
    setTimeout(() => {
      setLoading(false);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 1500);
    }, 1000);
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
        <a href="#" aria-label="Insightful Games Home" className="inline-block hover:scale-[1.01] transition-transform">
          <img alt="Insightful Games" className="h-9 sm:h-10 w-auto object-contain rounded-md" src="https://lh3.googleusercontent.com/aida-public/AB6AXuDLpjEJMqcoHj5kyHCd_den9mRKN0NrinrcNxjKJbXDL9aI6XGvJyoJpT3uUv8gj-sQMchrdLD9pStCkMaJ0_TT4nESDQTT-BO9H4TzkKi9IAJoiB9FCG_jVT-j3TcHIilU-bCWHptgWcLHNj998YZR-1wU8TcpGKCVEkFu067sJ-2DWUQADPAarcBCB3JH6dFOneiqpMkYYhkVFrpRiOrk-8vPFIvJuo3JI7lWtht3T7_BM_NqLs2NbRRTjv6pUcLWJtA" />
        </a>
      </header>

      <main className="relative z-10 w-full max-w-md mx-auto px-4 py-6 my-auto">
        <div className="bg-[#FFFDF9] border border-[#ECE2D5] rounded-3xl shadow-[0_12px_40px_-10px_rgba(80,55,30,0.07),0_2px_10px_rgba(0,0,0,0.02)] p-6 sm:p-8">
          <div className="text-center mb-6">
            <h1 className="text-2xl sm:text-[26px] font-bold font-serif text-[#231D19] tracking-tight">Accede a tu Cuenta</h1>
            <p className="text-xs sm:text-[13px] text-[#756A63] mt-2 leading-relaxed">Calibra tu ELO y entrena con explicaciones heurísticas en tiempo real.</p>
          </div>

          <div className="grid grid-cols-2 p-1 bg-[#F5EFE6] border border-[#EAE0D2] rounded-2xl mb-6">
            <button onClick={() => setTab('login')} className={`py-2 text-xs font-semibold rounded-xl transition-all ${tab === 'login' ? 'bg-[#D85A2B] text-white shadow-sm' : 'text-[#756A63] hover:text-[#231D19]'}`}>Iniciar Sesión</button>
            <button onClick={() => setTab('signup')} className={`py-2 text-xs font-semibold rounded-xl transition-all ${tab === 'signup' ? 'bg-[#D85A2B] text-white shadow-sm' : 'text-[#756A63] hover:text-[#231D19]'}`}>Crear Cuenta</button>
          </div>

          {tab === 'login' ? (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-[#443831] mb-1.5">Email o Usuario</label>
                <input required type="text" placeholder="erfan@insightfulgames.com" className="w-full pl-10 pr-3.5 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm" />
              </div>
              <div>
                <label className="block text-xs font-semibold text-[#443831] mb-1.5">Contraseña</label>
                <div className="relative">
                  <input id="password-input-login" required type={showPass ? 'text' : 'password'} placeholder="••••••••••••" className="w-full pl-10 pr-10 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm" />
                  <button type="button" onClick={() => setShowPass(!showPass)} className="absolute inset-y-0 right-0 pr-3 flex items-center text-[#988A80] hover:text-[#55463E]">{showPass ? 'Ocultar' : 'Ver'}</button>
                </div>
              </div>
              <button type="submit" disabled={loading || success} className="w-full py-2.5 px-4 bg-[#D85A2B] hover:bg-[#BF4C22] text-white text-sm font-semibold rounded-xl shadow-md shadow-[#D85A2B]/25 flex items-center justify-center gap-2 transition-all duration-200 active:scale-[0.99] mt-2">
                <span>{success ? 'Sesión Iniciada' : loading ? 'Verificando...' : 'Entrar a Insightful Games'}</span>
              </button>
            </form>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-3.5">
              <div><label className="block text-xs font-semibold text-[#443831] mb-1">Nombre Completo</label><input required type="text" placeholder="Erfán" className="w-full px-3 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm" /></div>
              <div><label className="block text-xs font-semibold text-[#443831] mb-1">Email</label><input required type="email" placeholder="erfan@insightfulgames.com" className="w-full px-3 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm" /></div>
              <div className="grid grid-cols-2 gap-3"><input required type="password" placeholder="Contraseña" className="w-full px-3 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm" /><input required type="password" placeholder="Confirmar" className="w-full px-3 py-2.5 bg-white border border-[#E5DCD0] rounded-xl text-sm text-[#231D19] placeholder-[#988A80] focus:outline-none focus:border-[#D85A2B] focus:ring-2 focus:ring-[#D85A2B]/15 transition-all shadow-sm" /></div>
              <button type="submit" disabled={loading || success} className="w-full py-2.5 px-4 bg-[#D85A2B] hover:bg-[#BF4C22] text-white text-sm font-semibold rounded-xl shadow-md shadow-[#D85A2B]/25 flex items-center justify-center gap-2 transition-all duration-200 active:scale-[0.99] mt-2">Registrarse</button>
            </form>
          )}
        </div>
      </main>
    </div>
  );
}
