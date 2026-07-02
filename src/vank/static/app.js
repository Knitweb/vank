const $ = (id) => document.getElementById(id);

function values(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok || data.ok === false) throw new Error(data.error || "Request failed");
  return data;
}

async function loadState() {
  const data = await fetch("/api/state").then((r) => r.json());
  $("balance").textContent = data.balance;
  $("grant").textContent = data.grant
    ? `${data.grant.grant_id}\nmaterials: ${data.grant.materials.join(", ")}`
    : "Nog geen mintrecht.";
  $("status").textContent = data.audit.ok
    ? `Audit ok · ${data.events.length} events · ${data.unit_count} units`
    : `Audit errors: ${data.audit.errors.join("; ")}`;
  $("events").innerHTML = data.events.map(renderEvent).join("");
  return data;
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[ch]));
}

function renderEvent(e) {
  const sign = e.tokens_delta >= 0 ? "+" : "";
  const eventType = escapeHtml(e.event_type);
  const material = escapeHtml(e.material);
  const batchId = escapeHtml(e.batch_id);
  const assayId = escapeHtml(e.assay_id);
  const eventId = escapeHtml(e.event_id);
  return `
    <div class="event">
      <span class="pill">${eventType} ${sign}${e.tokens_delta} VANK</span>
      <strong>${material} · ${batchId} · ${assayId}</strong>
      <span>${e.mass_g} g × ${e.grade_ppm} ppm = ${e.contained_ug} ug contained</span>
      <code>${eventId}</code>
    </div>`;
}

$("register-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const body = values(ev.currentTarget);
  body.materials = body.materials.split(",").map((x) => x.trim()).filter(Boolean);
  try {
    await api("/api/register", body);
    await loadState();
  } catch (err) {
    alert(err.message);
  }
});

for (const [id, path] of [["measure-form", "/api/measure"], ["revalue-form", "/api/revalue"]]) {
  $(id).addEventListener("submit", async (ev) => {
    ev.preventDefault();
    try {
      await api(path, values(ev.currentTarget));
      await loadState();
    } catch (err) {
      alert(err.message);
    }
  });
}

$("refresh").addEventListener("click", loadState);
$("download").addEventListener("click", async () => {
  const report = await fetch("/api/export").then((r) => r.json());
  const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "vank.report.json";
  a.click();
  URL.revokeObjectURL(url);
});

loadState();
