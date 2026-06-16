export default function SetupRequiredPage() {
  return (
    <div className="login-page">
      <div className="login-card">
        <h1 className="login-title">Setup Required</h1>
        <p style={{ color: "#374151", fontSize: 14, lineHeight: "1.6" }}>
          No admin account exists yet. Run the setup script to create one:
        </p>
        <pre style={{
          background: "#f1f5f9", borderRadius: 8, padding: "12px 16px",
          fontSize: 13, marginTop: 16, overflowX: "auto" as const,
        }}>
          {`python scripts/setup.py`}
        </pre>
        <p style={{ color: "#6b7280", fontSize: 13, marginTop: 12 }}>
          Then restart the backend and reload this page.
        </p>
      </div>
    </div>
  );
}
