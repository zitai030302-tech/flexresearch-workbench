/* Keeps the workspace report link in sync without coupling UI state to agent code. */
(async () => {
  const reportLink = document.querySelector('#report-link');
  const latestSession = async () => {
    const response = await fetch('/api/sessions');
    const data = await response.json();
    const session = data.items?.[0];
    if (session) {
      reportLink.href = `/api/sessions/${session.id}/report.md`;
      reportLink.hidden = false;
    }
  };
  await latestSession();
  document.querySelector('#research-form').addEventListener('submit', () => {
    window.setTimeout(latestSession, 2200);
  });
})();

