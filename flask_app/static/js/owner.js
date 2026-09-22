const labels = { open: "متاحة الآن", full: "ممتلئة", closed: "مغلقة" };
let activeOwner = null;
let ownedPoints = [];
const loginView = document.querySelector("#loginView");
const dashboardView = document.querySelector("#dashboardView");
const ownerKey = document.querySelector("#ownerKey");
const loginMessage = document.querySelector("#loginMessage");
const ownerName = document.querySelector("#ownerName");
const ownerPoints = document.querySelector("#ownerPoints");
const pointSelect = document.querySelector("#pointSelect");
const statusInput = document.querySelector("#statusInput");
const hoursInput = document.querySelector("#hoursInput");
const capacityInput = document.querySelector("#capacityInput");
const waitingInput = document.querySelector("#waitingInput");
const saveMessage = document.querySelector("#saveMessage");

function renderStats() {
  document.querySelector("#totalPoints").textContent = ownedPoints.length;
  document.querySelector("#openPoints").textContent = ownedPoints.filter(
    (p) => p.status === "open",
  ).length;
  document.querySelector("#totalWaiting").textContent = ownedPoints.reduce(
    (sum, p) => sum + Number(p.waiting_count || 0),
    0,
  );
}
function renderOwnedPoints() {
  ownerPoints.innerHTML = ownedPoints
    .map(
      (p) =>
        `<button class="owner-point ${p.chargepoint_id === Number(pointSelect.value) ? "selected" : ""}" type="button" data-id="${p.chargepoint_id}"><span><strong>${p.chargepoint_name}</strong><small>${p.area} · السعة ${p.capacity}</small></span><b class="status ${p.status}">${labels[p.status] || p.status}</b></button>`,
    )
    .join("");
  ownerPoints.querySelectorAll("[data-id]").forEach((b) =>
    b.addEventListener("click", () => {
      pointSelect.value = b.dataset.id;
      loadSelectedPoint();
    }),
  );
}
function loadSelectedPoint() {
  const point = ownedPoints.find(
    (p) => p.chargepoint_id === Number(pointSelect.value),
  );
  if (!point) return;
  statusInput.value = point.status;
  hoursInput.value = point.opening_hours || "";
  capacityInput.value = point.capacity || 1;
  waitingInput.value = point.waiting_count || 0;
  document.querySelector("#selectedPointLabel").textContent =
    point.chargepoint_name;
  renderOwnedPoints();
}
async function login(key) {
  const response = await fetch("/api/owner/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ owner_key: key }),
  });
  if (!response.ok) throw new Error("رمز المالك غير صحيح");
  activeOwner = await response.json();
  const pointsResponse = await fetch(
    `/api/owners/${activeOwner.owner_id}/chargepoints`,
  );
  ownedPoints = await pointsResponse.json();
  loginView.hidden = true;
  dashboardView.hidden = false;
  ownerName.textContent = `مرحبًا ${activeOwner.name} — هذه التحديثات ستظهر في الواجهة العامة.`;
  pointSelect.innerHTML = ownedPoints
    .map(
      (p) =>
        `<option value="${p.chargepoint_id}">${p.chargepoint_name}</option>`,
    )
    .join("");
  loadSelectedPoint();
  renderStats();
}
document.querySelector("#loginForm").addEventListener("submit", (e) => {
  e.preventDefault();
  login(ownerKey.value.trim()).catch((error) => {
    loginMessage.textContent = error.message;
  });
});
pointSelect.addEventListener("change", loadSelectedPoint);
document.querySelector("#logoutButton").addEventListener("click", () => {
  activeOwner = null;
  ownedPoints = [];
  dashboardView.hidden = true;
  loginView.hidden = false;
  ownerKey.value = "";
});
document.querySelector("#updateForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = Number(pointSelect.value);
  const response = await fetch(`/api/chargepoints/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      status: statusInput.value,
      opening_hours: hoursInput.value.trim(),
      capacity: Number(capacityInput.value),
      waiting_count: Number(waitingInput.value),
      last_update: new Date().toISOString(),
    }),
  });
  if (!response.ok) {
    saveMessage.textContent = "تعذر حفظ التحديث.";
    return;
  }
  const updated = await response.json();
  ownedPoints = ownedPoints.map((p) => (p.chargepoint_id === id ? updated : p));
  renderStats();
  renderOwnedPoints();
  saveMessage.textContent = "تم حفظ التحديث في قاعدة البيانات.";
  window.setTimeout(() => {
    saveMessage.textContent = "";
  }, 3500);
});
