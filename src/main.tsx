import React from 'react'
import ReactDOM from 'react-dom/client'
import './style.css'

function App() {
  return <main className="p-8"><h1 className="text-2xl font-bold">C.R.A.T.E.R Mission Control</h1><p>Foundation ready.</p></main>
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><App /></React.StrictMode>,
)
