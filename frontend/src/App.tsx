import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import AuthGate from "./components/AuthGate";
import NotificationBell from "./components/NotificationBell";
import { useModules } from "./hooks/useModules";
import AnalyticsPage from "./pages/Analytics";
import AssistantPage from "./pages/Assistant";
import AutomationPage from "./pages/Automation";
import ModelsPage from "./pages/Models";
import ProfilePage from "./pages/Profile";
import CompaniesPage from "./pages/Companies";
import CompanyPage from "./pages/Company";
import ComparePage from "./pages/Compare";
import Dashboard from "./pages/Dashboard";
import PortfolioPage from "./pages/Portfolio";
import SettingsPage from "./pages/Settings";
import StrategiesPage from "./pages/Strategies";
import WatchlistsPage from "./pages/Watchlists";
import WhatIfPage from "./pages/WhatIf";

function useTheme(): [string, () => void] {
  const [theme, setTheme] = useState(
    () =>
      localStorage.getItem("aiptp-theme") ??
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("aiptp-theme", theme);
  }, [theme]);
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))];
}

export default function App() {
  const [theme, toggleTheme] = useTheme();
  const { running } = useModules();
  return (
    <AuthGate>
      <nav className="rail" aria-label="Primary">
        <div className="brand">AIPTP</div>
        <NavLink to="/" end>
          Dashboard
        </NavLink>
        <NavLink to="/companies">Companies</NavLink>
        <NavLink to="/watchlists">Watchlists</NavLink>
        <NavLink to="/compare">Compare</NavLink>
        <NavLink to="/strategies">Strategies</NavLink>
        <NavLink to="/models">AI Models</NavLink>
        {running("gamification") && <NavLink to="/profile">Profile</NavLink>}
        <NavLink to="/settings">Settings</NavLink>
        <div className="spacer" />
        <NotificationBell />
        <button className="ghost" onClick={toggleTheme}>
          {theme === "dark" ? "Light theme" : "Dark theme"}
        </button>
        <div className="muted" style={{ padding: "12px 12px 0" }}>
          Paper trading only. Real market data; simulated funds.
        </div>
      </nav>
      <main className="content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/portfolios/:id" element={<PortfolioPage />} />
          <Route path="/portfolios/:id/analytics" element={<AnalyticsPage />} />
          <Route path="/portfolios/:id/automation" element={<AutomationPage />} />
          <Route path="/portfolios/:id/assistant" element={<AssistantPage />} />
          <Route path="/portfolios/:id/whatif" element={<WhatIfPage />} />
          <Route path="/models" element={<ModelsPage />} />
          <Route path="/strategies" element={<StrategiesPage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/companies" element={<CompaniesPage />} />
          <Route path="/companies/:symbol" element={<CompanyPage />} />
          <Route path="/watchlists" element={<WatchlistsPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </AuthGate>
  );
}
