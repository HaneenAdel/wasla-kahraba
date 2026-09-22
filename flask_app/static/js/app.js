const labels = { open: "متاحة الآن", full: "ممتلئة", closed: "مغلقة" };
const list = document.querySelector("#pointsList");
const count = document.querySelector("#pointsCount");
const form = document.querySelector("#searchForm");
const input = document.querySelector("#searchInput");
const message = document.querySelector("#searchMessage");
const smartReply = document.querySelector("#smartReply");
const smartReplyText = document.querySelector("#smartReplyText");

function formatDate(value) {
  if (!value) return "غير محدد";
  return new Intl.DateTimeFormat("ar", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

function render(items) {
  count.textContent = `${items.length} نقاط مسجلة`;
  if (!items.length) {
    list.innerHTML =
      '<div class="point-card"><h3>لم نجد نقطة مطابقة</h3><p>جرّب اسم منطقة مختلفًا أو نوع خدمة آخر.</p></div>';
    return;
  }
  list.innerHTML = items
    .map((point) => {
      const stale =
        point.last_update &&
        Date.now() - new Date(point.last_update).getTime() >
          1000 * 60 * 60 * 24 * 3;
      return `<article class="point-card"><div class="point-head"><div><h3>${point.chargepoint_name}</h3><p>${point.area} · ${point.service_type}</p><p>${point.description}</p></div><span class="status ${point.status}">${labels[point.status] || point.status}</span></div><div class="meta"><span>الانتظار <b>${point.waiting_count ?? 0} أشخاص</b></span><span>السعة <b>${point.capacity ?? 0}</b></span><span>الساعات <b>${point.opening_hours || "غير محدد"}</b></span><span class="updated">آخر تحديث <b>${formatDate(point.last_update)}</b></span><span class="fresh ${stale ? "stale" : ""}">${stale ? "قديمة - تحتاج تحديثًا" : "محدثة مؤخرًا"}</span></div></article>`;
    })
    .join("");
}

async function search(query = "") {
  if (!query.trim()) {
    smartReply.hidden = true;
    const response = await fetch("/api/chargepoints");
    if (!response.ok) throw new Error("تعذر تحميل نقاط الشحن");
    message.textContent = "";
    render(await response.json());
    return;
  }

  const response = await fetch("/api/smart-search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: query.trim() }),
  });
  if (!response.ok) throw new Error("تعذر تنفيذ البحث الذكي");
  const result = await response.json();
  message.textContent = result.points.length
    ? `نتائج البحث عن: ${query}`
    : `لم نجد نتائج مطابقة للبحث عن: ${query}`;
  smartReplyText.textContent = result.reply;
  smartReply.hidden = false;
  render(result.points);
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  search(input.value).catch(() => {
    message.textContent = "تعذر الاتصال بالخادم.";
  });
});
document.querySelectorAll("[data-query]").forEach((button) =>
  button.addEventListener("click", () => {
    input.value = button.dataset.query;
    search(input.value);
  }),
);
search().catch(() => {
  message.textContent = "تعذر تحميل نقاط الشحن.";
});
