import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import CompaniesPage from "./pages/Companies";
import CompanyPage from "./pages/Company";
import Dashboard from "./pages/Dashboard";
import PortfolioPage from "./pages/Portfolio";

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
  return (
    <>
      <nav className="rail" aria-label="Primary">
        <div className="brand">AIPTP</div>
        <NavLink to="/" end>
          Dashboard
        </NavLink>
        <NavLink to="/companies">Companies</NavLink>
        <div className="spacer" />
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
          <Route path="/companies" element={<CompaniesPage />} />
          <Route path="/companies/:symbol" element={<CompanyPage />} />
        </Routes>
      </main>
    </>
  );
}
