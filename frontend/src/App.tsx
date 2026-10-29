import { Link, Route, Routes } from 'react-router'

function App() {
  return (
    <main>
      <p className="eyebrow">ISE DAY</p>
      <Routes>
        <Route path="/" element={
          <>
            <h1>Seu próximo passo começa com uma descoberta.</h1>
            <p>O quiz de afinidades do ISE Day está em preparação.</p>
          </>
        } />
        <Route path="*" element={
          <>
            <h1>Página não encontrada</h1>
            <Link to="/">Voltar ao início</Link>
          </>
        } />
      </Routes>
    </main>
  )
}

export default App
