import { NavLink, Navigate, Route, Routes } from 'react-router-dom';
import AnalyzePage from './pages/AnalyzePage';
import SuggestPage from './pages/SuggestPage';
import ClassifyPage from './pages/ClassifyPage';

function NavItem({ to, label }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `nav-item ${isActive ? 'nav-item-active' : ''}`
      }
    >
      {label}
    </NavLink>
  );
}

export default function App() {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div>
          <h1>Literature Classifier</h1>
          <p>三阶段本地工作台：Analyze / Codex标签确认 / Classify</p>
        </div>
        <nav className="nav-tabs">
          <NavItem to="/analyze" label="阶段1 Analyze" />
          <NavItem to="/suggest" label="阶段2 Codex" />
          <NavItem to="/classify" label="阶段3 Classify" />
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/analyze" element={<AnalyzePage />} />
          <Route path="/suggest" element={<SuggestPage />} />
          <Route path="/classify" element={<ClassifyPage />} />
          <Route path="*" element={<Navigate to="/analyze" replace />} />
        </Routes>
      </main>
    </div>
  );
}
