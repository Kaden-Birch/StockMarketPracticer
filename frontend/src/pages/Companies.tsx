import SymbolSearch from "../components/SymbolSearch";

export default function CompaniesPage() {
  return (
    <div>
      <h1>Companies</h1>
      <div className="card">
        <h2>Find a company</h2>
        <SymbolSearch />
        <p className="muted" style={{ marginTop: 12 }}>
          Search any listed company or ticker to open its dashboard with live
          pricing and interactive charts.
        </p>
      </div>
    </div>
  );
}
